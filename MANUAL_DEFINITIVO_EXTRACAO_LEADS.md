# 📖 Manual Definitivo: Extração de Leads WhatsApp no Hermes Agent

Este documento descreve a arquitetura, as regras de ouro, os comandos e os procedimentos técnicos utilizados pelo **Hermes Agent** para mapear grupos do WhatsApp e extrair listas de contatos altamente qualificadas, segmentadas e 100% compatíveis com softwares de disparo em massa e com o Microsoft Excel.

---

## 🧭 1. Visão Geral e Arquitetura

O sistema opera na VPS do usuário integrada ao WhatsApp através da biblioteca Baileys v7, rodando em um container Docker Swarm gerenciado pelo Hermes.

```
┌─────────────────────────────────────────────────────────────┐
│                      WHATSAPP DO USUÁRIO                    │
│                 (1.086 Grupos / +54.000 Membros)            │
└──────────────────────────────┬──────────────────────────────┘
                               │ WebSocket Baileys
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    HERMES WHATSAPP BRIDGE                   │
│          /opt/data/scripts/whatsapp-bridge/bridge.js        │
│          /opt/data/scripts/whatsapp-bridge/group_extractor.js│
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼                               ▼
    [ Processamento & Filtros ]     [ Servidor Web de Downloads ]
    - 5 Sub-temas Educacionais       - Nginx Port 80 / HTTPS
    - 3 Nichos de TI Pura           - https://hermes.acessaronline.com.br
    - 1 Nicho Robótica/Computação   - /downloads/lotes_educacao/
    - Desduplicação Global Total     - /downloads/lotes_tecnologia/
    - Regra ANATEL (9º Dígito)      - /downloads/lotes_robotica_computacao/
    - Fatiamento em Máx 500         - Arquivos ZIP Consolidados
```

---

## ⚡ 2. As 4 Regras de Ouro da Extração

Para garantir eficiência máxima nas campanhas e zero dor de cabeça operacional, o extrator segue 4 regras inegociáveis:

### Regra 1: Limite Rígido de 500 Contatos por Lista
* **Motivo:** Disparos no WhatsApp exigem controle de cadência e aquecimento de chip. Listas gigantescas aumentam o risco de bloqueio.
* **Execução:** O sistema divide automaticamente grupos grandes em partes numeradas (`_Parte1.csv`, `_Parte2.csv`, etc.), garantindo que nenhum arquivo ultrapasse 500 leads.

### Regra 2: Desduplicação Global e Separação de Nichos
* **Motivo:** Professores de robótica/computação não devem ser misturados com desenvolvedores de software ou agências de automação.
* **Execução:** O sistema mantém isolamento total entre os nichos e desduplica contatos entre as listas afins.

### Regra 3: Normalização do 9º Dígito (Padrão ANATEL)
* **Motivo:** Contas antigas de WhatsApp (criadas antes de 2016) foram salvas no servidor do WhatsApp sem o nono dígito (com 12 dígitos). Disparadores rejeitam celulares com 12 dígitos.
* **Execução:** O extrator identifica celulares do Brasil de 12 dígitos (onde o primeiro número após o DDD é `6, 7, 8 ou 9`) e insere automaticamente o dígito `9` após o DDD, totalizando os **13 dígitos oficiais da ANATEL** (`55` + DDD + `9` + 8 dígitos).

### Regra 4: Imunidade à Notação Científica do Excel
* **Motivo:** O Excel transforma números com mais de 11 dígitos em notação científica (`5,547E+12`), destruindo os números ao salvar.
* **Execução:**
  - O arquivo CSV é gerado com cabeçalho **UTF-8 BOM (`\uFEFF`)** para manter acentuação correta.
  - Separador oficial: ponto-e-vírgula (`;`).
  - As colunas de telefone são gravadas com fórmula de texto: `="5546999765576"`. O Excel exibe o número limpo, legível e alinhado à esquerda.

---

## 📊 3. Estrutura das Colunas nos Arquivos CSV

| Coluna | Exemplo | Função |
| :--- | :--- | :--- |
| **`whatsapp`** | `="5546999765576"` | **Coluna Principal.** Telefone oficial de 13 dígitos formatado para o Excel e disparadores. |
| **`telefone_original`** | `="554699765576"` | Número original sem o 9º dígito (formatado como texto no Excel). |
| **`nome`** | `Professor(a) de Robótica/Computação` | Nome público do WhatsApp ou tratamento humanizado para personalizar a mensagem. |
| **`grupo_origem`** | `Robótica NRE Maringá - NEM` | Nome do grupo do WhatsApp de onde o lead veio. |
| **`subtema`** | `Robótica e Pensamento Computacional Escolar` | Nome da categoria do lote. |
| **`is_admin`** | `NAO` / `SIM` | Indica se o participante é administrador do grupo. |
| **`ddd`** | `44` | DDD extraído para permitir filtros regionais no Excel. |
| **`data_extracao`** | `29/10/2026` | Data da geração da lista. |

---

## 🎯 4. As 3 Verticais de Leads Mapeadas e Geradas

### 📚 Vertical A: Educação & Professores Gerais (21 Lotes | 9.080 Leads Únicos)
* **Lote 01:** BNCC, Séries Iniciais e Alfabetização *(2 partes | 672 contatos)*
* **Lote 02:** Educação Física e Esportes *(1 parte | 238 contatos)*
* **Lote 03:** Sala de Recursos, Inclusão e Reforço - PMA *(2 partes | 724 contatos)*
* **Lote 04:** Concursos Públicos e PSS SEED-PR / Geral *(10 partes | 4.760 contatos)*
* **Lote 05:** Professores Gerais e Disciplinas do Ensino *(6 partes | 2.686 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_EDUCACAO.zip`

### 💻 Vertical B: Tecnologia Pura & Programação (7 Lotes | 2.613 Leads Únicos)
*(Professores de computação/robótica escolar foram 100% excluídos desta vertical)*
* **Lote Tech 01:** Automação, n8n, Chatbots e Agentes de IA *(4 partes | 1.549 contatos)*
* **Lote Tech 02:** Programadores, Devs, Python e Web3 *(1 parte | 488 contatos)*
* **Lote Tech 03:** IA para Negócios, Marketing e Agências *(2 partes | 576 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_TECNOLOGIA.zip`

### 🤖 Vertical C: Professores de Robótica & Pensamento Computacional (3 Lotes | 1.155 Leads Únicos)
*(Exclusivo para professores da rede escolar que lecionam computação, robótica e IA educativa)*
* **Lote 01:** Robótica e Pensamento Computacional Escolar - Parte 1 *(500 contatos)*
* **Lote 02:** Robótica e Pensamento Computacional Escolar - Parte 2 *(500 contatos)*
* **Lote 03:** Robótica e Pensamento Computacional Escolar - Parte 3 *(155 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_ROBOTICA_COMPUTACAO.zip`

### 🏫 Vertical D: Escolas, Comunidades & Projetos SEED-PR (6 Lotes | 1.834 Leads Únicos)
*(Colégios municipais/estaduais, projetos de vida, recomposição, chamamento e APP sindicato)*
* **Lote 01:** Colégios, Escolas e Comunidades Escolares *(CEIMM, Itaipu, Barra Bonita, Vicente Câmara, Doze, Rio Gavião) (1 parte | 242 contatos)*
* **Lote 02:** Disciplinas e Projetos Pedagógicos SEED-PR *(Recomposição, Projeto de Vida, Scratch, Pensamento Lógico, Português, Portfólio) (3 partes | 1.087 contatos)*
* **Lote 03:** APP Sindicato, Convocados/Chamamento, CEEBJA e NRE Dois Vizinhos *(Elite 1º chamamento, Rede APP Beltrão/Municipais/Salto, CEEBJA, AETEs) (2 partes | 505 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_ESCOLAS_SEED.zip`

### 💼 Vertical E: Negócios, Marketing, Vendas, Afiliados & PLR (10 Lotes | 4.317 Leads Únicos)
*(Empreendedores digitais, afiliados, dropshipping, gestores de tráfego, vendas e investidores)*
* **Lote 01:** PLR, Afiliados, Dropshipping e E-commerce *(PLR Premium, Dropaaqui, Afiliados 50K, Sócio WOM, WeDrop) (4 partes | 1.911 contatos)*
* **Lote 02:** Marketing Digital, Tráfego Pago, Vendas e Lançamentos *(Members Pro, Vendas de Aplicativos, Alerta Clone, Gestão e Vendas) (2 partes | 614 contatos)*
* **Lote 03:** Empreendedorismo, Renda Online, Investimentos e Revenda *(Empreendedorismo PR, Renda Online News, Revenda Sistemas, Curitiba Investimentos, Negócios Exponenciais) (4 partes | 1.792 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_NEGOCIOS.zip`

### 🚗 Vertical F: Regional Paraná & Caronas (9 Lotes | 3.727 Leads Únicos)
*(Caronas intermunicipais, briks e desapegos regionais, cidadania e debates do Paraná)*
* **Lote 01:** Caronas Paraná (Sudoeste, Oeste, Central e Curitiba) *(Caronas DV-Pato, LDS x Gpuava, Foz x Cvel/Toledo, Beltrão x Capanema, Urbano 46) (4 partes | 1.793 contatos)*
* **Lote 02:** Briks, Bazares, Desapegos e Comércio Regional *(Salto do Lontra Mil Grauuu, Desapegos Salto, Bricks DV, Beltrão Brikis, Bazar DV) (2 partes | 847 contatos)*
* **Lote 03:** Cidadania, Notícias, Debates e Esportes Paraná *(Fala Beltrão Debate Político, Gazeta do Povo PR, Funcis PR, Circuito Xadrez, Muay Thai) (3 partes | 1.087 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_REGIONAL_CARONAS.zip`

### ✈️ Vertical G: Turismo, Viagens & Milhas (4 Lotes | 1.269 Leads Únicos)
*(Viajantes, clientes de agências, alunos de turismo, emissores de passagens e milheiros)*
* **Lote 01:** Agências de Turismo, Excursões e Pacotes de Viagem *(Claudia Sousa Turismo, Fenicio's Tur, Comunidade Claudia Sousa, Viacapi, Olitur) (2 partes | 664 contatos)*
* **Lote 02:** Milhas Aéreas, Emissão de Voos, Passagens e Tarifas *(GoFly Tarifas Ocultas, Alertas de Passagens, Estevam pelo Mundo, Norton Milhas, Erik Galdino) (2 partes | 605 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_TURISMO_MILHAS.zip`

### 💼 Vertical H: Empregos, Vagas & Oportunidades (2 Lotes | 894 Leads Únicos)
*(Candidatos a empregos, grupos de recrutamento, seleções de vagas e oportunidades profissionais)*
* **Lote 01:** Vagas de Emprego, Recrutamento e Canais Regionais *(JobsPRO Sistema de Vagas, 21 e 92 Empregos na Bahia, Guincho 24h Vagas) (1 parte | 477 contatos)*
* **Lote 02:** Oportunidades de Crescimento e Vagas Abertas *(T5K Vagas Abertas, Oportunidades de Crescimento, Novas Oportunidades, Últimas Vagas) (1 parte | 417 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_EMPREGOS_VAGAS.zip`

### 🩺 Vertical I: Saúde, Terapia, Estética & Bem-Estar (2 Lotes | 181 Leads Únicos)
*(Praticantes de pilates, fisioterapia, emagrecimento, reiki, aromaterapia dōTerra/Charoma e saúde integrativa)*
* **Lote 01:** Pilates, Fisioterapia, Estética e Emagrecimento *(Elô Pilates, Treino Monstro, Cross Pilates CVEL, Dicas de Emagrecimento, Muay Thai) (1 parte | 56 contatos)*
* **Lote 02:** Terapias Integrativas, Aromaterapia e Saúde Natural *(Ozonteck Dream Team, DTX HND SETA Saúde, Charoma Time Diamantes, Terapia Reiki, dōTerra) (1 parte | 125 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_SAUDE_BEMESTAR.zip`

### 🎓 Vertical J: Ensino Superior, Pós-Graduação & Cursos (3 Lotes | 699 Leads Únicos)
*(Alunos de pós-graduação, segunda licenciatura UNIBF/ENPEX e docentes do Programa Mais Aprendizagem Paraná)*
* **Lote 01:** Pós-Graduação, Ensino Superior e Licenciaturas (UNIBF & ENPEX) *(Matrículas-Pós ENPEX, GRUPO ZUSE - UNIBF Semipresencial, Zuse Pós e Segunda Licenciatura) (2 partes | 621 contatos)*
* **Lote 02:** Programa Mais Aprendizagem Paraná *(SEED-PR / Apoio Pedagógico e Tutoria Escolar) (1 parte | 78 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_POS_GRADUACAO.zip`

### 💎 Vertical K: MMN, Vendas Diretas, Lançamentos & Infoprodutos (5 Lotes | 2.087 Leads Únicos)
*(Líderes de marketing multinível, consultores de vendas diretas e alunos de lançamentos digitais)*
* **Lote 01:** Marketing Multinível, Vendas Diretas e Liderança (Bonifica, Luci Luci, Hinode, Battistoni, White Club, GoBlack) *(Lucas Battistoni, Águias Bonifica, Luci Luci, White Club, GoBlack, Hinode, Atlântica Natural) (2 partes | 998 contatos)*
* **Lote 02:** Infoprodutos, Lançamentos, Mentorias e Lives (TomikOS, Hacks Free, Ultimate Academy, Marçal, Dark Lion) *(Hacks Free, TomikOS Lives, Notorius Research, Ultimate Academy, Novidades Marçal, Dark Lion) (3 partes | 1.089 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_MMN_VENDASDIRETAS.zip`

### 📈 Vertical L: Criptomoedas, Traders & Investimentos (2 Lotes | 367 Leads Únicos)
*(Entusiastas e investidores em Bitcoin/criptomoedas e operadores de day trade, mini-índice e mercado financeiro)*
* **Lote 01:** Criptomoedas, Bitcoin e Ativos Descentralizados (CriptoManiacos, Sinais, Bitcoin) *(CriptoManiacos, Criptomilionários, Sinais Crypto, Semana do Bitcoin, Descentralizadas) (1 parte | 69 contatos)*
* **Lote 02:** Day Trade, Traders e Mercado Financeiro (Ativos Trader, VikTraders, Tape Reading) *(Ativos Trader 14, Ação VikTraders, PJT Trader, Boteco do Trader, Clientes Ninja 3Trader) (1 parte | 298 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_CRIPTO_INVESTIMENTOS.zip`

### 🛍️ Vertical M: Ofertas, Compras, Achadinhos & E-commerce (6 Lotes | 1.975 Leads Únicos)
*(Consumidores e compradores segmentados por código de área regional / DDD - Sudoeste PR, Demais Regiões PR e Nacional)*
* **Lote 01:** Ofertas & Compras - Sudoeste do Paraná (Exclusivo DDD 46) *(Ofertas Manfroi Salto do Lontra, Ioris Repasses Beltrão/DV, Lojas Quero Quero, Brechó DV) (2 partes | 536 contatos)*
* **Lote 02:** Ofertas & Compras - Paraná Demais Regiões (DDDs 41 a 45) *(Curitiba 41, Ponta Grossa 42, Londrina 43, Maringá 44, Cascavel/Foz 45) (1 parte | 290 contatos)*
* **Lote 03:** Ofertas & Compras - Nacional e Outros Estados (E-commerce / Brasil) *(Madâme Outlet, Pires Ofertas, Rota Z Ofertas, Black Friday Júlio Martins, Vendas Porto) (3 partes | 1.149 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_OFERTAS_ECOMMERCE.zip`

### 🏛️ Vertical N: Política, Notícias Regionais & Debates (4 Lotes | 1.414 Leads Únicos)
*(Cidadãos, leitores, ativistas e participantes de grupos de notícias locais, cultura, política partidária e eleições 2026)*
* **Lote 01:** Eleições, Debates Políticos e Mobilização *(Prestação de Serviços Eleições 2026, Fala Beltrão debate, Lula 13, Rumo às Eleições Maringá/CWB/Campo Largo) (2 partes | 554 contatos)*
* **Lote 02:** Notícias Regionais, Cultura e Comunicados *(Site Revérbero - política e cultura, Notícias do Dia IB #14 e #16, Comunicados Importantes) (2 partes | 860 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_POLITICA_DEBATES.zip`

### 📱 Vertical O: Ferramentas Web, Apps & Soluções Lucrativas (2 Lotes | 473 Leads Únicos)
*(Usuários de clonadores de páginas, ferramentas de marketing, desenvolvimento de aplicativos móveis e comunidades de iGaming/apps lucrativos)*
* **Lote 01:** Clonadores de Páginas, Ferramentas Web e AppMobile *(REPLIC - Clonador de páginas, Eu Preciso x Eu Faço - AppMobile, Ferramentas Marketing) (1 parte | 367 contatos)*
* **Lote 02:** Aplicativos Lucrativos, Alertas e Comunidades iGaming *(TROPA IGAMING GP 02, Aplicativos Lucrativos, ALERTAS LUCRATIVOS, Sistemas Lucrativos) (1 parte | 106 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_FERRAMENTAS_APPS.zip`

### 🎫 Vertical P: Serviços, Mobilidade, Crédito & Rifas (3 Lotes | 355 Leads Únicos)
*(Consumidores de boleto parcelado, motoristas e usuários de mobilidade/rastreamento veicular e participantes de rifas/sorteios)*
* **Lote 01:** Boleto Parcelado e Crédito *(😱 Liberado Boleto Parcelado, Boletos para Pagamento) (1 parte | 92 contatos)*
* **Lote 02:** Mobilidade Urbana e Proteção Veicular *(Urbano46 Todos Os Grupos, Mobilecar Do Brasil) (1 parte | 130 contatos)*
* **Lote 03:** Rifas, Sorteios e Ações Regionais *(Rifa de Natal, Primeira Ação da Porto Rifas) (1 parte | 133 contatos)*
* 📦 **ZIP:** `https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_SERVICOS_MOBILIDADE_RIFAS.zip`

---

## 🏆 Resumo Consolidado das 16 Verticais Extraídas (Total: 32.440 Leads Únicos)

| Vertical | Arquivos CSV | Leads Únicos | Link do Pacote ZIP |
| :--- | :---: | :---: | :--- |
| **A. Educação Geral** | 21 CSVs | 9.080 | [TODOS_LOTES_EDUCACAO.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_EDUCACAO.zip) |
| **B. Tecnologia Pura** | 7 CSVs | 2.613 | [TODOS_LOTES_TECNOLOGIA.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_TECNOLOGIA.zip) |
| **C. Robótica Escolar** | 3 CSVs | 1.155 | [TODOS_LOTES_ROBOTICA_COMPUTACAO.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_ROBOTICA_COMPUTACAO.zip) |
| **D. Escolas & SEED** | 6 CSVs | 1.834 | [TODOS_LOTES_ESCOLAS_SEED.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_ESCOLAS_SEED.zip) |
| **E. Negócios & PLR** | 10 CSVs | 4.317 | [TODOS_LOTES_NEGOCIOS.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_NEGOCIOS.zip) |
| **F. Regional & Caronas** | 9 CSVs | 3.727 | [TODOS_LOTES_REGIONAL_CARONAS.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_REGIONAL_CARONAS.zip) |
| **G. Turismo & Milhas** | 4 CSVs | 1.269 | [TODOS_LOTES_TURISMO_MILHAS.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_TURISMO_MILHAS.zip) |
| **H. Empregos & Vagas** | 2 CSVs | 894 | [TODOS_LOTES_EMPREGOS_VAGAS.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_EMPREGOS_VAGAS.zip) |
| **I. Saúde & Bem-Estar** | 2 CSVs | 181 | [TODOS_LOTES_SAUDE_BEMESTAR.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_SAUDE_BEMESTAR.zip) |
| **J. Pós-Graduação & Cursos** | 3 CSVs | 699 | [TODOS_LOTES_POS_GRADUACAO.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_POS_GRADUACAO.zip) |
| **K. MMN & Infoprodutos** | 5 CSVs | 2.087 | [TODOS_LOTES_MMN_VENDASDIRETAS.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_MMN_VENDASDIRETAS.zip) |
| **L. Cripto & Traders** | 2 CSVs | 367 | [TODOS_LOTES_CRIPTO_INVESTIMENTOS.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_CRIPTO_INVESTIMENTOS.zip) |
| **M. Ofertas & Compras (DDD)** | 6 CSVs | 1.975 | [TODOS_LOTES_OFERTAS_ECOMMERCE.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_OFERTAS_ECOMMERCE.zip) |
| **N. Política & Notícias** | 4 CSVs | 1.414 | [TODOS_LOTES_POLITICA_DEBATES.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_POLITICA_DEBATES.zip) |
| **O. Ferramentas Web & Apps** | 2 CSVs | 473 | [TODOS_LOTES_FERRAMENTAS_APPS.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_FERRAMENTAS_APPS.zip) |
| **P. Serviços, Mobilidade & Rifas** | 3 CSVs | 355 | [TODOS_LOTES_SERVICOS_MOBILIDADE_RIFAS.zip](https://hermes.acessaronline.com.br/downloads/TODOS_LOTES_SERVICOS_MOBILIDADE_RIFAS.zip) |
| **TOTAL GERAL** | **89 CSVs** | **32.440** | *100% livres de duplicatas cruzadas e com 9º dígito* |

---

## 📱 5. Comandos no WhatsApp (Auto-Atendimento)

Diretamente no WhatsApp vinculado ao Hermes (no chat de mensagens salvas / consigo mesmo), basta enviar:

* `#lotes` ou `#professores` — Atualiza e regera os 21 lotes de educação geral.
* `#tech` ou `#tecnologia` — Atualiza e regera os 7 lotes de tecnologia pura (sem professores).
* `#robotica` ou `#computacao` — Atualiza e regera os 3 lotes de professores de robótica/computação.
* `#escolas` ou `#seed` ou `#colegios` — Atualiza e regera os 6 lotes de escolas locais e projetos SEED.
* `#negocios` ou `#marketing` ou `#plr` ou `#afiliados` — Atualiza e regera os 10 lotes de negócios, marketing e PLR.
* `#regional` ou `#caronas` ou `#parana` — Atualiza e regera os 9 lotes regionais e caronas do PR.
* `#turismo` ou `#viagens` ou `#milhas` — Atualiza e regera os 4 lotes de turismo, viagens e milhas.
* `#empregos` ou `#vagas` ou `#oportunidades` — Atualiza e regera os 2 lotes de empregos e vagas.
* `#saude` ou `#bemestar` ou `#terapia` ou `#pilates` — Atualiza e regera os 2 lotes de saúde, terapias e bem-estar.
* `#pos` ou `#unibf` ou `#enpex` ou `#aprendizagem` — Atualiza e regera os 3 lotes de pós-graduação e cursos.
* `#mmn` ou `#vendasdiretas` ou `#bonifica` ou `#battistoni` — Atualiza e regera os 5 lotes de MMN e vendas diretas.
* `#cripto` ou `#crypto` ou `#trader` ou `#investimentos` — Atualiza e regera os 2 lotes de cripto e traders.
* `#ofertas` ou `#compras` ou `#manfroi` ou `#ioris` — Atualiza e regera os 6 lotes de ofertas e e-commerce segmentados por DDD.
* `#politica` ou `#noticias` ou `#eleicoes` ou `#debates` — Atualiza e regera os 4 lotes de política, notícias regionais e debates.
* `#ferramentas` ou `#apps` ou `#replic` ou `#igaming` — Atualiza e regera os 2 lotes de ferramentas web e apps lucrativos.
* `#servicos` ou `#rifas` ou `#boleto` ou `#urbano46` ou `#mobilecar` — Atualiza e regera os 3 lotes de serviços, mobilidade, boleto e rifas.
* `#mapa` ou `#inventario` — Gera o relatório geral de todos os 1.086 grupos da conta.
* `#extrair [qualquer termo]` — Extrai qualquer nicho sob demanda.

---

## 🛠️ 6. Testes via Terminal na VPS

```bash
CID=$(docker ps -q -f name=hermes_hermes | head -n 1)

# Extração de Professores Gerais:
docker exec $CID curl -m 120 -s http://localhost:3000/api/extract-lotes

# Extração de Tecnologia Pura:
docker exec $CID curl -m 120 -s http://localhost:3000/api/extract-tech

# Extração de Professores de Robótica:
docker exec $CID curl -m 120 -s http://localhost:3000/api/extract-robotica

# Extração de Escolas e Projetos SEED:
docker exec $CID curl -m 120 -s http://localhost:3000/api/extract-escolas

# Extração de Negócios, Marketing e PLR:
docker exec $CID curl -m 180 -s http://localhost:3000/api/extract-negocios

# Extração de Regional Paraná e Caronas:
docker exec $CID curl -m 180 -s http://localhost:3000/api/extract-regional

# Extração de Turismo, Viagens e Milhas:
docker exec $CID curl -m 180 -s http://localhost:3000/api/extract-turismo

# Extração de Empregos, Vagas e Oportunidades:
docker exec $CID curl -m 180 -s http://localhost:3000/api/extract-empregos

# Extração de Saúde, Terapias, Estética e Bem-Estar:
docker exec $CID curl -m 180 -s http://localhost:3000/api/extract-saude

# Extração de Ensino Superior, Pós-Graduação e Cursos:
docker exec $CID curl -m 180 -s http://localhost:3000/api/extract-pos

# Extração de MMN, Vendas Diretas e Infoprodutos:
docker exec $CID curl -m 240 -s http://localhost:3000/api/extract-mmn

# Extração de Criptomoedas, Traders e Investimentos:
docker exec $CID curl -m 180 -s http://localhost:3000/api/extract-cripto

# Extração de Ofertas, Compras e E-commerce (Segmentado por DDD):
docker exec $CID curl -m 240 -s http://localhost:3000/api/extract-ofertas

# Extração de Política, Notícias Regionais e Debates:
docker exec $CID curl -m 240 -s http://localhost:3000/api/extract-politica

# Extração de Ferramentas Web e Apps Lucrativos:
docker exec $CID curl -m 180 -s http://localhost:3000/api/extract-ferramentas

# Extração de Serviços, Mobilidade, Boleto Parcelado e Rifas:
docker exec $CID curl -m 180 -s http://localhost:3000/api/extract-servicos
```
```
```
