import urllib.request
import re
import html as html_lib
import time
import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# 42 Municipalities of DDD 46 (Sudoeste do Paraná)
CITIES = [
    ("ampere-pr", "Ampére"),
    ("barracao-pr", "Barracão"),
    ("bela-vista-da-caroba-pr", "Bela Vista da Caroba"),
    ("boa-esperanca-do-iguacu-pr", "Boa Esperança do Iguaçu"),
    ("bom-jesus-do-sul-pr", "Bom Jesus do Sul"),
    ("bom-sucesso-do-sul-pr", "Bom Sucesso do Sul"),
    ("capanema-pr", "Capanema"),
    ("chopinzinho-pr", "Chopinzinho"),
    ("clevelandia-pr", "Clevelândia"),
    ("coronel-domingos-soares-pr", "Coronel Domingos Soares"),
    ("coronel-vivida-pr", "Coronel Vivida"),
    ("cruzeiro-do-iguacu-pr", "Cruzeiro do Iguaçu"),
    ("dois-vizinhos-pr", "Dois Vizinhos"),
    ("eneas-marques-pr", "Enéas Marques"),
    ("flor-da-serra-do-sul-pr", "Flor da Serra do Sul"),
    ("francisco-beltrao-pr", "Francisco Beltrão"),
    ("honorio-serpa-pr", "Honório Serpa"),
    ("itapejara-do-oeste-pr", "Itapejara d'Oeste"),
    ("manfrinopolis-pr", "Manfrinópolis"),
    ("mangueirinha-pr", "Mangueirinha"),
    ("mariopolis-pr", "Mariópolis"),
    ("marmeleiro-pr", "Marmeleiro"),
    ("nova-esperanca-do-sudoeste-pr", "Nova Esperança do Sudoeste"),
    ("nova-prata-do-iguacu-pr", "Nova Prata do Iguaçu"),
    ("palmas-pr", "Palmas"),
    ("pato-branco-pr", "Pato Branco"),
    ("perola-do-oeste-pr", "Pérola d'Oeste"),
    ("pinhal-de-sao-bento-pr", "Pinhal de São Bento"),
    ("planalto-pr", "Planalto"),
    ("pranchita-pr", "Pranchita"),
    ("realeza-pr", "Realeza"),
    ("renascenca-pr", "Renascença"),
    ("salgado-filho-pr", "Salgado Filho"),
    ("salto-do-lontra-pr", "Salto do Lontra"),
    ("santa-isabel-do-oeste-pr", "Santa Isabel do Oeste"),
    ("santo-antonio-do-sudoeste-pr", "Santo Antônio do Sudoeste"),
    ("sao-joao-pr", "São João"),
    ("sao-jorge-do-oeste-pr", "São Jorge d'Oeste"),
    ("saudade-do-iguacu-pr", "Saudade do Iguaçu"),
    ("sulina-pr", "Sulina"),
    ("vere-pr", "Verê"),
    ("vitorino-pr", "Vitorino")
]

CITY_PAGES = {
    'francisco-beltrao-pr': 273, 'pato-branco-pr': 217, 'dois-vizinhos-pr': 95,
    'palmas-pr': 52, 'realeza-pr': 48, 'marmeleiro-pr': 47, 'ampere-pr': 39,
    'chopinzinho-pr': 34, 'santo-antonio-do-sudoeste-pr': 34, 'coronel-vivida-pr': 33,
    'capanema-pr': 29, 'mangueirinha-pr': 22, 'barracao-pr': 20, 'clevelandia-pr': 20,
    'salto-do-lontra-pr': 20, 'sao-joao-pr': 18, 'planalto-pr': 17, 'santa-isabel-do-oeste-pr': 17,
    'itapejara-do-oeste-pr': 15, 'nova-prata-do-iguacu-pr': 12, 'pranchita-pr': 11,
    'renascenca-pr': 11, 'sao-jorge-do-oeste-pr': 9, 'vere-pr': 9, 'vitorino-pr': 9,
    'perola-do-oeste-pr': 7, 'eneas-marques-pr': 6, 'mariopolis-pr': 6,
    'flor-da-serra-do-sul-pr': 5, 'nova-esperanca-do-sudoeste-pr': 5, 'saudade-do-iguacu-pr': 5,
    'salgado-filho-pr': 4, 'bom-sucesso-do-sul-pr': 3, 'cruzeiro-do-iguacu-pr': 3,
    'honorio-serpa-pr': 3, 'sulina-pr': 3, 'bela-vista-da-caroba-pr': 2,
    'boa-esperanca-do-iguacu-pr': 2, 'bom-jesus-do-sul-pr': 2, 'coronel-domingos-soares-pr': 2,
    'manfrinopolis-pr': 2, 'pinhal-de-sao-bento-pr': 1
}

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_lib.unescape(text)
    return ' '.join(text.split()).strip()

def fetch_url(url, retries=3):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                return resp.read().decode('cp1252', errors='replace')
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return None

def parse_page(html, city_name):
    leads = []
    if not html:
        return leads

    pos = html.find('id="div_results"')
    if pos != -1:
        chunk = html[pos:]
        pag_pos = chunk.find('class="pagination"')
        if pag_pos != -1:
            chunk = chunk[:pag_pos]
    else:
        chunk = html

    blocks = re.split(r'<div\s+class=[\"\']row\s+[^\"\']*resultado[^\"\']*[\"\']', chunk)
    for b in blocks[1:]:
        slug_m = re.search(r'contato/([0-9]{10,11}-[^\"\'\)\s]+)', b)
        if not slug_m:
            continue
        slug = slug_m.group(1)
        phone_raw = slug.split('-')[0]

        # Name
        name_m = re.search(r'class=[\"\'][^\"\']*nome(?:cliente|par|impar|normal)[^\"\']*[\"\'][^>]*>(.*?)</div>', b, re.DOTALL)
        name = clean_text(name_m.group(1)) if name_m else ""
        if not name:
            span_m = re.search(r'<span>(.*?)</span>\s*<a\s+href=[\"\']https?://g123\.com\.br/contato', b, re.DOTALL)
            if span_m:
                name = clean_text(span_m.group(1))
        if not name:
            parts = slug.split('-')
            name = ' '.join(parts[1:parts.index('pr') if 'pr' in parts else len(parts)]).title()

        # Category
        ramo_m = re.search(r'/ramos-de-atividades/([^/\"\'\?#]+)', b)
        ramo = ramo_m.group(1).replace('-', ' ').title() if ramo_m else ""

        # Address
        end_m = re.search(r'class=[\"\'][^\"\']*endereco[^\"\']*[\"\'][^>]*>(.*?)</div>', b, re.DOTALL)
        endereco = clean_text(end_m.group(1)) if end_m else ""

        # City from card or fallback
        city_m = re.search(r'class=[\"\'][^\"\']*cidadebase[^\"\']*[\"\'][^>]*>(.*?)</div>', b, re.DOTALL)
        cidade_str = clean_text(city_m.group(1)) if city_m else f"{city_name} - PR"
        if " - " in cidade_str:
            cidade_nome = cidade_str.split(" - ")[0].strip()
        else:
            cidade_nome = cidade_str.strip()

        # Is cell phone (11 digits, starts with 469)
        is_cell = len(phone_raw) == 11 and phone_raw.startswith("469")
        has_wpp = "whatsapp" in b.lower() or is_cell

        # Format phone
        if len(phone_raw) == 11:
            phone_fmt = f"({phone_raw[:2]}) {phone_raw[2:7]}-{phone_raw[7:]}"
        elif len(phone_raw) == 10:
            phone_fmt = f"({phone_raw[:2]}) {phone_raw[2:6]}-{phone_raw[6:]}"
        else:
            phone_fmt = phone_raw

        leads.append({
            "nome": name,
            "telefone": phone_fmt,
            "numero_limpo": phone_raw,
            "tipo": "Celular / WhatsApp" if is_cell else "Fixo",
            "whatsapp": "Sim" if (is_cell or has_wpp) else "Não",
            "cidade": cidade_nome,
            "estado": "PR",
            "categoria": ramo,
            "endereco": endereco,
            "link": f"https://g123.com.br/contato/{slug}"
        })
    return leads

def main():
    print("=" * 70)
    print("  ROBÔ EXTRATOR GUIASCHNELL - REGIÃO 46 (SUDOESTE DO PARANÁ)")
    print("=" * 70)

    # Build queue of all URLs
    tasks = []
    for slug, name in CITIES:
        pages = CITY_PAGES.get(slug, 1)
        for p in range(1, pages + 1):
            url = f"https://g123.com.br/listas/{slug}" if p == 1 else f"https://g123.com.br/listas/{slug}/pagina-{p}"
            tasks.append((url, name, slug, p, pages))

    total_tasks = len(tasks)
    print(f"Total de tarefas: {total_tasks} páginas em {len(CITIES)} municípios do DDD 46.")
    print("Iniciando varredura com 12 conexões paralelas...\n")

    t_start = time.time()
    all_raw_leads = []
    completed = 0

    with ThreadPoolExecutor(max_workers=12) as executor:
        future_to_task = {executor.submit(fetch_url, t[0]): t for t in tasks}
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            url, city_name, slug, p, total_p = task
            completed += 1
            try:
                html = future.result()
                if html:
                    page_leads = parse_page(html, city_name)
                    all_raw_leads.extend(page_leads)
            except Exception as e:
                pass

            if completed % 100 == 0 or completed == total_tasks:
                elapsed = time.time() - t_start
                rate = completed / elapsed if elapsed > 0 else 0
                print(f"[{completed:4d}/{total_tasks}] Páginas processadas ({completed*100//total_tasks}%). Leads brutos coletados: {len(all_raw_leads):5d} | {rate:.1f} págs/s")

    elapsed_total = time.time() - t_start
    print("\n" + "=" * 70)
    print(f"Varredura concluída em {elapsed_total:.1f} segundos!")
    print(f"Total de registros brutos extraídos: {len(all_raw_leads)}")

    # Deduplication by phone number
    unique_all = {}
    for l in all_raw_leads:
        num = l['numero_limpo']
        if num not in unique_all:
            unique_all[num] = l
        else:
            existing = unique_all[num]
            if not existing['categoria'] and l['categoria']:
                existing['categoria'] = l['categoria']
            if len(l['nome']) > len(existing['nome']):
                existing['nome'] = l['nome']
            if not existing['endereco'] and l['endereco']:
                existing['endereco'] = l['endereco']

    leads_unicos = list(unique_all.values())
    leads_whatsapp = [l for l in leads_unicos if l['tipo'] == "Celular / WhatsApp"]
    leads_fixo = [l for l in leads_unicos if l['tipo'] == "Fixo"]

    print(f"Total de contatos ÚNICOS: {len(leads_unicos)}")
    print(f"  -> Celulares / WhatsApp válidos (DDD 46): {len(leads_whatsapp)}")
    print(f"  -> Telefones fixos (DDD 46): {len(leads_fixo)}")

    # Sort alphabetically by City then Name
    leads_whatsapp.sort(key=lambda x: (x['cidade'], x['nome']))
    leads_unicos.sort(key=lambda x: (x['cidade'], x['nome']))

    # 1. Export Excel/CSV with BOM (utf-8-sig) and semicolon delimiter (Standard BR)
    csv_whatsapp_path = r"c:\++TUDO SOBRE O HERMES\leads_whatsapp_ddd46.csv"
    with open(csv_whatsapp_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "Nome da Empresa / Profissional",
            "Telefone / WhatsApp",
            "Número Limpo",
            "WhatsApp",
            "Cidade",
            "Estado",
            "Ramo / Categoria",
            "Endereço",
            "Link no Guia"
        ])
        for l in leads_whatsapp:
            writer.writerow([
                l['nome'],
                l['telefone'],
                l['numero_limpo'],
                l['whatsapp'],
                l['cidade'],
                l['estado'],
                l['categoria'],
                l['endereco'],
                l['link']
            ])
    print(f"\n[OK] Arquivo principal de WhatsApp salvo em:\n  -> {csv_whatsapp_path}")

    # 2. Export All (Cell + Landline)
    csv_todos_path = r"c:\++TUDO SOBRE O HERMES\leads_todos_ddd46.csv"
    with open(csv_todos_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "Nome da Empresa / Profissional",
            "Telefone / WhatsApp",
            "Número Limpo",
            "Tipo",
            "WhatsApp",
            "Cidade",
            "Estado",
            "Ramo / Categoria",
            "Endereço",
            "Link no Guia"
        ])
        for l in leads_unicos:
            writer.writerow([
                l['nome'],
                l['telefone'],
                l['numero_limpo'],
                l['tipo'],
                l['whatsapp'],
                l['cidade'],
                l['estado'],
                l['categoria'],
                l['endereco'],
                l['link']
            ])
    print(f"[OK] Arquivo completo (Celular + Fixo) salvo em:\n  -> {csv_todos_path}")

    # Summary by city
    cidade_counts = {}
    for l in leads_whatsapp:
        cidade_counts[l['cidade']] = cidade_counts.get(l['cidade'], 0) + 1

    print("\n--- Resumo de Celulares/WhatsApp por Cidade ---")
    for cid, count in sorted(cidade_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"  {cid:<30}: {count:>5} números de WhatsApp")
    if len(cidade_counts) > 15:
        print(f"  ... e mais {len(cidade_counts) - 15} cidades!")

if __name__ == "__main__":
    main()
