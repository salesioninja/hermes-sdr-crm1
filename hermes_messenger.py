#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hermes_messenger.py - Módulo Executivo de Envio e Agendamento de Mensagens WhatsApp
Hermes Agent & Antigravity
"""

import sys
import os
import re
import json
import sqlite3
import argparse
import urllib.request
import urllib.error
import time
from datetime import datetime, timedelta, timezone

# -----------------------------------------------------------------------------
# Configurações de Fuso Horário e Caminhos
# -----------------------------------------------------------------------------
TZ_BR = timezone(timedelta(hours=-3))

def get_db_path():
    candidates = [
        "/opt/data/campaigns.db",
        "/opt/hermes-agent/data/campaigns.db",
        os.path.join(os.path.dirname(__file__), "campaigns.db"),
        "campaigns.db"
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]

def get_bridge_url():
    candidates = [
        os.environ.get("WHATSAPP_BRIDGE_URL", ""),
        "http://127.0.0.1:3000",
        "http://hermes:3000",
        "http://localhost:3000"
    ]
    for url in candidates:
        if not url:
            continue
        try:
            req = urllib.request.Request(f"{url}/health", headers={"User-Agent": "HermesMessenger/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    return url
        except Exception:
            pass
    return "http://127.0.0.1:3000"

# -----------------------------------------------------------------------------
# Normalização de Telefone (Padrão BR 55 + DDD + 9 Dígitos)
# -----------------------------------------------------------------------------
def normalize_phone(raw: str) -> str:
    digits = re.sub(r'\D', '', str(raw or ''))
    if not digits:
        return ''
    if not digits.startswith('55'):
        if len(digits) in (10, 11):
            digits = '55' + digits
    if digits.startswith('55') and len(digits) == 12:
        ddd = digits[2:4]
        rest = digits[4:]
        digits = f"55{ddd}9{rest}"
    return digits

# -----------------------------------------------------------------------------
# Parser de Horário em Linguagem Natural Brasileira
# -----------------------------------------------------------------------------
def parse_schedule_time(s: str) -> datetime:
    s = s.strip().lower()
    now = datetime.now(TZ_BR)

    # 1. "em X minutos" ou "em X horas"
    m_rel = re.search(r'em\s+(\d+)\s*(min|minuto|m|hora|h)', s)
    if m_rel:
        val = int(m_rel.group(1))
        unit = m_rel.group(2)
        if 'h' in unit:
            return now + timedelta(hours=val)
        return now + timedelta(minutes=val)

    # 2. "HH:MM" ou "HHhMM" ou "HHh" ou "HH"
    m_time = re.search(r'(\d{1,2})(?:[:h](\d{2})?|h|\s*horas?|\s*hrs?)?', s)
    is_tomorrow = 'amanha' in s or 'amanhã' in s

    if m_time:
        hour = int(m_time.group(1))
        minute = int(m_time.group(2)) if m_time.group(2) else 0
        if 'e meia' in s or 'e 30' in s:
            minute = 30
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if is_tomorrow:
            target += timedelta(days=1)
        elif target <= now and 'hoje' not in s:
            target += timedelta(days=1)
        return target

    # 3. Fallback: ISO format
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_BR)
        return dt
    except Exception:
        return now + timedelta(minutes=5)

# -----------------------------------------------------------------------------
# Banco de Dados
# -----------------------------------------------------------------------------
def init_db(conn):
    c = conn.cursor()
    c.execute("""
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
    conn.commit()

# -----------------------------------------------------------------------------
# Envio via Bridge WhatsApp
# -----------------------------------------------------------------------------
def send_whatsapp_direct(phone: str, text: str, bridge_url: str = None) -> bool:
    if not bridge_url:
        bridge_url = get_bridge_url()

    target_jid = f"{phone}@s.whatsapp.net"

    # Simulação de digitação (presence: composing)
    try:
        req_type = urllib.request.Request(
            f"{bridge_url}/typing",
            data=json.dumps({"chatId": target_jid, "presence": "composing"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req_type, timeout=3.0)
        time.sleep(2.0)
        req_type_pause = urllib.request.Request(
            f"{bridge_url}/typing",
            data=json.dumps({"chatId": target_jid, "presence": "paused"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req_type_pause, timeout=3.0)
    except Exception:
        pass

    # Disparo oficial
    req_send = urllib.request.Request(
        f"{bridge_url}/send",
        data=json.dumps({"chatId": target_jid, "message": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req_send, timeout=10.0) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[Hermes Messenger] Erro no envio via bridge: {e}", file=sys.stderr)
        return False

# -----------------------------------------------------------------------------
# Ações CLI
# -----------------------------------------------------------------------------
def cmd_send(args):
    phone = normalize_phone(args.phone)
    if not phone or len(phone) < 10:
        print(json.dumps({"status": "ERROR", "message": "Número de telefone inválido."}))
        return 1

    text = args.message.strip()
    if not text:
        print(json.dumps({"status": "ERROR", "message": "Mensagem não pode ser vazia."}))
        return 1

    bridge = get_bridge_url()
    success = send_whatsapp_direct(phone, text, bridge)

    db_path = get_db_path()
    try:
        with sqlite3.connect(db_path) as conn:
            init_db(conn)
            now_iso = datetime.now().isoformat()
            # Registra lead se não existir
            conn.execute("""
            INSERT OR IGNORE INTO leads (campaign_slug, phone, name, category, source_file, status, created_at, message_sent, sent_at)
            VALUES ('lotes_manual_test', ?, ?, 'Manual', 'whatsapp_cli', 'SENT', ?, ?, ?)
            """, (phone, args.name or 'Contato WhatsApp', now_iso, text, now_iso))
            # Registra mensagem na conversa
            lead_id = conn.execute("SELECT id FROM leads WHERE phone = ? ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
            if lead_id:
                conn.execute("""
                INSERT INTO conversation_messages (lead_id, lead_phone, role, message, created_at)
                VALUES (?, ?, 'assistant', ?, ?)
                """, (lead_id[0], phone, text, now_iso))
                conn.execute("UPDATE leads SET last_message_at = ?, message_sent = ? WHERE id = ?", (now_iso, text, lead_id[0]))
            conn.execute("""
            INSERT INTO dispatch_logs (lead_phone, campaign_slug, action, status, details, timestamp)
            VALUES (?, 'lotes_manual_test', 'WHATSAPP_EXEC_SENT', ?, ?, ?)
            """, (phone, 'SUCCESS' if success else 'FAILED', text, now_iso))
            conn.commit()
    except Exception as e:
        print(f"[Hermes Messenger] Aviso ao gravar banco: {e}", file=sys.stderr)

    if success:
        out = {
            "status": "SUCCESS",
            "phone": phone,
            "name": args.name or "Contato",
            "message": text,
            "delivered_at": datetime.now(TZ_BR).strftime("%d/%m/%Y %H:%M:%S")
        }
        print(f"✅ MENSAGEM ENVIADA COM SUCESSO!\n📱 Para: +{phone}\n💬 Texto: \"{text}\"")
        return 0
    else:
        print(f"❌ FALHA NO ENVIO para +{phone}. Verifique a conexão do WhatsApp Bridge.")
        return 1

def cmd_schedule(args):
    phone = normalize_phone(args.phone)
    if not phone or len(phone) < 10:
        print(json.dumps({"status": "ERROR", "message": "Número de telefone inválido."}))
        return 1

    text = args.message.strip()
    if not text:
        print(json.dumps({"status": "ERROR", "message": "Mensagem não pode ser vazia."}))
        return 1

    dt_target = parse_schedule_time(args.at)
    dt_utc = dt_target.astimezone(timezone.utc)
    utc_iso = dt_utc.isoformat()
    local_str = dt_target.strftime("%d/%m/%Y às %H:%M")

    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        init_db(conn)
        now_iso = datetime.now(timezone.utc).isoformat()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO scheduled_dispatches (phone, lead_name, message, scheduled_for, status, created_at)
        VALUES (?, ?, ?, ?, 'PENDING', ?)
        """, (phone, args.name or 'Contato', text, utc_iso, now_iso))
        disp_id = cur.lastrowid
        conn.commit()

    print(f"⏰ MENSAGEM AGENDADA COM SUCESSO! [ID: #{disp_id}]\n📱 Para: +{phone}\n🕐 Agendada para: {local_str}\n💬 Mensagem: \"{text}\"")
    return 0

def cmd_list(args):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute("""
        SELECT id, phone, lead_name, message, scheduled_for, status 
        FROM scheduled_dispatches 
        WHERE status = 'PENDING' 
        ORDER BY scheduled_for ASC
        """).fetchall()

    if not rows:
        print("📭 Nenhuma mensagem agendada no momento.")
        return 0

    print(f"📋 MENSAGENS AGENDADAS PENDENTES ({len(rows)}):")
    for r in rows:
        try:
            dt_utc = datetime.fromisoformat(r[4])
            dt_local = dt_utc.astimezone(TZ_BR).strftime("%d/%m/%Y %H:%M")
        except Exception:
            dt_local = r[4]
        preview = r[3][:45] + "..." if len(r[3]) > 45 else r[3]
        print(f"• [ID #{r[0]}] 📱 +{r[1]} ({r[2] or 'Contato'}) | ⏰ {dt_local} | \"{preview}\"")
    return 0

def cmd_cancel(args):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        init_db(conn)
        conn.execute("UPDATE scheduled_dispatches SET status = 'CANCELLED' WHERE id = ?", (args.id,))
        conn.commit()
    print(f"🚫 Mensagem agendada ID #{args.id} foi cancelada.")
    return 0

def cmd_run_pending(args):
    db_path = get_db_path()
    now_utc_iso = datetime.now(timezone.utc).isoformat()
    owner_phone = os.environ.get("OWNER_PHONE", "5546999765576")

    with sqlite3.connect(db_path) as conn:
        init_db(conn)
        pending = conn.execute("""
        SELECT id, phone, lead_name, message, scheduled_for 
        FROM scheduled_dispatches 
        WHERE status = 'PENDING' AND scheduled_for <= ?
        ORDER BY scheduled_for ASC
        """, (now_utc_iso,)).fetchall()

        if not pending:
            return 0

        bridge = get_bridge_url()
        sent_count = 0

        for item in pending:
            disp_id, phone, name, msg, sched_for = item
            success = send_whatsapp_direct(phone, msg, bridge)
            now_sent = datetime.now(timezone.utc).isoformat()

            if success:
                conn.execute("UPDATE scheduled_dispatches SET status = 'SENT', sent_at = ? WHERE id = ?", (now_sent, disp_id))
                sent_count += 1

                # Notifica o Dono no WhatsApp
                try:
                    time_br = datetime.now(TZ_BR).strftime("%H:%M")
                    notify_text = (
                        f"⏰ *HERMES: MENSAGEM AGENDADA ENTREGUE!*\n\n"
                        f"👤 *Destinatário:* {name or 'Contato'} (+{phone})\n"
                        f"🕐 *Entregue às:* {time_br}\n"
                        f"💬 *Mensagem enviada:*\n\"{msg}\""
                    )
                    send_whatsapp_direct(owner_phone, notify_text, bridge)
                except Exception:
                    pass
            else:
                conn.execute("UPDATE scheduled_dispatches SET status = 'FAILED', error = 'Bridge error' WHERE id = ?", (disp_id,))

        conn.commit()
        print(f"Executados {sent_count}/{len(pending)} envios agendados.")
    return 0

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Hermes Messenger CLI")
    subparsers = parser.add_subparsers(dest="command")

    # send
    p_send = subparsers.add_parser("send", help="Envia mensagem imediatamente")
    p_send.add_argument("phone", help="Número de telefone do destinatário")
    p_send.add_argument("message", help="Texto da mensagem a enviar")
    p_send.add_argument("--name", default="", help="Nome do contato (opcional)")

    # schedule
    p_sched = subparsers.add_parser("schedule", help="Agenda envio para data/horário")
    p_sched.add_argument("phone", help="Número de telefone do destinatário")
    p_sched.add_argument("message", help="Texto da mensagem a enviar")
    p_sched.add_argument("at", help="Horário de agendamento (ex: 19:00, 'amanha 10:00', 'em 30 minutos')")
    p_sched.add_argument("--name", default="", help="Nome do contato (opcional)")

    # list
    subparsers.add_parser("list", help="Lista mensagens agendadas pendentes")

    # cancel
    p_canc = subparsers.add_parser("cancel", help="Cancela mensagem agendada por ID")
    p_canc.add_argument("id", type=int, help="ID da mensagem agendada")

    # run-pending
    subparsers.add_parser("run-pending", help="Processa e envia mensagens que atingiram o horário")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    if args.command == "send":
        return cmd_send(args)
    elif args.command == "schedule":
        return cmd_schedule(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "cancel":
        return cmd_cancel(args)
    elif args.command == "run-pending":
        return cmd_run_pending(args)
    return 0

if __name__ == "__main__":
    sys.exit(main())
