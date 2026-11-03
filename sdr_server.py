"""
Hermes Outbound SDR Campaign & Leads Dispatcher Backend
Provides REST API, anti-ban pacing engine, SQLite persistence, and hooks into WhatsApp bridge & Google Calendar.
"""

import os
import sys
import time
import json
import random
import glob
import re
import sqlite3
import csv
import io
import asyncio
from datetime import datetime, date
from typing import Optional, List, Dict, Any

import hashlib
import secrets
import unicodedata
import hmac
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request, Response, Depends, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

# Injected venv path for packages if running in container
VENV_PACKAGES = "/opt/hermes/.venv/lib/python3.14/site-packages"
if os.path.exists(VENV_PACKAGES) and VENV_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_PACKAGES)

# Config & Directories
DATA_DIR = os.environ.get("HERMES_DATA_DIR", "/opt/data")
if not os.path.exists(DATA_DIR):
    DATA_DIR = "/opt/hermes-agent/data"
if not os.path.exists(DATA_DIR):
    DATA_DIR = "c:\\++TUDO SOBRE O HERMES"

DOWNLOADS_DIR = os.path.join(DATA_DIR, "downloads")
DB_PATH = os.path.join(DATA_DIR, "campaigns.db")
SCRAPER_NINJA_URL = os.environ.get("SCRAPER_NINJA_URL", "https://leads.acessaronline.com.br").rstrip("/")


# Load .env if present in DATA_DIR or current directory
for env_candidate in [os.path.join(DATA_DIR, ".env"), os.path.join(os.getcwd(), ".env")]:
    if os.path.exists(env_candidate):
        try:
            with open(env_candidate, "r", encoding="utf-8", errors="ignore") as ef:
                for line in ef:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass

BRIDGE_URL = os.environ.get("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:3000")
OWNER_PHONE = os.environ.get("OWNER_PHONE", "5546999765576")

app = FastAPI(title="Hermes Outbound SDR Engine", docs_url="/painel/docs", openapi_url="/painel/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------
# Authentication Guard Middleware
# -------------------------------------------------------------
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    
    # Public endpoints that do not require login
    PUBLIC_PATHS = {
        "/painel",
        "/painel/",
        "/sdr",
        "/sdr/",
        "/painel/api/auth/login",
        "/painel/api/auth/me",
        "/painel/api/auth/logout",
        "/painel/api/webhook/incoming",
        "/docs",
        "/openapi.json"
    }
    
    # Protect all /painel/api/* endpoints (except public ones)
    if path.startswith("/painel/api") and path not in PUBLIC_PATHS:
        token = request.cookies.get("hermes_token")
        if not token:
            auth_header = request.headers.get("Authorization") or ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            elif request.headers.get("X-Auth-Token"):
                token = request.headers.get("X-Auth-Token").strip()
            elif "token" in request.query_params:
                token = request.query_params.get("token")
                
        username = None
        if token:
            try:
                with get_db() as conn:
                    username = validate_session(conn, token)
            except Exception:
                username = None
                
        if not username:
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized", "message": "Acesso não autorizado. Faça login para continuar."}
            )
            
        request.state.user = username

    return await call_next(request)


# -------------------------------------------------------------
# Database Management
# -------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# -------------------------------------------------------------
# Security & Authentication Helpers
# -------------------------------------------------------------
def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return hashed, salt

def verify_password(password: str, hashed: str, salt: str) -> bool:
    try:
        expected, _ = hash_password(password, salt)
        return hmac.compare_digest(expected, hashed)
    except Exception:
        return False

def ensure_admin_user(conn):
    admin_user = os.environ.get("HERMES_ADMIN_USER", "hermessdr").strip()
    admin_pass = os.environ.get("HERMES_ADMIN_PASSWORD", "Max38171").strip()
    if not admin_user or not admin_pass:
        admin_user = "hermessdr"
        admin_pass = "Max38171"
    
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = ?", (admin_user,))
    row = cur.fetchone()
    pw_hash, salt = hash_password(admin_pass)
    now = datetime.now().isoformat()
    if row:
        cur.execute("UPDATE users SET password_hash = ?, salt = ? WHERE username = ?", (pw_hash, salt, admin_user))
    else:
        cur.execute("INSERT INTO users (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                    (admin_user, pw_hash, salt, now))
    conn.commit()

def create_session(conn, username: str, remember_me: bool = True) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    max_age_seconds = 30 * 86400 if remember_me else 86400
    expires_at = datetime.fromtimestamp(now.timestamp() + max_age_seconds).isoformat()
    now_iso = now.isoformat()
    with conn:
        conn.execute(
            "INSERT INTO sessions (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, username, now_iso, expires_at)
        )
    return token, max_age_seconds

def validate_session(conn, token: str) -> Optional[str]:
    if not token:
        return None
    cur = conn.cursor()
    cur.execute("SELECT username, expires_at FROM sessions WHERE token = ?", (token,))
    row = cur.fetchone()
    if not row:
        return None
    username, expires_at = row[0], row[1]
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
        with conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return None
    return username

def delete_session(conn, token: str):
    if token:
        with conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

class LoginPayload(BaseModel):
    username: str
    password: str
    remember: Optional[bool] = True

def init_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            salt TEXT,
            created_at TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT,
            created_at TEXT,
            expires_at TEXT
        )
        """)
        ensure_admin_user(conn)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            name TEXT,
            category TEXT,
            source_folder TEXT,
            daily_limit INTEGER DEFAULT 35,
            min_delay INTEGER DEFAULT 60,
            max_delay INTEGER DEFAULT 180,
            message_template TEXT,
            is_active INTEGER DEFAULT 0,
            is_dry_run INTEGER DEFAULT 1,
            created_at TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_slug TEXT,
            phone TEXT,
            name TEXT,
            category TEXT,
            source_file TEXT,
            status TEXT DEFAULT 'PENDING',
            sent_at TEXT,
            message_sent TEXT,
            response TEXT,
            response_at TEXT,
            error TEXT,
            human_takeover INTEGER DEFAULT 0,
            last_message_at TEXT,
            city TEXT,
            niche TEXT,
            details TEXT,
            created_at TEXT,
            UNIQUE(campaign_slug, phone)
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS dispatch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_phone TEXT,
            campaign_slug TEXT,
            action TEXT,
            status TEXT,
            details TEXT,
            timestamp TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS system_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            phone TEXT PRIMARY KEY,
            reason TEXT,
            created_at TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER,
            lead_phone TEXT,
            role TEXT,
            message TEXT,
            created_at TEXT
        )
        """)

        # Migration: ensure leads table has human_takeover and last_message_at
        cols = [c[1] for c in conn.execute("PRAGMA table_info(leads)").fetchall()]
        if "human_takeover" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN human_takeover INTEGER DEFAULT 0")
        if "last_message_at" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN last_message_at TEXT")
        if "city" not in cols:
            try:
                conn.execute("ALTER TABLE leads ADD COLUMN city TEXT")
            except Exception:
                pass
        if "niche" not in cols:
            try:
                conn.execute("ALTER TABLE leads ADD COLUMN niche TEXT")
            except Exception:
                pass
        if "details" not in cols:
            try:
                conn.execute("ALTER TABLE leads ADD COLUMN details TEXT")
            except Exception:
                pass
        if "created_at" not in cols:
            try:
                conn.execute("ALTER TABLE leads ADD COLUMN created_at TEXT")
            except Exception:
                pass

        # Default state
        defaults = {
            "global_status": "PAUSED",  # RUNNING or PAUSED
            "active_campaign": "lotes_educacao",
            "daily_limit": "35",
            "min_delay": "60",
            "max_delay": "180",
            "dry_run": "1",
            "work_hours_start": "8",
            "work_hours_end": "19",
            "ai_auto_reply": "1"
        }
        for k, v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO system_state (key, value) VALUES (?, ?)", (k, v))
        conn.commit()

# -------------------------------------------------------------
# Spintax & AI Variation Helpers
# -------------------------------------------------------------
def parse_spintax(text: str) -> str:
    """Resolve {opcao1|opcao2|opcao3} recursively, leaving single tags like {nome} intact."""
    pattern = re.compile(r'\{([^{}]+)\}')
    def replace_spin(match):
        content = match.group(1)
        if '|' in content:
            return random.choice(content.split('|'))
        return match.group(0)

    while '{' in text and '}' in text:
        new_text = pattern.sub(replace_spin, text)
        if new_text == text:
            break
        text = new_text
    return text

def get_saudacao():
    h = datetime.now().hour
    if 5 <= h < 12:
        return "Bom dia"
    elif 12 <= h < 18:
        return "Boa tarde"
    else:
        return "Boa noite"

def render_message(template: str, lead_name: str, lead_phone: str) -> str:
    clean = re.sub(r'[\"=\d]', '', lead_name or '').strip()
    clean = re.sub(r'^(prof\.|prof|professor|professora)\s+', '', clean, flags=re.IGNORECASE).strip()
    if clean.lower() in ("desconhecido", "lead", "contato", "professores", "seed", "grupo"):
        clean = ""
    nome_display = clean.split()[0].title() if clean and len(clean) >= 2 else ""

    msg = parse_spintax(template)
    msg = msg.replace("{saudacao}", get_saudacao())
    msg = msg.replace("{nome}", f" {nome_display}" if nome_display else "")
    msg = re.sub(r' +', ' ', msg)
    msg = re.sub(r' ,', ',', msg)
    return msg.strip()

# -------------------------------------------------------------
# Lead Scanner / Ingestion
# -------------------------------------------------------------
def sync_leads_from_folders():
    init_db()
    categories_map = {
        "lotes_manual_test": ("Lista Manual & Testes Seguros", "Testes"),
        "lotes_educacao": ("Professores e Educação PR", "Educação"),
        "lotes_negocios": ("Negócios, PLR e Afiliados", "Negócios"),
        "lotes_regional_caronas": ("Regional e Caronas PR/SC", "Regional"),
        "lotes_tecnologia": ("Tecnologia e Programação", "Tech"),
        "lotes_robotica_computacao": ("Robótica e Computação Escolar", "Educação"),
        "lotes_escolas_seed": ("Escolas e Projetos SEED", "Educação"),
        "lotes_turismo_milhas": ("Turismo e Milhas", "Turismo"),
        "lotes_saude_bemestar": ("Saúde e Bem-Estar", "Saúde"),
        "lotes_empregos_vagas": ("Empregos e Vagas", "Empregos"),
        "lotes_pos_graduacao": ("Pós-Graduação e Cursos", "Educação"),
        "lotes_mmn_vendasdiretas": ("MMN e Vendas Diretas", "Vendas"),
        "lotes_cripto_investimentos": ("Cripto e Investimentos", "Finanças"),
        "lotes_ofertas_ecommerce": ("Ofertas e E-commerce", "E-commerce"),
        "lotes_politica_debates": ("Política e Debates", "Sociedade"),
        "lotes_ferramentas_apps": ("Ferramentas e Apps", "Tech"),
        "lotes_servicos_mobilidade_rifas": ("Serviços e Mobilidade", "Serviços"),
        "lotes_agenda_telefonica": ("Agenda Telefônica Segmentada", "Contatos")
    }

    templates_default = {
        "lotes_manual_test": "{Olá|Oi|Tudo bem}{nome}? {Aqui é o Salesio|Sou o Salesio Ninja}. Estou fazendo um teste da nossa nova plataforma de automação e SDR com IA no WhatsApp.\n\nComo você está? Se puder me responder com 'ok' ou qualquer dúvida, já valida o fluxo de resposta automática!",
        "lotes_educacao": "{Olá|Oi|Tudo bem}{nome}? {Aqui é o Salesio|Sou o Salesio}, especialista em automações e inteligência artificial para o setor educacional no Paraná.\n\nNotei seu perfil em fóruns de educadores do estado. Estamos demonstrando como professores e gestores estão economizando mais de 10 horas semanais com assistentes IA pedagógicos alinhados à BNCC.\n\nTeria 5 minutinhos amanhã para conversarmos ou posso te enviar um material rápido sobre como funciona?",
        "lotes_negocios": "{Olá|Oi|Tudo bom}{nome}? {Aqui é o Salesio|Sou o Salesio Ninja}, desenvolvedor e especialista em automações de vendas e SDR com IA.\n\nVi seu contato em comunidades de negócios e produtos digitais. Desenvolvemos uma solução de atendimento e prospecção ativa que qualifica leads e agenda reuniões no WhatsApp de forma 100% humanizada e sem risco de banimento.\n\nVocê teria disponibilidade amanhã para ver uma demonstração prática de 5 minutos?",
        "lotes_regional_caronas": "{Olá|Oi}{nome}, {tudo bem|como vai}? {Aqui é o Salesio|Sou o Salesio}, contato da nossa rede regional do Paraná.\n\nPassando só para validar o seu contato na nossa rede de networking e parcerias regionais. Um abraço e excelente semana!",
        "lotes_tecnologia": "{Olá|Oi}{nome}, {tudo bem|como você está}? {Aqui é o Salesio|Sou o Salesio Ninja}, atuando com infraestrutura de agentes autônomos e IA avançada.\n\nVi seu contato em grupos de tech/desenvolvimento. Estamos conectando desenvolvedores e parceiros para soluções de IA corporativa.\n\nSe tiver interesse em trocar uma ideia sobre agentes e automação, me dá um toque por aqui!"
    }

    with get_db() as conn:
        for folder_name, (cat_title, main_cat) in categories_map.items():
            folder_path = os.path.join(DOWNLOADS_DIR, folder_name)
            default_tmpl = templates_default.get(folder_name, "{Olá|Oi}{nome}, {tudo bem|como vai}? Aqui é o Salesio. Um grande abraço!")
            
            conn.execute("""
            INSERT OR IGNORE INTO campaigns 
            (slug, name, category, source_folder, message_template, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (folder_name, cat_title, main_cat, folder_path, default_tmpl, datetime.now().isoformat()))

            if not os.path.exists(folder_path):
                continue

            csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
            for csv_path in csv_files:
                base_file = os.path.basename(csv_path)
                try:
                    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    
                    for line in lines[1:]:  # skip header
                        parts = line.strip().split(";") if ";" in line else line.strip().split(",")
                        if not parts:
                            continue
                        
                        phone_raw = parts[0].strip()
                        name_raw = parts[1].strip() if len(parts) > 1 else ""
                        
                        digits = re.sub(r'\D', '', phone_raw)
                        if len(digits) in (10, 11) and not digits.startswith("55"):
                            digits = "55" + digits
                        
                        if len(digits) >= 12 and len(digits) <= 14:
                            conn.execute("""
                            INSERT OR IGNORE INTO leads 
                            (campaign_slug, phone, name, category, source_file, status)
                            VALUES (?, ?, ?, ?, ?, 'PENDING')
                            """, (folder_name, digits, name_raw, main_cat, base_file))
                except Exception as e:
                    print(f"Erro lendo CSV {csv_path}: {e}")

        conn.commit()

# -------------------------------------------------------------
# Background SDR Dispatcher Task
# -------------------------------------------------------------
async def sdr_dispatcher_loop():
    print("Hermes SDR Dispatcher Engine Iniciado!")
    while True:
        try:
            await asyncio.sleep(5)
            with get_db() as conn:
                state_rows = conn.execute("SELECT key, value FROM system_state").fetchall()
                state = {r["key"]: r["value"] for r in state_rows}
            
            global_status = state.get("global_status", "PAUSED")
            if global_status != "RUNNING":
                continue

            active_slug = state.get("active_campaign", "lotes_educacao")
            is_dry_run = state.get("dry_run", "1") == "1"
            daily_limit = int(state.get("daily_limit", 35))
            min_delay = int(state.get("min_delay", 60))
            max_delay = int(state.get("max_delay", 180))
            work_start = int(state.get("work_hours_start", 8))
            work_end = int(state.get("work_hours_end", 19))

            # Check working hours
            now = datetime.now()
            if not (work_start <= now.hour < work_end):
                print(f"[Hermes SDR] Fora do horário comercial ({now.hour}h). Aguardando...")
                await asyncio.sleep(60)
                continue

            today_str = date.today().isoformat()
            with get_db() as conn:
                count_today = conn.execute(
                    "SELECT COUNT(*) as c FROM leads WHERE sent_at LIKE ? AND status IN ('SENT', 'DRY_RUN')",
                    (f"{today_str}%",)
                ).fetchone()["c"]

                if count_today >= daily_limit:
                    print(f"[Hermes SDR] Limite diário atingido ({count_today}/{daily_limit}). Pausando robô...")
                    conn.execute("UPDATE system_state SET value = 'PAUSED_LIMIT' WHERE key = 'global_status'")
                    conn.commit()
                    continue

                # Fetch active campaign
                camp = conn.execute("SELECT * FROM campaigns WHERE slug = ?", (active_slug,)).fetchone()
                if not camp:
                    continue

                # Fetch next lead
                lead = conn.execute("""
                SELECT * FROM leads 
                WHERE campaign_slug = ? AND status = 'PENDING' AND phone NOT IN (SELECT phone FROM blacklist)
                ORDER BY id ASC LIMIT 1
                """, (active_slug,)).fetchone()

                if not lead:
                    print(f"[Hermes SDR] Fila zerada para a campanha {active_slug}. Pausando...")
                    conn.execute("UPDATE system_state SET value = 'COMPLETED' WHERE key = 'global_status'")
                    conn.commit()
                    continue

            lead_id = lead["id"]
            phone = lead["phone"]
            name = lead["name"]
            template = camp["message_template"] or "Olá{nome}, tudo bem? Aqui é o Salesio."
            final_message = render_message(template, name, phone)

            print(f"[Hermes SDR] Processando Lead #{lead_id}: {phone} ({name}) | Modo: {'DRY_RUN' if is_dry_run else 'LIVE'}")

            if is_dry_run:
                # Simula delay curto
                await asyncio.sleep(random.uniform(4, 8))
                now_iso = datetime.now().isoformat()
                with get_db() as conn:
                    conn.execute("""
                    UPDATE leads 
                    SET status = 'DRY_RUN', sent_at = ?, message_sent = ?
                    WHERE id = ?
                    """, (now_iso, final_message, lead_id))
                    conn.execute("""
                    INSERT INTO dispatch_logs (lead_phone, campaign_slug, action, status, details, timestamp)
                    VALUES (?, ?, 'DRY_RUN_SEND', 'SUCCESS', ?, ?)
                    """, (phone, active_slug, final_message, now_iso))
                    conn.commit()
                print(f"[Hermes SDR] [SIMULAÇÃO] Mensagem gravada para {phone}: '{final_message[:50]}...'")
            else:
                # LIVE MODE: Simula digitação e envia via Baileys WhatsApp Bridge
                target_jid = f"{phone}@s.whatsapp.net"
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        # 1. Simula digitando
                        try:
                            await client.post(f"{BRIDGE_URL}/typing", json={"chatId": target_jid, "presence": "composing"})
                            await asyncio.sleep(random.uniform(4.0, 7.0))
                            await client.post(f"{BRIDGE_URL}/typing", json={"chatId": target_jid, "presence": "paused"})
                        except Exception as e:
                            print(f"[Hermes SDR] Aviso digitando: {e}")

                        # 2. Envia mensagem real
                        res = await client.post(f"{BRIDGE_URL}/send", json={"chatId": target_jid, "message": final_message})
                        
                        now_iso = datetime.now().isoformat()
                        if res.status_code == 200:
                            res_data = res.json()
                            resolved_jid = res_data.get("resolvedJid", target_jid)
                            actual_phone = resolved_jid.replace("@s.whatsapp.net", "") if resolved_jid else phone
                            with get_db() as conn:
                                try:
                                    conn.execute("""
                                    UPDATE leads 
                                    SET status = 'SENT', sent_at = ?, message_sent = ?, phone = ?
                                    WHERE id = ?
                                    """, (now_iso, final_message, actual_phone, lead_id))
                                except sqlite3.IntegrityError:
                                    conn.execute("""
                                    UPDATE leads 
                                    SET status = 'SENT', sent_at = ?, message_sent = ?
                                    WHERE id = ?
                                    """, (now_iso, final_message, lead_id))
                                conn.execute("""
                                INSERT INTO dispatch_logs (lead_phone, campaign_slug, action, status, details, timestamp)
                                VALUES (?, ?, 'WHATSAPP_SENT', 'SUCCESS', ?, ?)
                                """, (actual_phone, active_slug, final_message, now_iso))
                                conn.execute("""
                                INSERT INTO conversation_messages (lead_id, lead_phone, role, message, created_at)
                                VALUES (?, ?, 'outbound', ?, ?)
                                """, (lead_id, actual_phone, final_message, now_iso))
                                conn.commit()
                            print(f"[Hermes SDR] [ENVIADO COM SUCESSO] {actual_phone}")
                        else:
                            err_msg = res.text
                            with get_db() as conn:
                                conn.execute("""
                                UPDATE leads 
                                SET status = 'ERROR', error = ?
                                WHERE id = ?
                                """, (err_msg, lead_id))
                                conn.commit()
                            print(f"[Hermes SDR] [ERRO AO ENVIAR] {phone}: {err_msg}")
                except Exception as ex:
                    print(f"[Hermes SDR] Exceção de rede: {ex}")

            # Sleep human random delay between dispatches
            delay = random.uniform(min_delay, max_delay) if not is_dry_run else random.uniform(5, 12)
            print(f"[Hermes SDR] Aguardando pacing de {delay:.1f}s antes do próximo disparo...")
            await asyncio.sleep(delay)

        except Exception as general_err:
            print(f"[Hermes SDR] Erro no loop de disparo: {general_err}")
            await asyncio.sleep(10)

async def scheduled_messages_worker():
    print("[Hermes SDR] Worker de Mensagens Agendadas Iniciado!")
    tz_br = timezone(timedelta(hours=-3))
    while True:
        try:
            await asyncio.sleep(15)
            now_utc_iso = datetime.now(timezone.utc).isoformat()
            
            with get_db() as conn:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_dispatches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    lead_name TEXT,
                    message TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    error TEXT
                )
                """)
                
                pending = conn.execute("""
                SELECT id, phone, lead_name, message, scheduled_for 
                FROM scheduled_dispatches 
                WHERE status = 'PENDING' AND scheduled_for <= ?
                ORDER BY scheduled_for ASC
                """, (now_utc_iso,)).fetchall()
                
                if not pending:
                    continue

                for item in pending:
                    disp_id = item["id"]
                    phone = item["phone"]
                    name = item["lead_name"] or "Contato"
                    msg = item["message"]
                    target_jid = f"{phone}@s.whatsapp.net"
                    
                    try:
                        async with httpx.AsyncClient(timeout=15.0) as client:
                            await client.post(f"{BRIDGE_URL}/typing", json={"chatId": target_jid, "presence": "composing"})
                            await asyncio.sleep(2.0)
                            await client.post(f"{BRIDGE_URL}/typing", json={"chatId": target_jid, "presence": "paused"})
                            res = await client.post(f"{BRIDGE_URL}/send", json={"chatId": target_jid, "message": msg})
                            
                        now_sent = datetime.now(timezone.utc).isoformat()
                        if res.status_code == 200:
                            conn.execute("UPDATE scheduled_dispatches SET status = 'SENT', sent_at = ? WHERE id = ?", (now_sent, disp_id))
                            
                            now_iso = datetime.now().isoformat()
                            lead_row = conn.execute("SELECT id FROM leads WHERE phone = ? ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
                            if lead_row:
                                conn.execute("""
                                INSERT INTO conversation_messages (lead_id, lead_phone, role, message, created_at)
                                VALUES (?, ?, 'assistant', ?, ?)
                                """, (lead_row["id"], phone, msg, now_iso))
                                conn.execute("UPDATE leads SET last_message_at = ?, message_sent = ? WHERE id = ?", (now_iso, msg, lead_row["id"]))
                            
                            time_br = datetime.now(tz_br).strftime("%H:%M")
                            notify_text = (
                                f"⏰ *HERMES: MENSAGEM AGENDADA ENTREGUE!*\n\n"
                                f"👤 *Destinatário:* {name} (+{phone})\n"
                                f"🕐 *Entregue às:* {time_br}\n"
                                f"💬 *Mensagem enviada:*\n\"{msg}\""
                            )
                            async with httpx.AsyncClient(timeout=10.0) as client:
                                await client.post(f"{BRIDGE_URL}/send", json={"chatId": f"{OWNER_PHONE}@s.whatsapp.net", "message": notify_text})
                                
                            print(f"[Hermes SDR] Mensagem agendada #{disp_id} para {phone} entregue com sucesso!")
                        else:
                            conn.execute("UPDATE scheduled_dispatches SET status = 'FAILED', error = ? WHERE id = ?", (res.text, disp_id))
                    except Exception as err:
                        print(f"[Hermes SDR] Erro ao enviar mensagem agendada #{disp_id}: {err}")
                        conn.execute("UPDATE scheduled_dispatches SET status = 'FAILED', error = ? WHERE id = ?", (str(err), disp_id))
                conn.commit()
        except Exception as e:
            print(f"[Hermes SDR] Erro no worker de mensagens agendadas: {e}")


@app.on_event("startup")
async def on_startup():
    init_db()
    asyncio.create_task(sdr_dispatcher_loop())
    asyncio.create_task(scheduled_messages_worker())

# -------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------

# -------------------------------------------------------------
# Authentication Endpoints
# -------------------------------------------------------------
@app.post("/painel/api/auth/login")
async def auth_login(req: LoginPayload):
    req_username = req.username.strip()
    req_password = req.password.strip()
    
    init_db()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT password_hash, salt FROM users WHERE username = ?", (req_username,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Usuário ou senha incorretos."}
            )
        
        pw_hash, salt = row[0], row[1]
        if not verify_password(req_password, pw_hash, salt):
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Usuário ou senha incorretos."}
            )
        
        token, max_age = create_session(conn, req_username, req.remember if req.remember is not None else True)
    
    res = JSONResponse(
        content={
            "success": True,
            "token": token,
            "user": {"username": req_username}
        }
    )
    res.set_cookie(
        key="hermes_token",
        value=token,
        max_age=max_age,
        expires=max_age,
        path="/",
        httponly=False,
        samesite="lax",
        secure=False
    )
    return res

@app.get("/painel/api/auth/me")
async def auth_me(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        token = request.cookies.get("hermes_token")
        if not token:
            auth_header = request.headers.get("Authorization") or ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            elif request.headers.get("X-Auth-Token"):
                token = request.headers.get("X-Auth-Token").strip()
            elif "token" in request.query_params:
                token = request.query_params.get("token")
        if token:
            with get_db() as conn:
                user = validate_session(conn, token)
                
    if user:
        return {"authenticated": True, "user": {"username": user}}
    return JSONResponse(status_code=401, content={"authenticated": False, "message": "Não autenticado."})

@app.post("/painel/api/auth/logout")
async def auth_logout(request: Request):
    token = request.cookies.get("hermes_token")
    if not token:
        auth_header = request.headers.get("Authorization") or ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif request.headers.get("X-Auth-Token"):
            token = request.headers.get("X-Auth-Token").strip()
            
    if token:
        try:
            with get_db() as conn:
                delete_session(conn, token)
        except Exception:
            pass
            
    res = JSONResponse(content={"success": True, "message": "Sessão encerrada com sucesso."})
    res.delete_cookie(key="hermes_token", path="/")
    res.delete_cookie(key="hermes_token", path="/painel")
    return res

@app.get("/painel/api/stats")
async def get_stats():
    init_db()
    today_str = date.today().isoformat()
    with get_db() as conn:
        total_leads = conn.execute("SELECT COUNT(*) as c FROM leads").fetchone()["c"]
        total_pending = conn.execute("SELECT COUNT(*) as c FROM leads WHERE status = 'PENDING'").fetchone()["c"]
        sent_today = conn.execute(
            "SELECT COUNT(*) as c FROM leads WHERE sent_at LIKE ? AND status IN ('SENT', 'DRY_RUN')",
            (f"{today_str}%",)
        ).fetchone()["c"]
        total_replies = conn.execute("SELECT COUNT(*) as c FROM leads WHERE status = 'REPLIED'").fetchone()["c"]
        total_scheduled = conn.execute("SELECT COUNT(*) as c FROM leads WHERE status = 'SCHEDULED'").fetchone()["c"]

        state_rows = conn.execute("SELECT key, value FROM system_state").fetchall()
        state = {r["key"]: r["value"] for r in state_rows}

    # WhatsApp connection status
    wa_connected = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{BRIDGE_URL}/health")
            if r.status_code == 200 and r.json().get("status") == "connected":
                wa_connected = True
    except Exception:
        pass

    return {
        "total_leads": total_leads,
        "total_pending": total_pending,
        "sent_today": sent_today,
        "total_replies": total_replies,
        "total_scheduled": total_scheduled,
        "daily_limit": int(state.get("daily_limit", 35)),
        "global_status": state.get("global_status", "PAUSED"),
        "dry_run": state.get("dry_run", "1") == "1",
        "active_campaign": state.get("active_campaign", "lotes_educacao"),
        "min_delay": int(state.get("min_delay", 60)),
        "max_delay": int(state.get("max_delay", 180)),
        "whatsapp_connected": wa_connected,
        "ai_auto_reply": state.get("ai_auto_reply", "1") == "1"
    }

@app.get("/painel/api/campaigns")
async def get_campaigns():
    init_db()
    with get_db() as conn:
        camps = conn.execute("SELECT * FROM campaigns ORDER BY id ASC").fetchall()
        res = []
        for c in camps:
            total = conn.execute("SELECT COUNT(*) as count FROM leads WHERE campaign_slug = ?", (c["slug"],)).fetchone()["count"]
            pending = conn.execute("SELECT COUNT(*) as count FROM leads WHERE campaign_slug = ? AND status = 'PENDING'", (c["slug"],)).fetchone()["count"]
            sent = conn.execute("SELECT COUNT(*) as count FROM leads WHERE campaign_slug = ? AND status IN ('SENT', 'DRY_RUN')", (c["slug"],)).fetchone()["count"]
            res.append({
                "id": c["id"],
                "slug": c["slug"],
                "name": c["name"],
                "category": c["category"],
                "template": c["message_template"],
                "total_leads": total,
                "pending_leads": pending,
                "sent_leads": sent
            })
    return res

class ControlPayload(BaseModel):
    action: str  # start, pause, toggle_dry_run, sync_leads
    campaign_slug: Optional[str] = None

@app.post("/painel/api/control")
async def control_sdr(payload: ControlPayload):
    with get_db() as conn:
        if payload.action == "start":
            conn.execute("UPDATE system_state SET value = 'RUNNING' WHERE key = 'global_status'")
        elif payload.action == "pause":
            conn.execute("UPDATE system_state SET value = 'PAUSED' WHERE key = 'global_status'")
        elif payload.action == "toggle_dry_run":
            curr = conn.execute("SELECT value FROM system_state WHERE key = 'dry_run'").fetchone()["value"]
            new_val = "0" if curr == "1" else "1"
            conn.execute("UPDATE system_state SET value = ? WHERE key = 'dry_run'", (new_val,))
        elif payload.action == "toggle_ai_reply":
            curr = conn.execute("SELECT value FROM system_state WHERE key = 'ai_auto_reply'").fetchone()
            curr_val = curr["value"] if curr else "1"
            new_val = "0" if curr_val == "1" else "1"
            conn.execute("UPDATE system_state SET value = ? WHERE key = 'ai_auto_reply'", (new_val,))
        elif payload.action == "sync_leads":
            sync_leads_from_folders()

        if payload.campaign_slug:
            conn.execute("UPDATE system_state SET value = ? WHERE key = 'active_campaign'", (payload.campaign_slug,))
        conn.commit()

    return {"success": True, "action": payload.action}

class SettingsPayload(BaseModel):
    daily_limit: int
    min_delay: int
    max_delay: int
    dry_run: bool
    active_campaign: str
    message_template: Optional[str] = None

@app.post("/painel/api/settings")
async def update_settings(payload: SettingsPayload):
    with get_db() as conn:
        conn.execute("UPDATE system_state SET value = ? WHERE key = 'daily_limit'", (str(payload.daily_limit),))
        conn.execute("UPDATE system_state SET value = ? WHERE key = 'min_delay'", (str(payload.min_delay),))
        conn.execute("UPDATE system_state SET value = ? WHERE key = 'max_delay'", (str(payload.max_delay),))
        conn.execute("UPDATE system_state SET value = ? WHERE key = 'dry_run'", ("1" if payload.dry_run else "0",))
        conn.execute("UPDATE system_state SET value = ? WHERE key = 'active_campaign'", (payload.active_campaign,))
        
        if payload.message_template:
            conn.execute("UPDATE campaigns SET message_template = ? WHERE slug = ?", (payload.message_template, payload.active_campaign))
        conn.commit()
    return {"success": True}

@app.get("/painel/api/leads")
async def get_leads(
    campaign_slug: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50
):
    offset = (page - 1) * limit
    query = "SELECT * FROM leads WHERE 1=1"
    params = []
    
    if campaign_slug and campaign_slug != "all":
        query += " AND campaign_slug = ?"
        params.append(campaign_slug)
    if status and status != "all":
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (phone LIKE ? OR name LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")

    count_query = query.replace("SELECT *", "SELECT COUNT(*) as c")
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as conn:
        total = conn.execute(count_query, params[:-2]).fetchone()["c"]
        rows = conn.execute(query, params).fetchall()
        leads = [dict(r) for r in rows]

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "leads": leads
    }

class PreviewRequest(BaseModel):
    template: str
    lead_name: Optional[str] = "Prof. Carlos Silva"
    lead_phone: Optional[str] = "5546999765576"

@app.post("/painel/api/preview-ai")
async def preview_ai(req: PreviewRequest):
    variations = []
    for _ in range(3):
        variations.append(render_message(req.template, req.lead_name, req.lead_phone))
    return {"variations": variations}

# -------------------------------------------------------------
# Manual Dispatch / Safe Known Leads Test
# -------------------------------------------------------------
class ManualContactItem(BaseModel):
    phone: str
    name: Optional[str] = ""

class ManualDispatchRequest(BaseModel):
    raw_text: Optional[str] = None
    contacts: Optional[List[ManualContactItem]] = None
    template: Optional[str] = None
    immediate: bool = True
    dry_run: bool = False

@app.post("/painel/api/manual-dispatch")
async def manual_dispatch(payload: ManualDispatchRequest):
    """
    Dispatches to a manually pasted list of contacts or adds them to the queue.
    If immediate=True, sends right away with typing simulation without waiting for long queue delays.
    """
    init_db()
    items_to_send = []

    # 1. Parse raw_text if provided
    if payload.raw_text:
        lines = payload.raw_text.strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(";") if ";" in line else line.split(",")
            phone_raw = parts[0].strip()
            name_raw = parts[1].strip() if len(parts) > 1 else ""
            digits = re.sub(r'\D', '', phone_raw)
            if len(digits) in (10, 11) and not digits.startswith("55"):
                digits = "55" + digits
            if len(digits) >= 12 and len(digits) <= 14:
                items_to_send.append({"phone": digits, "name": name_raw})

    # 2. Add explicit contacts
    if payload.contacts:
        for c in payload.contacts:
            digits = re.sub(r'\D', '', c.phone)
            if len(digits) in (10, 11) and not digits.startswith("55"):
                digits = "55" + digits
            if len(digits) >= 12 and len(digits) <= 14:
                items_to_send.append({"phone": digits, "name": c.name or ""})

    if not items_to_send:
        raise HTTPException(status_code=400, detail="Nenhum número de telefone válido encontrado. Use o formato: 46999765576 ou 5546999765576, Nome")

    # Template
    template = payload.template
    if not template:
        with get_db() as conn:
            camp = conn.execute("SELECT message_template FROM campaigns WHERE slug = 'lotes_manual_test'").fetchone()
            template = camp["message_template"] if camp else "{Olá|Oi}{nome}, tudo bem? Aqui é o Salesio Ninja."

    results = []
    now_iso = datetime.now().isoformat()

    with get_db() as conn:
        for item in items_to_send:
            phone = item["phone"]
            name = item["name"]
            msg_rendered = render_message(template, name, phone)

            # Insert or update in leads table under lotes_manual_test
            conn.execute("""
            INSERT INTO leads (campaign_slug, phone, name, category, source_file, status, message_sent)
            VALUES ('lotes_manual_test', ?, ?, 'Testes', 'manual_input', 'PENDING', ?)
            ON CONFLICT(campaign_slug, phone) DO UPDATE SET 
                name = coalesce(nullif(excluded.name, ''), leads.name),
                category = 'Testes',
                source_file = 'manual_input',
                status = 'PENDING',
                message_sent = excluded.message_sent
            """, (phone, name, msg_rendered))
            conn.commit()

            lead_row = conn.execute("SELECT id FROM leads WHERE campaign_slug = 'lotes_manual_test' AND phone = ?", (phone,)).fetchone()
            lead_id = lead_row["id"] if lead_row else None

            if not payload.immediate:
                results.append({
                    "phone": phone,
                    "name": name,
                    "status": "QUEUED",
                    "message": msg_rendered,
                    "details": "Adicionado à fila de testes manual"
                })
                continue

            # IMMEDIATE DISPATCH:
            if payload.dry_run:
                conn.execute("""
                UPDATE leads SET status = 'DRY_RUN', sent_at = ?, message_sent = ? WHERE id = ?
                """, (now_iso, msg_rendered, lead_id))
                conn.execute("""
                INSERT INTO dispatch_logs (lead_phone, campaign_slug, action, status, details, timestamp)
                VALUES (?, 'lotes_manual_test', 'MANUAL_DRY_RUN', 'SUCCESS', ?, ?)
                """, (phone, msg_rendered, now_iso))
                conn.commit()
                results.append({
                    "phone": phone,
                    "name": name,
                    "status": "DRY_RUN",
                    "message": msg_rendered,
                    "details": "Simulado com sucesso (Dry-Run)"
                })
            else:
                # REAL LIVE SEND
                target_jid = f"{phone}@s.whatsapp.net"
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        # Typing simulation
                        try:
                            await client.post(f"{BRIDGE_URL}/typing", json={"chatId": target_jid, "presence": "composing"})
                            await asyncio.sleep(3.0)
                            await client.post(f"{BRIDGE_URL}/typing", json={"chatId": target_jid, "presence": "paused"})
                        except Exception:
                            pass

                        # Send WhatsApp message
                        res = await client.post(f"{BRIDGE_URL}/send", json={"chatId": target_jid, "message": msg_rendered})
                        if res.status_code == 200:
                            res_data = res.json()
                            resolved_jid = res_data.get("resolvedJid", target_jid)
                            actual_phone = resolved_jid.replace("@s.whatsapp.net", "") if resolved_jid else phone
                            try:
                                conn.execute("""
                                UPDATE leads SET status = 'SENT', sent_at = ?, message_sent = ?, phone = ? WHERE id = ?
                                """, (now_iso, msg_rendered, actual_phone, lead_id))
                            except sqlite3.IntegrityError:
                                conn.execute("""
                                UPDATE leads SET status = 'SENT', sent_at = ?, message_sent = ? WHERE id = ?
                                """, (now_iso, msg_rendered, lead_id))
                            conn.execute("""
                            INSERT INTO dispatch_logs (lead_phone, campaign_slug, action, status, details, timestamp)
                            VALUES (?, 'lotes_manual_test', 'MANUAL_SENT', 'SUCCESS', ?, ?)
                            """, (actual_phone, msg_rendered, now_iso))
                            conn.execute("""
                            INSERT INTO conversation_messages (lead_id, lead_phone, role, message, created_at)
                            VALUES (?, ?, 'outbound', ?, ?)
                            """, (lead_id, actual_phone, msg_rendered, now_iso))
                            conn.commit()
                            results.append({
                                "phone": actual_phone,
                                "name": name,
                                "status": "SENT",
                                "message": msg_rendered,
                                "details": "Enviado com sucesso no WhatsApp"
                            })
                        else:
                            err_text = res.text
                            conn.execute("""
                            UPDATE leads SET status = 'ERROR', error = ? WHERE id = ?
                            """, (err_text, lead_id))
                            conn.commit()
                            results.append({
                                "phone": phone,
                                "name": name,
                                "status": "ERROR",
                                "message": msg_rendered,
                                "details": f"Erro do WhatsApp: {err_text}"
                            })
                except Exception as ex:
                    conn.execute("""
                    UPDATE leads SET status = 'ERROR', error = ? WHERE id = ?
                    """, (str(ex), lead_id))
                    conn.commit()
                    results.append({
                        "phone": phone,
                        "name": name,
                        "status": "ERROR",
                        "message": msg_rendered,
                        "details": f"Erro de conexão: {str(ex)}"
                    })

                # Small polite delay between multiple immediate sends
                if len(items_to_send) > 1:
                    await asyncio.sleep(2.0)

    return {
        "success": True,
        "count": len(results),
        "immediate": payload.immediate,
        "dry_run": payload.dry_run,
        "results": results
    }

@app.get("/painel/api/calendar")
async def get_calendar_events():
    """Fetch next events from Google Calendar via hermes_calendar.py or agenda tool."""
    try:
        cmd = "/usr/local/bin/agenda list 7" if os.path.exists("/usr/local/bin/agenda") else "python3 /opt/data/hermes_calendar.py list 7"
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out_text = stdout.decode("utf-8", errors="replace")
        return {"events_raw": out_text}
    except Exception as e:
        return {"error": str(e), "events_raw": "Agenda Google integrada. Próximos compromissos sincronizados."}

# -------------------------------------------------------------
# Conversational AI SDR Engine & Inbound Handlers
# -------------------------------------------------------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

# Real-Time SSE Broadcasting for Live Chat
active_sse_clients: List[asyncio.Queue] = []

async def broadcast_chat_event(event_type: str, data: dict):
    if "message" in data and "content" not in data:
        data["content"] = data["message"]
    if "content" in data and "message" not in data:
        data["message"] = data["content"]
        
    payload = json.dumps(data)
    sse_frame = f"event: {event_type}\ndata: {payload}\n\n"
    generic_frame = f"data: {json.dumps({'type': event_type, 'data': data})}\n\n"
    combined_frame = sse_frame + generic_frame

    to_remove = []
    for q in active_sse_clients:
        try:
            q.put_nowait(combined_frame)
        except Exception:
            to_remove.append(q)
    for q in to_remove:
        if q in active_sse_clients:
            active_sse_clients.remove(q)

def find_lead_by_phone(conn, raw_phone: str):
    digits = re.sub(r'\D', '', raw_phone or '')
    if not digits:
        return None
        
    with_55 = digits if digits.startswith("55") else "55" + digits
    variations = [digits, with_55]
    
    if with_55.startswith("55"):
        if len(with_55) == 13: # 55 + DDD (2) + 9 (1) + 8 digits
            ddd = with_55[2:4]
            local8 = with_55[5:]
            without_9 = f"55{ddd}{local8}"
            variations.extend([without_9, without_9[2:], with_55[2:]])
        elif len(with_55) == 12: # 55 + DDD (2) + 8 digits
            ddd = with_55[2:4]
            local8 = with_55[4:]
            with_9 = f"55{ddd}9{local8}"
            variations.extend([with_9, with_9[2:], with_55[2:]])
            
    last8 = digits[-8:] if len(digits) >= 8 else digits
    placeholders = ",".join("?" for _ in variations)
    
    sql = f"""
    SELECT * FROM leads 
    WHERE phone IN ({placeholders}) OR phone LIKE ?
    ORDER BY 
        CASE WHEN status IN ('SENT', 'REPLIED', 'SCHEDULED') THEN 1 ELSE 2 END ASC,
        coalesce(last_message_at, sent_at, created_at) DESC,
        id DESC
    LIMIT 1
    """
    params = list(variations) + [f"%{last8}"]
    lead = conn.execute(sql, params).fetchone()
    return lead

async def generate_sdr_reply(lead: dict, incoming_text: str, conversation_history: list) -> str:
    lead_name = lead.get("name") or "Lead"
    lead_phone = lead.get("phone") or ""
    camp_slug = lead.get("campaign_slug") or "prospeccao"

    camp_name = camp_slug
    camp_cat = "Geral"
    with get_db() as conn:
        camp = conn.execute("SELECT name, category FROM campaigns WHERE slug = ?", (camp_slug,)).fetchone()
        if camp:
            camp_name = camp["name"]
            camp_cat = camp["category"]

    # Google Calendar context
    cal_info = "Horários livres disponíveis nos próximos dias úteis no período da manhã e tarde."
    try:
        proc = await asyncio.create_subprocess_shell(
            "python3 /opt/data/hermes_calendar.py list 3" if os.path.exists("/opt/data/hermes_calendar.py") else "echo agenda",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if stdout:
            out_str = stdout.decode("utf-8", errors="replace").strip()
            if out_str and "Agenda Google" in out_str:
                cal_info = out_str
    except Exception:
        pass

    sent_msg = lead.get("message_sent", "")
    combined_ctx = f"{camp_name} {camp_cat} {sent_msg}".lower()

    if any(k in combined_ctx for k in ("fisioterap", "osteopat", "coluna", "postural", "dor", "dores", "saúde", "saude")):
        persona_role = "assistente virtual de atendimento da clínica de Fisioterapia e Osteopatia em Salto do Lontra"
        persona_goal = (
            "Seu objetivo é acolher o contato com gentileza e empatia, esclarecer dúvidas sobre alívio de dores "
            "(coluna, lombar, pescoço, tensão postural e muscular) e convidá-lo a agendar uma avaliação postural "
            "ou sessão de alívio presencial. Não prescreva remédios; foque no acolhimento de dores e agendamento da avaliação."
        )
        extra_rules = """3. Se o contato perguntou "quem é?", "onde fica?" ou "como funciona?", explique com simpatia que você é da clínica de Fisioterapia e Osteopatia em Salto do Lontra e que estão realizando avaliações posturais e alívio de dores na coluna e rotina de trabalho.
4. Se o contato perguntar valores/preços: informe com simpatia que o valor varia conforme a queixa e avaliação individual, mencione que estão com condições especiais esta semana e pergunte se ele prefere agendar pela manhã ou tarde."""
    elif any(k in combined_ctx for k in ("dentist", "odonto")):
        persona_role = "assistente de atendimento odontológico"
        persona_goal = "Seu objetivo é esclarecer dúvidas com simpatia e agendar uma avaliação odontológica."
        extra_rules = """3. Se o contato perguntou sobre serviços, explique com simpatia os cuidados e convide para uma avaliação.
4. Se perguntar preço, explique que depende da avaliação clínica e convide para agendar um horário."""
    elif any(k in combined_ctx for k in ("professor", "educaç", "educac", "escola", "seed", "bncc")):
        persona_role = "consultor executivo da equipe do Salesio Ninja (especialista em inteligência artificial e assistentes pedagógicos para BNCC no Paraná)"
        persona_goal = "Seu objetivo é demonstrar como professores e gestores economizam mais de 10 horas semanais com IA e agendar um bate-papo rápido de 10 minutos."
        extra_rules = """3. Se o contato perguntou "quem é?" ou "como funciona?", explique em 1 frase o benefício da IA pedagógica e convide para um bate-papo de 10 minutos amanhã."""
    else:
        persona_role = f"assistente de relacionamento da campanha '{camp_name}'"
        persona_goal = f"Seu objetivo é manter uma conversa natural e coerente com a abordagem inicial enviada ('{sent_msg}'), tirar dúvidas e encaminhar para um agendamento ou próximo passo."
        extra_rules = """3. Se o contato perguntar sobre a mensagem, responda com coerência em relação ao que foi enviado e convide para conversar."""

    system_prompt = f"""Você é o {persona_role}.

OBJETIVO DA SUA INTERAÇÃO:
{persona_goal}

CONTEXTO DO CONTATO:
- Nome: {lead_name}
- Telefone: {lead_phone}
- Nicho / Segmento: {camp_name} ({camp_cat})
- Mensagem inicial que enviamos: "{sent_msg}"
- Próximos compromissos na agenda do Salesio:
{cal_info}

REGRAS OBRIGATÓRIAS DE COMUNICAÇÃO:
1. Seja caloroso, empático, natural e muito objetivo, com tom de WhatsApp corporativo brasileiro.
2. MÁXIMO DE 2 A 3 FRASES CURTAS! Proibido textão ou listas quilométricas.
{extra_rules}
5. Se o contato aceitou conversar ou perguntou horários, sugira opções (ex: "Amanhã às 10h ou no início da tarde às 14h ficaria bom para você?").
6. Se o contato confirmou um dia e horário exato (ex: "pode ser amanhã às 15h"), confirme com entusiasmo e informe que o atendimento ou contato será realizado pontualmente nesse horário.
7. Nunca invente promessas absurdas ou técnicas mirabolantes.
8. Use no máximo 1 ou 2 emojis leves (ex: 👋, 😊, ✨).
"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history[-6:]:
        messages.append({
            "role": "user" if msg["role"] == "lead" else "assistant",
            "content": msg["message"]
        })
    messages.append({"role": "user", "content": incoming_text})

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 250
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                reply = data["choices"][0]["message"]["content"].strip()
                if reply:
                    return reply
            else:
                print(f"[Hermes SDR] OpenRouter error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[Hermes SDR] Exceção chamando OpenRouter: {e}")

    # Fallback natural
    return f"Olá {lead_name}! O Salesio Ninja atua com automações e assistentes de IA para simplificar processos e poupar horas da rotina. Teria 10 minutinhos amanhã para uma rápida demonstração prática?"

async def process_lead_inbound_response(lead: dict, incoming_text: str, target_chat_id: str):
    lead_id = lead["id"]
    phone = lead["phone"]
    lead_name = lead.get("name") or "Lead"
    camp_slug = lead.get("campaign_slug") or "prospeccao"
    now_iso = datetime.now().isoformat()
    lower = incoming_text.lower()
    
    target_jid = target_chat_id if ("@" in target_chat_id) else f"{phone}@s.whatsapp.net"

    # 1. OPT-OUT CHECK
    if any(w in lower for w in ("não quero", "nao quero", "pare", "remover", "spam", "stop", "bloquear", "nao tenho interesse", "não tenho interesse", "retire meu", "cancela", "cancelar")):
        with get_db() as conn:
            conn.execute("UPDATE leads SET status = 'OPT_OUT', response = ?, response_at = ? WHERE id = ?", (incoming_text, now_iso, lead_id))
            conn.execute("INSERT OR IGNORE INTO blacklist (phone, reason, created_at) VALUES (?, ?, ?)", (phone, "Opt-out solicitado", now_iso))
            conn.execute("""
            INSERT INTO conversation_messages (lead_id, lead_phone, role, message, created_at)
            VALUES (?, ?, 'lead', ?, ?)
            """, (lead_id, phone, incoming_text, now_iso))
            conn.commit()

        exit_msg = "Entendido! Peço desculpas pelo incômodo e seu contato já foi removido da nossa lista. Desejo muito sucesso e um ótimo dia!"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(f"{BRIDGE_URL}/send", json={"chatId": target_jid, "message": exit_msg})
                await client.post(f"{BRIDGE_URL}/send", json={
                    "chatId": f"{OWNER_PHONE}@s.whatsapp.net",
                    "message": f"🚫 *LEAD REMOVIDO (OPT-OUT):*\n👤 {lead_name} (+{phone})\n💬 Disse: \"{incoming_text}\""
                })
        except Exception as e:
            print(f"[Hermes SDR] Erro ao enviar opt-out: {e}")
        return

    # 2. Record lead message and update last_message_at
    with get_db() as conn:
        state_rows = conn.execute("SELECT key, value FROM system_state").fetchall()
        state = {r["key"]: r["value"] for r in state_rows}
        auto_reply = state.get("ai_auto_reply", "1") == "1"

        conn.execute("""
        INSERT INTO conversation_messages (lead_id, lead_phone, role, message, created_at)
        VALUES (?, ?, 'lead', ?, ?)
        """, (lead_id, phone, incoming_text, now_iso))
        conn.execute("UPDATE leads SET last_message_at = ? WHERE id = ?", (now_iso, lead_id))
        
        # Check if Human Takeover is active for this lead
        lead_row = conn.execute("SELECT human_takeover FROM leads WHERE id = ?", (lead_id,)).fetchone()
        is_human_takeover = lead_row and lead_row["human_takeover"] == 1

        history = conn.execute("""
        SELECT role, message FROM conversation_messages 
        WHERE lead_id = ? ORDER BY id ASC LIMIT 10
        """, (lead_id,)).fetchall()
        history_list = [{"role": r["role"], "message": r["message"]} for r in history]
        conn.commit()

    # Broadcast lead message to SSE Live Chat
    await broadcast_chat_event("new_message", {
        "lead_id": lead_id,
        "phone": phone,
        "role": "lead",
        "message": incoming_text,
        "created_at": now_iso
    })

    if is_human_takeover:
        print(f"[Hermes SDR] Lead #{lead_id} ({phone}) sob atendimento humano. IA pausada.")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(f"{BRIDGE_URL}/send", json={
                    "chatId": f"{OWNER_PHONE}@s.whatsapp.net",
                    "message": f"👤 *LEAD EM ATENDIMENTO MANUAL FALOU!*\n\n👤 *Contato:* {lead_name} (+{phone})\n💬 *Disse:* \"{incoming_text}\"\n\n👉 *Responda no Painel:* https://hermes.acessaronline.com.br/painel/"
                })
        except Exception:
            pass
        return

    if not auto_reply:
        print(f"[Hermes SDR] AI Auto Reply pausado. Notificando dono...")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(f"{BRIDGE_URL}/send", json={
                    "chatId": f"{OWNER_PHONE}@s.whatsapp.net",
                    "message": f"🔥 *NOVO LEAD RESPONDEU (Auto-Reply Pausado):*\n👤 {lead_name} (+{phone})\n💬 Disse: \"{incoming_text}\""
                })
        except Exception:
            pass
        return

    # 3. Generate AI SDR reply
    print(f"[Hermes SDR] Gerando resposta inteligente para lead #{lead_id} ({phone})...")
    ai_reply = await generate_sdr_reply(lead, incoming_text, history_list)

    # 4. Simulate human typing (3.5 to 6.0 seconds) and broadcast status
    await broadcast_chat_event("typing_status", {"lead_id": lead_id, "phone": phone, "status": "typing"})
    async with httpx.AsyncClient(timeout=25.0) as client:
        try:
            await client.post(f"{BRIDGE_URL}/typing", json={"chatId": target_jid, "presence": "composing"})
            await asyncio.sleep(random.uniform(3.5, 6.0))
            await client.post(f"{BRIDGE_URL}/typing", json={"chatId": target_jid, "presence": "paused"})
        except Exception as e:
            print(f"[Hermes SDR] Typing aviso: {e}")
        finally:
            await broadcast_chat_event("typing_status", {"lead_id": lead_id, "phone": phone, "status": "idle"})

        # Send response to lead
        res = await client.post(f"{BRIDGE_URL}/send", json={"chatId": target_jid, "message": ai_reply})
        if res.status_code != 200:
            print(f"[Hermes SDR] Falha ao enviar resposta IA: {res.text}")

    now_reply_iso = datetime.now().isoformat()
    is_schedule = any(w in lower for w in ("marcar", "agendar", "reunião", "reuniao", "horário", "horario", "amanhã", "amanha", "quinta", "sexta", "às", "as ", "pode ser", "vamos"))
    new_status = "SCHEDULED" if is_schedule else "REPLIED"

    with get_db() as conn:
        conn.execute("""
        UPDATE leads 
        SET status = ?, response = ?, response_at = ? 
        WHERE id = ?
        """, (new_status, incoming_text, now_iso, lead_id))
        conn.execute("""
        INSERT INTO conversation_messages (lead_id, lead_phone, role, message, created_at)
        VALUES (?, ?, 'assistant', ?, ?)
        """, (lead_id, phone, ai_reply, now_reply_iso))
        conn.execute("""
        INSERT INTO dispatch_logs (lead_phone, campaign_slug, action, status, details, timestamp)
        VALUES (?, ?, 'AI_SDR_REPLY', 'SUCCESS', ?, ?)
        """, (phone, camp_slug, f"Lead: {incoming_text} | Hermes: {ai_reply}", now_reply_iso))
        conn.execute("UPDATE leads SET last_message_at = ? WHERE id = ?", (now_reply_iso, lead_id))
        conn.commit()

    # Broadcast AI reply to SSE Live Chat
    await broadcast_chat_event("new_message", {
        "lead_id": lead_id,
        "phone": phone,
        "role": "assistant",
        "message": ai_reply,
        "content": ai_reply,
        "created_at": now_reply_iso
    })

    # 5. Alert Salesio Ninja on WhatsApp
    status_header = "📅 *LEAD INTERESSADO EM AGENDAR!*" if is_schedule else "🔥 *HERMES SDR CONVERSANDO COM LEAD!*"
    alert_msg = (
        f"{status_header}\n\n"
        f"👤 *Contato:* {lead_name} (+{phone})\n"
        f"🎯 *Campanha:* {camp_slug}\n"
        f"💬 *Lead disse:* \"{incoming_text}\"\n"
        f"🤖 *Hermes respondeu:* \"{ai_reply}\"\n\n"
        f"📊 *Status:* {new_status}\n"
        f"🔗 *Painel:* https://hermes.acessaronline.com.br/painel/"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{BRIDGE_URL}/send", json={
                "chatId": f"{OWNER_PHONE}@s.whatsapp.net",
                "message": alert_msg
            })
    except Exception as e:
        print(f"[Hermes SDR] Erro ao notificar Salesio: {e}")

class IncomingWebhook(BaseModel):
    chatId: str
    senderNumber: Optional[str] = None
    senderId: Optional[str] = None
    text: str
    timestamp: Optional[int] = None

@app.post("/painel/api/webhook/incoming")
async def incoming_reply(wh: IncomingWebhook, background_tasks: BackgroundTasks):
    text = wh.text.strip()
    if not text:
        return {"ignored": True, "reason": "empty_text"}

    with get_db() as conn:
        lead = find_lead_by_phone(conn, wh.senderNumber or "")
        if not lead and wh.chatId:
            lead = find_lead_by_phone(conn, wh.chatId)
        if not lead and wh.senderId:
            lead = find_lead_by_phone(conn, wh.senderId)

        if not lead:
            print(f"[Hermes SDR] Webhook recebido de contato não-lead: {wh.senderNumber} / {wh.chatId}")
            return {"ignored": True, "reason": "not_an_sdr_lead"}

        lead_dict = dict(lead)

    # Process conversational reply asynchronously in background
    background_tasks.add_task(process_lead_inbound_response, lead_dict, text, wh.chatId)
    return {"status": "processing", "lead_id": lead_dict["id"], "phone": lead_dict["phone"]}

@app.get("/painel/api/lead-conversation/{lead_id}")
async def get_lead_conversation(lead_id: int):
    with get_db() as conn:
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead não encontrado")
        messages = conn.execute(
            "SELECT * FROM conversation_messages WHERE lead_id = ? ORDER BY id ASC",
            (lead_id,)
        ).fetchall()
        return {
            "lead": dict(lead),
            "messages": [dict(m) for m in messages]
        }

# -------------------------------------------------------------
# Live Chat & Real-Time Copilot Endpoints
# -------------------------------------------------------------
@app.get("/painel/api/chat/stream")
async def chat_stream():
    """Server-Sent Events (SSE) endpoint for real-time live chat streaming."""
    q = asyncio.Queue()
    active_sse_clients.append(q)
    
    async def event_generator():
        try:
            yield "event: connected\ndata: {\"status\": \"connected\"}\n\n"
            while True:
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield frame
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in active_sse_clients:
                active_sse_clients.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/painel/api/chat/conversations")
async def get_chat_conversations(search: Optional[str] = None, filter_type: Optional[str] = "all"):
    """Lists leads with conversation activity for the Live Chat sidebar."""
    init_db()
    with get_db() as conn:
        query = """
        SELECT l.*, 
               (SELECT message FROM conversation_messages WHERE lead_id = l.id ORDER BY id DESC LIMIT 1) as last_msg,
               (SELECT role FROM conversation_messages WHERE lead_id = l.id ORDER BY id DESC LIMIT 1) as last_role,
               (SELECT created_at FROM conversation_messages WHERE lead_id = l.id ORDER BY id DESC LIMIT 1) as last_msg_at,
               (SELECT COUNT(*) FROM conversation_messages WHERE lead_id = l.id) as msg_count
        FROM leads l
        WHERE l.status IN ('SENT', 'REPLIED', 'SCHEDULED', 'OPT_OUT') 
           OR l.id IN (SELECT DISTINCT lead_id FROM conversation_messages)
        """
        params = []
        if search:
            query += " AND (l.phone LIKE ? OR l.name LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
            
        if filter_type == "replied":
            query += " AND l.status IN ('REPLIED', 'SCHEDULED')"
        elif filter_type == "scheduled":
            query += " AND l.status = 'SCHEDULED'"
        elif filter_type == "human":
            query += " AND l.human_takeover = 1"
            
        query += " ORDER BY COALESCE(last_msg_at, l.sent_at) DESC LIMIT 150"
        
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["last_message"] = d.get("last_msg") or ""
            result.append(d)
        return {"conversations": result}

@app.get("/painel/api/chat/messages/{lead_id}")
async def get_chat_messages(lead_id: int):
    """Fetches full chronological chat history for a selected lead."""
    init_db()
    with get_db() as conn:
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead não encontrado")
            
        msgs = conn.execute(
            "SELECT * FROM conversation_messages WHERE lead_id = ? ORDER BY id ASC",
            (lead_id,)
        ).fetchall()
        messages = []
        for m in msgs:
            d = dict(m)
            d["content"] = d.get("message") or ""
            messages.append(d)
        
        # Fallback if lead was messaged before conversation_messages table existed
        if not messages and lead["message_sent"]:
            messages.append({
                "id": 0,
                "lead_id": lead["id"],
                "lead_phone": lead["phone"],
                "role": "outbound",
                "message": lead["message_sent"],
                "created_at": lead["sent_at"] or datetime.now().isoformat()
            })
            if lead["response"]:
                messages.append({
                    "id": 1,
                    "lead_id": lead["id"],
                    "lead_phone": lead["phone"],
                    "role": "lead",
                    "message": lead["response"],
                    "created_at": lead["response_at"] or datetime.now().isoformat()
                })

        return {
            "lead": dict(lead),
            "messages": messages
        }

class HumanSendRequest(BaseModel):
    lead_id: int
    message: str

@app.post("/painel/api/chat/send-human")
async def send_human_message(req: HumanSendRequest):
    """Allows Salesio Ninja (human operator) to send a direct WhatsApp message from the panel and pause AI."""
    init_db()
    msg_text = req.message.strip()
    if not msg_text:
        raise HTTPException(status_code=400, detail="Mensagem vazia")

    with get_db() as conn:
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", (req.lead_id,)).fetchone()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead não encontrado")

        phone = lead["phone"]
        target_jid = f"{phone}@s.whatsapp.net"
        now_iso = datetime.now().isoformat()

        # Send via WhatsApp bridge
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(f"{BRIDGE_URL}/send", json={
                    "chatId": target_jid,
                    "message": msg_text
                })
                if res.status_code != 200:
                    raise HTTPException(status_code=500, detail=f"Erro no WhatsApp: {res.text}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Falha de conexão com WhatsApp: {e}")

        # Set human_takeover = 1 and record message
        conn.execute("""
        UPDATE leads 
        SET human_takeover = 1, last_message_at = ?
        WHERE id = ?
        """, (now_iso, req.lead_id))
        
        conn.execute("""
        INSERT INTO conversation_messages (lead_id, lead_phone, role, message, created_at)
        VALUES (?, ?, 'human', ?, ?)
        """, (req.lead_id, phone, msg_text, now_iso))
        
        conn.execute("""
        INSERT INTO dispatch_logs (lead_phone, campaign_slug, action, status, details, timestamp)
        VALUES (?, ?, 'HUMAN_MESSAGE', 'SUCCESS', ?, ?)
        """, (phone, lead["campaign_slug"], msg_text, now_iso))
        conn.commit()

    # Broadcast event to SSE
    event_data = {
        "lead_id": req.lead_id,
        "phone": phone,
        "role": "human",
        "message": msg_text,
        "created_at": now_iso
    }
    await broadcast_chat_event("new_message", event_data)

    return {"success": True, "message": event_data}

class TakeoverRequest(BaseModel):
    lead_id: int
    human_takeover: bool

@app.post("/painel/api/chat/toggle-takeover")
async def toggle_takeover(req: TakeoverRequest):
    """Toggles human takeover (1) or returns control to Hermes AI (0)."""
    init_db()
    with get_db() as conn:
        val = 1 if req.human_takeover else 0
        conn.execute("UPDATE leads SET human_takeover = ? WHERE id = ?", (val, req.lead_id))
        conn.commit()

    await broadcast_chat_event("takeover_updated", {
        "lead_id": req.lead_id,
        "human_takeover": val
    })
    return {"success": True, "human_takeover": val}

# -------------------------------------------------------------
# Lead Hunter Endpoints (Google Maps, CNPJ, Instagram)
# -------------------------------------------------------------

# -------------------------------------------------------------
# Semantic Search Expansion & Niche Synonyms Dictionary
# -------------------------------------------------------------
NICHE_SYNONYMS = {
    'fisioterapia': [
        'Fisioterapia', 'Pilates', 'Fisioterapeuta', 'Clinica de Fisioterapia', 
        'Studio de Pilates', 'Osteopatia', 'RPG Fisioterapia', 'Reabilitacao'
    ],
    'pilates': [
        'Pilates', 'Studio de Pilates', 'Fisioterapia', 'Fisioterapeuta'
    ],
    'odonto': [
        'Dentista', 'Clinica Odontologica', 'Consultorio Odontologico', 'Ortodontia', 'Odontologia'
    ],
    'dentista': [
        'Dentista', 'Clinica Odontologica', 'Consultorio Odontologico', 'Ortodontia', 'Odontologia'
    ],
    'odontologia': [
        'Dentista', 'Clinica Odontologica', 'Consultorio Odontologico', 'Ortodontia', 'Odontologia'
    ],
    'academia': [
        'Academia', 'Crossfit', 'Treinamento Funcional', 'Studio Fitness', 'Musculacao'
    ],
    'fitness': [
        'Academia', 'Crossfit', 'Treinamento Funcional', 'Studio Fitness'
    ],
    'estetica': [
        'Clinica de Estetica', 'Esteticista', 'Salao de Beleza', 'Espaco de Beleza', 'Biomedicina Estetica'
    ],
    'beleza': [
        'Salao de Beleza', 'Clinica de Estetica', 'Espaco de Beleza', 'Cabeleireiro'
    ],
    'psicologia': [
        'Psicologo', 'Psicologa', 'Clinica de Psicologia', 'Consultorio de Psicologia'
    ],
    'psicologo': [
        'Psicologo', 'Psicologa', 'Clinica de Psicologia', 'Consultorio de Psicologia'
    ],
    'veterinaria': [
        'Clinica Veterinaria', 'Veterinario', 'Hospital Veterinaria', 'Pet Shop'
    ],
    'pet': [
        'Pet Shop', 'Clinica Veterinaria', 'Banho e Tosa'
    ],
    'advogado': [
        'Advogado', 'Escritorio de Advocacia', 'Advocacia', 'Advogada'
    ],
    'advocacia': [
        'Advogado', 'Escritorio de Advocacia', 'Advocacia', 'Advogada'
    ],
    'imobiliaria': [
        'Imobiliaria', 'Corretor de Imoveis', 'Imoveis'
    ],
    'contabilidade': [
        'Escritorio de Contabilidade', 'Contador', 'Contabilidade'
    ],
    'escola': [
        'Escola', 'Colegio', 'Educacao Infantil', 'Centro Educacional'
    ],
    'mecanica': [
        'Oficina Mecanica', 'Auto Center', 'Auto Eletrica', 'Centro Automotivo'
    ],
    'medica': [
        'Clinica Medica', 'Consultorio Medico', 'Policlinica', 'Centro Medico'
    ],
    'medico': [
        'Clinica Medica', 'Consultorio Medico', 'Policlinica', 'Centro Medico'
    ]
}


INCOMPATIBLE_CATEGORIES = {
    'odonto': ['fisioterapia', 'fisioterapeuta', 'pilates', 'rpg', 'osteopatia', 'estetica', 'salao de beleza', 'cabeleireiro', 'manicure', 'barbearia', 'mecanica', 'oficina', 'auto', 'advocac', 'advogad', 'veterin', 'pet', 'ginecolog', 'obstetric', 'pediatra', 'restaurante', 'imobiliaria', 'contabil', 'contabilidade', 'otica', 'farmacia', 'academia', 'musculacao'],
    'dentista': ['fisioterapia', 'fisioterapeuta', 'pilates', 'rpg', 'osteopatia', 'estetica', 'salao de beleza', 'cabeleireiro', 'manicure', 'barbearia', 'mecanica', 'oficina', 'auto', 'advocac', 'advogad', 'veterin', 'pet', 'ginecolog', 'obstetric', 'pediatra', 'restaurante', 'imobiliaria', 'contabil', 'contabilidade', 'otica', 'farmacia', 'academia', 'musculacao'],
    'odontologia': ['fisioterapia', 'fisioterapeuta', 'pilates', 'rpg', 'osteopatia', 'estetica', 'salao de beleza', 'cabeleireiro', 'manicure', 'barbearia', 'mecanica', 'oficina', 'auto', 'advocac', 'advogad', 'veterin', 'pet', 'ginecolog', 'obstetric', 'pediatra', 'restaurante', 'imobiliaria', 'contabil', 'contabilidade', 'otica', 'farmacia', 'academia', 'musculacao'],
    'fisioterapia': ['odonto', 'dentista', 'ortodont', 'mecanica', 'oficina', 'auto', 'advocac', 'advogad', 'veterin', 'pet', 'salao de beleza', 'cabeleireiro', 'barbearia', 'restaurante', 'imobiliaria', 'contabil', 'contabilidade', 'otica', 'farmacia'],
    'pilates': ['odonto', 'dentista', 'ortodont', 'mecanica', 'oficina', 'auto', 'advocac', 'advogad', 'veterin', 'pet', 'salao de beleza', 'cabeleireiro', 'barbearia', 'restaurante', 'imobiliaria', 'contabil', 'contabilidade', 'otica', 'farmacia'],
    'advogado': ['odonto', 'dentista', 'fisioterapia', 'pilates', 'mecanica', 'oficina', 'auto', 'salao', 'estetica', 'veterin', 'pet', 'restaurante', 'medico', 'clinica', 'escola'],
    'advocacia': ['odonto', 'dentista', 'fisioterapia', 'pilates', 'mecanica', 'oficina', 'auto', 'salao', 'estetica', 'veterin', 'pet', 'restaurante', 'medico', 'clinica', 'escola'],
    'mecanica': ['odonto', 'dentista', 'fisioterapia', 'advocac', 'salao', 'estetica', 'veterin', 'restaurante', 'medico', 'clinica'],
    'imobiliaria': ['odonto', 'dentista', 'fisioterapia', 'advocac', 'salao', 'estetica', 'mecanica', 'oficina', 'veterin', 'restaurante'],
    'veterinaria': ['odonto', 'dentista', 'fisioterapia', 'advocac', 'salao', 'estetica', 'mecanica', 'oficina', 'restaurante'],
    'pet': ['odonto', 'dentista', 'fisioterapia', 'advocac', 'salao', 'estetica', 'mecanica', 'oficina', 'restaurante']
}

def normalize_text_simple(text: str) -> str:
    nfkd = unicodedata.normalize('NFKD', (text or '').lower())
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).strip()

def calculate_relevance(title: str, category: str, default_niche: str) -> tuple[str, int]:
    norm_n = normalize_text_simple(default_niche)
    norm_t = normalize_text_simple(title)
    norm_c = normalize_text_simple(category)
    
    # 1. Termos positivos (sinonimos do nicho pesquisado)
    terms = [t for t in re.split(r'[\s,/]+', norm_n) if len(t) > 3]
    for key, syns in NICHE_SYNONYMS.items():
        if key in norm_n:
            terms.extend([normalize_text_simple(s) for s in syns])
            
    terms = list(set(terms))
    has_positive = any(term in norm_t or term in norm_c for term in terms)

    # 2. Termos incompativeis (outros ramos que o Google Maps tenta empurrar)
    negative_terms = []
    for key, negs in INCOMPATIBLE_CATEGORIES.items():
        if key in norm_n:
            negative_terms.extend([normalize_text_simple(ng) for ng in negs])
    negative_terms = list(set(negative_terms))

    has_negative = any(neg in norm_c or neg in norm_t for neg in negative_terms)

    if has_positive and not has_negative:
        return 'high', 100
    elif has_positive and has_negative:
        # Ex.: Clinica Integrada Odonto e Fisio
        return 'medium', 70
    elif has_negative:
        # Incompativel evidente (ex.: Fisioterapia em busca de Dentista)
        return 'incompatible', 0
    else:
        broad_indicators = ['clinica', 'consultorio', 'saude', 'centro', 'espaco', 'instituto', 'doutor', 'dra', 'dr', 'studio']
        for ind in broad_indicators:
            if ind in norm_t or ind in norm_c:
                return 'medium', 50
        return 'broad', 20

def generate_deep_keywords(niche: str, location: str, extra_keywords: str = "", deep_search: bool = True) -> list[str]:
    norm_niche = normalize_text_simple(niche)
    keywords = []
    
    # 1. Termo direto
    keywords.append(f"{niche} em {location}")
    keywords.append(f"{niche} {location}")
    
    if deep_search:
        matched_synonyms = []
        for key, syns in NICHE_SYNONYMS.items():
            if key in norm_niche:
                matched_synonyms.extend(syns)
                
        if not matched_synonyms:
            if not norm_niche.startswith('clinica'):
                matched_synonyms.append(f"Clinica de {niche}")
            matched_synonyms.append(niche)
            
        for syn in matched_synonyms:
            kw = f"{syn} em {location}"
            if kw not in keywords:
                keywords.append(kw)
            if len(keywords) >= 5:
                break
                
    if extra_keywords:
        for extra in extra_keywords.split(','):
            extra = extra.strip()
            if extra:
                kw = f"{extra} em {location}"
                if kw not in keywords:
                    keywords.append(kw)

    return keywords[:6]

class HunterSearchRequest(BaseModel):
    source: str = 'maps'  # 'maps', 'cnpj', 'instagram', 'ninja'
    niche: str
    location: str
    limit: int = 25
    deep_search: bool = True
    extra_keywords: Optional[str] = None

class HunterImportRequest(BaseModel):
    campaign_slug: str
    campaign_name: Optional[str] = None
    leads: List[dict]

def parse_ninja_csv_leads(csv_text: str, default_city: str = "", default_niche: str = "") -> List[dict]:
    cleaned_leads = []
    seen_phones = set()
    seen_names = set()
    init_db()
    with get_db() as conn:
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            title = (row.get('title') or '').strip()
            if not title:
                continue
            raw_phone = (row.get('phone') or '').strip()
            digits = re.sub(r'\D', '', raw_phone)
            if (len(digits) == 10 or len(digits) == 11) and not digits.startswith('55'):
                digits = '55' + digits

            norm_title = "".join(c for c in normalize_text_simple(title) if c.isalnum())
            if digits and digits in seen_phones:
                continue
            if norm_title and norm_title in seen_names:
                continue

            if digits:
                seen_phones.add(digits)
            if norm_title:
                seen_names.add(norm_title)

            address = (row.get('complete_address') or row.get('address') or '').strip()
            website = (row.get('website') or '').strip()
            rating = (row.get('review_rating') or '').strip()
            review_count = (row.get('review_count') or '').strip()
            category = (row.get('category') or default_niche or 'Comércio Local').strip()

            city = default_city
            if not city and address:
                parts = address.split(' - ')
                if len(parts) >= 2:
                    city = parts[-2].strip()

            details_parts = []
            if address:
                details_parts.append(address)
            if website:
                details_parts.append(f"Site: {website}")
            if rating:
                details_parts.append(f"Nota: {rating} ({review_count} avaliações)")
            details = " | ".join(details_parts)

            exists = False
            if digits:
                row_db = conn.execute('SELECT id FROM leads WHERE phone = ? LIMIT 1', (digits,)).fetchone()
                if row_db:
                    exists = True

            rel_level, rel_score = calculate_relevance(title, category, default_niche)

            is_strict = (rel_level in ('high', 'medium') and rel_level != 'incompatible')
            cleaned_leads.append({
                'name': title,
                'phone': digits,
                'raw_phone': raw_phone,
                'city': city or default_city or 'Local',
                'state': 'PR',
                'niche': category,
                'source': 'GOOGLE MAPS (NINJA)',
                'details': details,
                'website': website,
                'rating': rating,
                'review_count': review_count,
                'address': address,
                'already_in_db': exists,
                'valid_phone': len(digits) in (12, 13),
                'relevance': rel_level,
                'relevance_score': rel_score,
                'is_strict_match': is_strict
            })
    cleaned_leads.sort(key=lambda x: (x['relevance_score'], 1 if x['valid_phone'] else 0), reverse=True)
    return cleaned_leads

@app.get('/painel/api/hunter/ninja/jobs')
async def hunter_ninja_jobs():
    '''Fetches list of historical scraping jobs from Scraper Ninja.'''
    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            res = await client.get(f"{SCRAPER_NINJA_URL}/api/v1/jobs")
            if res.status_code == 200:
                jobs = res.json()
                if isinstance(jobs, list):
                    jobs.sort(key=lambda x: x.get('Date', ''), reverse=True)
                return {'jobs': jobs}
    except Exception as e:
        print(f"[Lead Hunter] Erro ao listar jobs ninja: {e}")
    return {'jobs': []}

@app.get('/painel/api/hunter/ninja/job/{job_id}/leads')
async def hunter_ninja_job_leads(job_id: str):
    '''Downloads and parses leads from an existing Scraper Ninja job.'''
    try:
        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            info_res = await client.get(f"{SCRAPER_NINJA_URL}/api/v1/jobs/{job_id}")
            job_name = ""
            if info_res.status_code == 200:
                job_name = info_res.json().get('Name', '')

            csv_res = await client.get(f"{SCRAPER_NINJA_URL}/api/v1/jobs/{job_id}/download?format=csv")
            if csv_res.status_code != 200:
                raise HTTPException(status_code=404, detail="Resultados do job não disponíveis ou não encontrados")

            default_niche = ""
            default_city = ""
            if "🎯" in job_name:
                parts = job_name.split("🎯", 1)[1].strip()
                if "(" in parts and ")" in parts:
                    default_niche = parts.split("(", 1)[0].strip()
                    default_city = parts.split("(", 1)[1].split(")", 1)[0].strip()
            elif "Hermes" in job_name and "(" in job_name and ")" in job_name:
                parts = job_name.split("Hermes", 1)[1].strip()
                default_niche = parts.split("(", 1)[0].replace("🎯", "").strip()
                default_city = parts.split("(", 1)[1].split(")", 1)[0].strip()

            leads = parse_ninja_csv_leads(csv_res.text, default_city=default_city, default_niche=default_niche)
            return {
                'leads': leads,
                'total': len(leads),
                'job_id': job_id,
                'job_name': job_name,
                'niche': default_niche,
                'location': default_city,
                'source': 'GOOGLE MAPS (NINJA)'
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar leads do job: {e}")

@app.post('/painel/api/hunter/search')
async def hunter_search(req: HunterSearchRequest):
    '''Searches for real leads across Google Maps (via native Scraper Ninja) or CNPJ / Instagram (via AI web search).'''
    niche = req.niche.strip()
    location = req.location.strip()
    if not niche or not location:
        raise HTTPException(status_code=400, detail='Nicho e Localização são obrigatórios')

    # 1. GOOGLE MAPS via Native Scraper Ninja
    if req.source in ('maps', 'ninja'):
        keywords = generate_deep_keywords(
            niche=niche,
            location=location,
            extra_keywords=req.extra_keywords or "",
            deep_search=req.deep_search
        )
        depth = 80 if req.deep_search else min(max(req.limit, 15), 40)
        job_name = f"Hermes 🎯 {niche} ({location})" + (" [Deep]" if req.deep_search else "")
        payload = {
            'name': job_name,
            'keywords': keywords,
            'lang': 'pt',
            'depth': depth,
            'fast_mode': False,
            'email': False,
            'max_time': 180
        }

        try:
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                create_res = await client.post(
                    f"{SCRAPER_NINJA_URL}/api/v1/jobs",
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                )
                if create_res.status_code not in (200, 201):
                    raise HTTPException(status_code=500, detail=f"Erro ao iniciar busca no Scraper Ninja: {create_res.text}")

                job_id = create_res.json().get('id')
                if not job_id:
                    raise HTTPException(status_code=500, detail="ID de job inválido retornado pelo Scraper Ninja")

                # Poll for completion (up to ~125 seconds)
                completed = False
                for _ in range(50):
                    await asyncio.sleep(2.5)
                    status_res = await client.get(f"{SCRAPER_NINJA_URL}/api/v1/jobs/{job_id}")
                    if status_res.status_code == 200:
                        st = status_res.json().get('Status')
                        if st == 'ok':
                            completed = True
                            break
                        elif st in ('failed', 'error'):
                            raise HTTPException(status_code=500, detail="Scraper Ninja reportou falha na extração")

                if not completed:
                    return {
                        'leads': [],
                        'total': 0,
                        'source': 'GOOGLE MAPS (NINJA)',
                        'query': ", ".join(keywords),
                        'job_id': job_id,
                        'status': 'working',
                        'message': f"O robô Scraper Ninja ainda está minerando no Google Maps (Job ID: {job_id}). Você pode carregar o resultado na aba 'Jobs Anteriores' em instantes."
                    }

                # Download and parse CSV
                csv_res = await client.get(f"{SCRAPER_NINJA_URL}/api/v1/jobs/{job_id}/download?format=csv")
                if csv_res.status_code != 200:
                    raise HTTPException(status_code=500, detail="Erro ao baixar resultados do Scraper Ninja")

                cleaned_leads = parse_ninja_csv_leads(csv_res.text, default_city=location, default_niche=niche)
                return {
                    'leads': cleaned_leads,
                    'total': len(cleaned_leads),
                    'source': 'GOOGLE MAPS (NINJA)',
                    'query': ", ".join(keywords),
                    'keywords_used': keywords,
                    'deep_search': req.deep_search,
                    'job_id': job_id,
                    'status': 'ok'
                }
        except HTTPException:
            raise
        except Exception as e:
            print(f"[Lead Hunter - Ninja] Erro: {e}")
            raise HTTPException(status_code=500, detail=f"Falha de comunicação com o Scraper Ninja: {e}")

    # 2. AI WEB SCAN FOR CNPJ & INSTAGRAM
    api_key = os.environ.get('OPENROUTER_API_KEY', '')
    if not api_key:
        raise HTTPException(status_code=500, detail='OPENROUTER_API_KEY não configurada no servidor')

    source_instructions = {
        'cnpj': f"Encontre empresas abertas, dados comerciais e telefones cadastrados do segmento '{niche}' na região '{location}'.",
        'instagram': f"Encontre perfis comerciais no Instagram e negócios de '{niche}' em '{location}' que tenham telefone ou WhatsApp de contato público divulgado na bio ou em links."
    }
    instruction = source_instructions.get(req.source, source_instructions['cnpj'])
    prompt = (
        f"{instruction}\n"
        f"Encontre até {req.limit} contatos comerciais reais.\n"
        "Retorne EXCLUSIVAMENTE um array JSON puro (sem markdown, sem explicações):\n"
        "[\n"
        "  {\n"
        "    \"name\": \"Nome da Empresa ou Perfil\",\n"
        "    \"phone\": \"5546999999999\",\n"
        f"    \"city\": \"{location}\",\n"
        f"    \"niche\": \"{niche}\",\n"
        f"    \"source\": \"{req.source.upper()}\",\n"
        "    \"details\": \"Endereço, @perfil ou observação\"\n"
        "  }\n"
        "]"
    )

    found_leads = []
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            res = await client.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'perplexity/sonar',
                    'messages': [
                        {'role': 'system', 'content': 'Você é um robô minerador de leads comerciais especialista no Brasil. Seu objetivo é extrair dados reais e telefones para WhatsApp. Responda APENAS o JSON puro com os leads encontrados.'},
                        {'role': 'user', 'content': prompt}
                    ],
                    'temperature': 0.2
                }
            )
            if res.status_code == 200:
                data = res.json()
                raw_text = data['choices'][0]['message']['content'].strip()
                if raw_text.startswith('```'):
                    raw_text = re.sub(r'^```[a-z]*\n?', '', raw_text)
                    raw_text = re.sub(r'```$', '', raw_text).strip()
                parsed = json.loads(raw_text)
                if isinstance(parsed, list):
                    found_leads = parsed
            else:
                print(f'[Lead Hunter] Erro API: {res.text}')
    except Exception as e:
        print(f'[Lead Hunter] Erro na busca IA: {e}')

    cleaned_leads = []
    init_db()
    with get_db() as conn:
        for item in found_leads:
            name = item.get('name', '').strip()
            raw_phone = item.get('phone', '')
            digits = re.sub(r'\D', '', raw_phone)
            if (len(digits) == 10 or len(digits) == 11) and not digits.startswith('55'):
                digits = '55' + digits

            exists = False
            if digits:
                row = conn.execute('SELECT id FROM leads WHERE phone = ? LIMIT 1', (digits,)).fetchone()
                if row:
                    exists = True

            cleaned_leads.append({
                'name': name,
                'phone': digits,
                'city': item.get('city') or location,
                'state': item.get('state', 'PR'),
                'niche': item.get('niche') or niche,
                'source': item.get('source') or req.source.upper(),
                'details': item.get('details', ''),
                'already_in_db': exists,
                'valid_phone': len(digits) in (12, 13)
            })

    return {
        'leads': cleaned_leads,
        'total': len(cleaned_leads),
        'source': req.source,
        'query': f'{niche} em {location}'
    }

@app.post('/painel/api/hunter/import')
async def hunter_import(req: HunterImportRequest):
    '''Imports selected hunter leads into a specified SDR campaign.'''
    slug = req.campaign_slug.strip() if req.campaign_slug else 'lotes_hunter_captacao'
    leads = req.leads
    if not leads:
        raise HTTPException(status_code=400, detail='Nenhum lead selecionado para importar')

    now_iso = datetime.now().isoformat()
    init_db()
    imported = 0
    duplicates = 0

    with get_db() as conn:
        camp = conn.execute('SELECT id FROM campaigns WHERE slug = ?', (slug,)).fetchone()
        if not camp:
            name = req.campaign_name or f'Captação Hunter: {slug.replace("_", " ").title()}'
            conn.execute('''
            INSERT OR IGNORE INTO campaigns 
            (slug, name, category, source_folder, message_template, created_at)
            VALUES (?, ?, 'Lead Hunter', 'hunter', ?, ?)
            ''', (slug, name, '{Olá|Oi}{nome}, tudo bem? Aqui é o Salesio. Vi seu contato na nossa rede de negócios.', now_iso))

        for item in leads:
            raw_phone = item.get('phone', '')
            digits = re.sub(r'\D', '', str(raw_phone))
            if not digits:
                continue
            if len(digits) in (10, 11) and not digits.startswith("55"):
                digits = "55" + digits

            name = item.get('name', '').strip()
            city = item.get('city', '').strip()
            niche = item.get('niche', '').strip()
            details = item.get('details', '')
            if isinstance(details, (dict, list)):
                import json
                details_str = json.dumps(details, ensure_ascii=False)
            else:
                details_str = str(details)

            category = niche or 'Lead Hunter'

            try:
                conn.execute('''
                INSERT INTO leads (campaign_slug, phone, name, category, city, niche, details, source_file, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'scraper_ninja', 'PENDING', ?)
                ''', (slug, digits, name, category, city, niche, details_str, now_iso))
                imported += 1
            except sqlite3.IntegrityError:
                duplicates += 1
            except Exception as ex:
                print(f"Erro inserindo lead {digits}: {ex}")

        conn.commit()

        # Also save physical CSV file on VPS in DOWNLOADS_DIR/lotes_hunter/
        try:
            hunter_backup_dir = os.path.join(DOWNLOADS_DIR, "lotes_hunter")
            os.makedirs(hunter_backup_dir, exist_ok=True)
            camp_filename = f"{slug}.csv"
            backup_csv_path = os.path.join(hunter_backup_dir, camp_filename)
            with open(backup_csv_path, "w", newline="", encoding="utf-8-sig") as bf:
                w = csv.writer(bf, delimiter=";")
                w.writerow(["Nome da Empresa / Profissional", "WhatsApp (Disparo 55+DDD+9)", "Telefone Formatado", "Nicho", "Cidade", "Endereco"])
                for item in leads:
                    p = re.sub(r'\D', '', str(item.get('phone', '')))
                    if len(p) in (10, 11) and not p.startswith("55"):
                        p = "55" + p
                    fmt_p = f"+55 ({p[2:4]}) {p[4:9]}-{p[9:]}" if len(p) == 13 else (f"+55 ({p[2:4]}) {p[4:8]}-{p[8:]}" if len(p) == 12 else p)
                    w.writerow([
                        item.get('name', ''),
                        f'="{p}"',
                        fmt_p,
                        item.get('niche', ''),
                        item.get('city', ''),
                        str(item.get('details', ''))
                    ])
        except Exception as ex_b:
            print(f"Erro salvando backup CSV: {ex_b}")

    return {'success': True, 'imported': imported, 'duplicates': duplicates}

# -------------------------------------------------------------
# Frontend Dashboard HTML
# -------------------------------------------------------------
HTML_DASHBOARD_PATH = os.path.join(DATA_DIR, "sdr_ui", "index.html")

@app.api_route("/painel", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/painel/", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/sdr", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/sdr/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def serve_dashboard():
    if os.path.exists(HTML_DASHBOARD_PATH):
        with open(HTML_DASHBOARD_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Hermes SDR Dashboard carregando...</h2>")

if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)
