import csv
import os
import re
import unicodedata
from collections import defaultdict

BASE_DIR = r"c:\++TUDO SOBRE O HERMES\LEADS_POR_CIDADE"
INPUT_CSV = r"c:\++TUDO SOBRE O HERMES\leads_whatsapp_ddd46.csv"

# Category inference patterns for empty categories
PATTERNS = [
    (r'\b(advocaci|advogad|juridic)', 'Advocacias E Advogados'),
    (r'\b(fisioterap|pilates|osteopat)', 'Fisioterapia E Pilates'),
    (r'\b(dentist|odontolog|odonto)\b', 'Dentistas E Clinicas Odontologicas'),
    (r'\b(mecanic|auto\s*center|oficina)\b', 'Mecanica De Automoveis'),
    (r'\b(auto\s*pecas|autopecas)\b', 'Auto Pecas'),
    (r'\b(chapeac|funilari)', 'Chapeacao E Pintura'),
    (r'\b(lavacar|lava\s*car|estetica\s*automotiva)', 'Lavacar'),
    (r'\b(clinica|medic[ao]s?|pediatr|psicolog|nutri|terapia)\b', 'Clinicas E Medicos'),
    (r'\b(farmaci|drogar)', 'Farmacia'),
    (r'\b(imobiliari|corretor)\b', 'Imobiliaria E Corretor De Imoveis'),
    (r'\b(moveis|marcenari|estofad)', 'Moveis'),
    (r'\b(restaurante|pizzari|churrascari|lanchonete|bar\b|choperi|gastronom)', 'Bares E Restaurantes'),
    (r'\b(mercado|supermercado|merceari)', 'Supermercados E Mercearias'),
    (r'\b(salao|cabeleir|barbeari|estetic)', 'Salao De Beleza E Barbearia'),
    (r'\b(agro|veterinari|pet\s*shop|rac[ao])', 'Agropecuaria E Pet Shop'),
    (r'\b(solar|fotovoltaic)', 'Energia Solar'),
    (r'\b(metalurgic|vidracari|esquadri|calha)', 'Metalurgica E Vidracaria'),
    (r'\b(roupa|confecc|modas?|calcado|boutique)\b', 'Loja De Roupas E Calcados'),
    (r'\b(contabil|contabilidade|assessori)', 'Contabilidade E Assessoria'),
    (r'\b(construc|construtor|materiais\s*p.*construc|engenhar)', 'Construcao Civil'),
    (r'\b(transport|frete|mudanc|guincho|munck)', 'Transportes E Fretes'),
    (r'\b(funerari|pax|plano\s*luto)', 'Funerarias E Planos'),
    (r'\b(fotograf|studio\s*foto|filmagem)', 'Fotografia E Filmagem'),
    (r'\b(informatica|computad|ti|celular|telecom)', 'Informatica E Celulares'),
    (r'\b(hotel|pousada|hospedag)', 'Hoteis E Hospedagem')
]

def infer_category(name):
    lower = name.lower()
    for pat, cat in PATTERNS:
        if re.search(pat, lower):
            return cat
    return 'Comercio E Servicos Gerais'

def clean_slug_filename(name):
    # remove accents
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '_', name)
    return name.strip('_')

def normalize_city_name(city_raw):
    raw = city_raw.strip()
    # Normalize variants
    mapping = {
        "ampere": "Ampére",
        "barracao": "Barracão",
        "bela vista da caroba": "Bela Vista da Caroba",
        "boa esperanca do iguacu": "Boa Esperança do Iguaçu",
        "bom jesus do sul": "Bom Jesus do Sul",
        "bom sucesso do sul": "Bom Sucesso do Sul",
        "capanema": "Capanema",
        "chopinzinho": "Chopinzinho",
        "clevelandia": "Clevelândia",
        "coronel domingos soares": "Coronel Domingos Soares",
        "coronel vivida": "Coronel Vivida",
        "cruzeiro do iguacu": "Cruzeiro do Iguaçu",
        "dois vizinhos": "Dois Vizinhos",
        "eneas marques": "Enéas Marques",
        "flor da serra do sul": "Flor da Serra do Sul",
        "francisco beltrao": "Francisco Beltrão",
        "honorio serpa": "Honório Serpa",
        "itapejara do oeste": "Itapejara d'Oeste",
        "itapejara d'oeste": "Itapejara d'Oeste",
        "manfrinopolis": "Manfrinópolis",
        "mangueirinha": "Mangueirinha",
        "mariopolis": "Mariópolis",
        "marmeleiro": "Marmeleiro",
        "nova esperanca do sudoeste": "Nova Esperança do Sudoeste",
        "nova prata do iguacu": "Nova Prata do Iguaçu",
        "palmas": "Palmas",
        "pato branco": "Pato Branco",
        "perola do oeste": "Pérola d'Oeste",
        "pinhal de sao bento": "Pinhal de São Bento",
        "planalto": "Planalto",
        "pranchita": "Pranchita",
        "realeza": "Realeza",
        "renascenca": "Renascença",
        "salgado filho": "Salgado Filho",
        "salto do lontra": "Salto do Lontra",
        "santa isabel do oeste": "Santa Isabel do Oeste",
        "santa izabel do oeste": "Santa Isabel do Oeste",
        "santo antonio do sudoeste": "Santo Antônio do Sudoeste",
        "saudade do iguacu": "Saudade do Iguaçu",
        "sao joao": "São João",
        "sao jorge do oeste": "São Jorge d'Oeste",
        "sao jorge d'oeste": "São Jorge d'Oeste",
        "sulina": "Sulina",
        "vere": "Verê",
        "vitorino": "Vitorino"
    }
    
    clean_key = unicodedata.normalize('NFKD', raw).encode('ASCII', 'ignore').decode('ASCII').lower()
    clean_key = clean_key.replace("'", "").strip()
    return mapping.get(clean_key, raw)

def main():
    print("=" * 70)
    print("  ORGANIZANDO LEADS POR CIDADE E POR NICHO / CATEGORIA")
    print("=" * 70)

    if not os.path.exists(INPUT_CSV):
        print(f"Erro: Arquivo {INPUT_CSV} não encontrado!")
        return

    os.makedirs(BASE_DIR, exist_ok=True)

    # Read all leads
    leads_by_city_niche = defaultdict(lambda: defaultdict(list))
    city_totals = defaultdict(int)

    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            city_norm = normalize_city_name(row['Cidade'])
            row['Cidade'] = city_norm
            
            cat_raw = row['Ramo / Categoria'].strip()
            if not cat_raw:
                cat_norm = infer_category(row['Nome da Empresa / Profissional'])
            else:
                cat_norm = cat_raw.title()
                
            row['Ramo / Categoria'] = cat_norm

            leads_by_city_niche[city_norm][cat_norm].append(row)
            city_totals[city_norm] += 1

    print(f"Total de cidades identificadas: {len(leads_by_city_niche)}")
    print(f"Diretório raiz de saída: {BASE_DIR}\n")

    header = [
        "Nome da Empresa / Profissional",
        "Telefone / WhatsApp",
        "Número Limpo",
        "WhatsApp",
        "Cidade",
        "Estado",
        "Ramo / Categoria",
        "Endereço",
        "Link no Guia"
    ]

    total_files_created = 0
    resumo_cidades = []

    for city_name, niches in sorted(leads_by_city_niche.items()):
        city_folder_name = clean_slug_filename(city_name)
        city_dir = os.path.join(BASE_DIR, city_folder_name)
        os.makedirs(city_dir, exist_ok=True)

        all_city_leads = []
        for niche_leads in niches.values():
            all_city_leads.extend(niche_leads)

        # Sort leads
        all_city_leads.sort(key=lambda x: (x['Ramo / Categoria'], x['Nome da Empresa / Profissional']))

        # 1. Master file for the city
        master_city_file = os.path.join(city_dir, f"00_TODOS_WHATSAPP_{city_folder_name}.csv")
        with open(master_city_file, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=header, delimiter=";")
            writer.writeheader()
            writer.writerows(all_city_leads)
        total_files_created += 1

        # 2. Individual CSVs per niche
        niche_count = 0
        for niche_name, leads in sorted(niches.items()):
            niche_filename = clean_slug_filename(niche_name) + ".csv"
            niche_file_path = os.path.join(city_dir, niche_filename)
            leads.sort(key=lambda x: x['Nome da Empresa / Profissional'])

            with open(niche_file_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=header, delimiter=";")
                writer.writeheader()
                writer.writerows(leads)
            total_files_created += 1
            niche_count += 1

        resumo_cidades.append({
            "cidade": city_name,
            "pasta": city_folder_name,
            "total_whatsapp": len(all_city_leads),
            "total_nichos": niche_count
        })

    # Save summary CSV
    summary_path = os.path.join(BASE_DIR, "00_INDICE_GERAL_DAS_CIDADES.csv")
    with open(summary_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Cidade", "Nome da Pasta", "Total Contatos WhatsApp", "Total Arquivos de Nichos"])
        for r in sorted(resumo_cidades, key=lambda x: x['total_whatsapp'], reverse=True):
            writer.writerow([r['cidade'], r['pasta'], r['total_whatsapp'], r['total_nichos']])

    print("=" * 70)
    print(f"ORGANIZAÇÃO CONCLUÍDA COM SUCESSO!")
    print(f"-> {len(resumo_cidades)} pastas de cidades criadas.")
    print(f"-> {total_files_created} arquivos CSV separados por categoria gerados.")
    print(f"-> Índice geral salvo em: {summary_path}")
    print("=" * 70)

    print("\nDemonstração das Top 10 cidades organizadas:")
    for r in sorted(resumo_cidades, key=lambda x: x['total_whatsapp'], reverse=True)[:10]:
        print(f"  [PASTA] {r['cidade']:<28} | {r['total_whatsapp']:>5} WhatsApp | {r['total_nichos']:>3} listas por nicho")

if __name__ == "__main__":
    main()
