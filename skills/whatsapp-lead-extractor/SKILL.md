---
name: whatsapp-lead-extractor
version: 1.0.0
author: Hermes Agent & Antigravity
description: Extrai, desduplica, segmenta por sub-tema/nicho e formata contatos de grupos do WhatsApp em lotes seguros (máx 500 contatos), com normalização do 9º dígito (ANATEL) e proteção contra notação científica do Excel.
metadata:
  hermes:
    tags: [whatsapp, extracao, leads, marketing, educacao, bncc, pss]
---

# Skill: Extrator de Leads de Grupos do WhatsApp

Esta skill estabelece o padrão operacional definitivo para o **Hermes Agent** e seus assistentes realizarem extrações seguras, organizadas e compatíveis de contatos a partir de grupos do WhatsApp.

---

## 🏛️ Arquitetura do Sistema

```
[ WhatsApp Web / Grupos ]
            │
            ▼ (Baileys v7 WebSocket)
[ Bridge Node.js (/opt/data/scripts/whatsapp-bridge/) ]
  ├── bridge.js (Servidor Express na porta 3000 + Socket WhatsApp)
  └── group_extractor.js (Motor de filtragem, desduplicação e exportação)
            │
            ├─► Gera CSVs e ZIP em: /opt/data/downloads/
            ├─► Notifica o usuário no WhatsApp com links de download
            └─► Disponibiliza via Web em: https://hermes.acessaronline.com.br/downloads/
```

---

## ⚡ As 4 Regras de Ouro da Extração

Toda e qualquer extração realizada pelo Hermes ou subagentes **DEVE** seguir rigorosamente estas quatro regras:

### 1. Limite Máximo de 500 Contatos por Arquivo
* **Por quê:** O disparo seguro de WhatsApp exige controle rígido de cadência para evitar banimento de chips. Lotes de até 500 contatos representam o tamanho ideal para 1 dia de aquecimento ou para dividir entre 2 disparadores.
* **Comportamento:** Se uma categoria possuir mais de 500 leads, ela **obrigatoriamente** deve ser fatiada em partes (`Lote_..._Parte1.csv`, `Lote_..._Parte2.csv`, etc.).

### 2. Desduplicação Global
* **Por quê:** Um mesmo lead não pode receber a mesma abordagem ou mensagens redundantes caso participe de mais de um grupo afim.
* **Comportamento:** O sistema mantém um `Set` global em memória (`globalSeenPhones`). O lead é alocado exclusivamente no primeiro sub-tema em que for identificado e ignorado nos seguintes.

### 3. Normalização do 9º Dígito (Padrão ANATEL)
* **Por quê:** Contas antigas de WhatsApp (criadas antes de 2016) são armazenadas no banco de dados do WhatsApp sem o nono dígito (com 12 dígitos: `55` + DDD + 8 dígitos). Ferramentas de disparo em massa costumam rejeitar números de celular com 12 dígitos.
* **Comportamento:** 
  - Todo celular brasileiro com 12 dígitos cujo primeiro número local seja `6, 7, 8 ou 9` recebe automaticamente o prefixo `9` após o DDD.
  - Exemplo: `554699765576` vira `5546999765576` (13 dígitos).
  - Telefones fixos (iniciados em 2, 3, 4, 5) permanecem com 12 dígitos.

### 4. Formatação Blindada contra Notação Científica do Excel
* **Por quê:** Quando o Excel no Windows abre um arquivo `.csv`, qualquer número longo (mais de 11 dígitos) é transformado automaticamente em notação científica (`5,547E+12`), destruindo o telefone se o usuário salvar a planilha.
* **Comportamento:**
  - O arquivo CSV **deve iniciar com UTF-8 BOM (`\uFEFF`)** para o Excel reconhecer acentuação brasileira (`ç`, `ã`, `é`).
  - O separador deve ser ponto-e-vírgula (`;`).
  - Todo campo numérico de telefone deve ser gravado com a fórmula de texto: `="5546999765576"`. Isso faz o Excel exibir o texto puro, alinhado à esquerda, sem notação científica.

---

## 📋 Estrutura Oficial das Colunas do CSV

| Coluna | Exemplo de Valor | Descrição |
| :--- | :--- | :--- |
| `whatsapp` | `="5546999765576"` | Telefone oficial com 13 dígitos (9º dígito inserido) pronto para o Excel e disparadores. |
| `telefone_original` | `="554699765576"` | Número original de registro no WhatsApp (caso o disparador exija JID antigo). |
| `nome` | `Professor(a)` | Nome público do perfil ou tratamento humanizado inteligente caso esteja em branco. |
| `grupo_origem` | `Debate Estágio probatório SEED` | Nome do grupo do WhatsApp de onde o lead foi extraído. |
| `subtema` | `Concursos Públicos e PSS (SEED-PR / Geral)` | Nome da categoria segmentada. |
| `is_admin` | `NAO` ou `SIM` | Indica se o contato é administrador do grupo. |
| `ddd` | `46` | DDD extraído para permitir filtragem regional no Excel. |
| `data_extracao` | `29/10/2026` | Data em formato brasileiro em que a lista foi gerada. |

---

## 🎯 Sub-temas e Expressões Regulares de Segmentação

Na vertical de **Educação / Professores**, as buscas devem respeitar a seguinte ordem de prioridade:

```javascript
const SUBTHEMES = [
  {
    id: 'Lote_01_BNCC_Series_Iniciais',
    title: 'BNCC, Séries Iniciais e Alfabetização',
    regex: /bncc|maternal|creche|alfabet|infantil|s[eé]ries iniciais|letramento|2[°º]\s*ano|alfabetinho/i,
    negative: null,
    defaultName: 'Professor(a)'
  },
  {
    id: 'Lote_02_Educacao_Fisica',
    title: 'Educação Física e Esportes',
    regex: /f[ií]sic[ao]|ed\.?\s*f[ií]|desporto|esport|futebol|futsal|jeps|escolinha/i,
    negative: /astro|qu[ií]mica/i,
    defaultName: 'Professor(a) de Ed. Física'
  },
  {
    id: 'Lote_03_Sala_Recursos_Inclusao',
    title: 'Sala de Recursos, Inclusão e Reforço (PMA)',
    regex: /recurso|refor[çc]o|inclus[aã]o|pma|autis|especial|adaptada|aee|libras/i,
    negative: null,
    defaultName: 'Professor(a)'
  },
  {
    id: 'Lote_04_Concursos_PSS_PR',
    title: 'Concursos Públicos e PSS (SEED-PR / Geral)',
    regex: /concurso|pss|cnu|edital|probat[oó]rio|nomeados|convocados|qpm/i,
    negative: null,
    defaultName: 'Professor(a)'
  },
  {
    id: 'Lote_05_Professores_Gerais_Ensino',
    title: 'Professores Gerais e Disciplinas do Ensino',
    regex: /professor|professora|professores|professoras|\bprof\b|pedagog|educa|ensino|docente|escola|colegio|aula|matemática|português|história|ciências|geografia|arte|química|física|inglês|computação|novo ensino médio/i,
    negative: null,
    defaultName: 'Professor(a)'
  }
];
```

---

## 📱 Comandos Disponíveis no WhatsApp

O usuário pode acionar o sistema diretamente pelo seu próprio WhatsApp (modo auto-conversa):

1. **`#lotes` ou `#professores`:**
   - Varre todos os grupos educacionais gerais.
   - Gera os 21 lotes (máximo 500 por lista) e o ZIP consolidado.

2. **`#tech` ou `#tecnologia`:**
   - Varre grupos de TI pura (Automação, Devs, IA). Professores são 100% excluídos.
   - Gera os 7 lotes e o ZIP consolidado.

3. **`#robotica` ou `#computacao`:**
   - Varre grupos escolares de robótica e pensamento computacional.
   - Gera os 3 lotes e o ZIP consolidado.

4. **`#escolas` ou `#seed` ou `#colegios`:**
   - Varre colégios municipais/estaduais (CEIMM, Itaipu, Barra Bonita, Doze, Vicente Câmara, Rio Gavião), projetos pedagógicos SEED-PR (Projeto de Vida, Recomposição, Scratch, Pensamento Lógico) e convocados/sindicato (Elite do 1.º chamamento, APP Beltrão/Municipais, CEEBJA e NRE).
   - Gera os 6 lotes e o ZIP consolidado.

5. **`#negocios` ou `#marketing` ou `#plr` ou `#afiliados`:**
   - Varre grupos de marketing digital, tráfego pago, lançamentos, vendas, e-commerce, dropshipping, infoprodutos e PLR.
   - Gera os 10 lotes e o ZIP consolidado.

6. **`#regional` ou `#caronas` ou `#parana`:**
   - Varre grupos regionais do Paraná (Dois Vizinhos, Pato Branco, Beltrão, Cascavel, Toledo, Foz, Curitiba), caronas intermunicipais, briks e debates.
   - Gera os 9 lotes e o ZIP consolidado.

7. **`#turismo` ou `#viagens` ou `#milhas`:**
   - Varre grupos de agências de turismo (Claudia Sousa, Fenicio's Tur, Viacapi, Olitur) e emissores de passagens/milhas (GoFly, Estevam, Norton, Alertas de Passagens).
   - Gera os 4 lotes e o ZIP consolidado.

8. **`#empregos` ou `#vagas` ou `#oportunidades`:**
   - Varre grupos de vagas de emprego, recrutamento regional (JobsPRO, Empregos Bahia, Vagas Jornalismo) e oportunidades de crescimento profissional (T5K, seleções).
   - Gera os 2 lotes e o ZIP consolidado.

9. **`#saude` ou `#bemestar` ou `#terapia` ou `#pilates`:**
   - Varre grupos de saúde natural, aromaterapia dōTerra/Charoma, reiki, pilates, fisioterapia e emagrecimento.
   - Gera os 2 lotes e o ZIP consolidado.

10. **`#pos` ou `#posgraduacao` ou `#unibf` ou `#enpex` ou `#aprendizagem`:**
   - Varre grupos de ensino superior, pós-graduação, segunda licenciatura UNIBF/ENPEX e Programa Mais Aprendizagem Paraná.
   - Gera os 3 lotes e o ZIP consolidado.

11. **`#mmn` ou `#vendasdiretas` ou `#bonifica` ou `#battistoni` ou `#lancamentos` ou `#infoprodutos`:**
   - Varre grupos de liderança em vendas diretas, marketing multinível (Bonifica, Luci Luci, Hinode, Battistoni, White Club, GoBlack) e infoprodutos/lançamentos (TomikOS, Hacks Free, Notorius, Marçal, Dark Lion).
   - Gera os 5 lotes e o ZIP consolidado.

12. **`#cripto` ou `#crypto` ou `#trader` ou `#traders` ou `#investimentos` ou `#financas`:**
   - Varre grupos de criptomoedas, Bitcoin, finanças descentralizadas (CriptoManiacos, Sinais Crypto, Bitcoin) e day trade, mercado financeiro (Ativos Trader, VikTraders, Tape Reading).
   - Gera os 2 lotes e o ZIP consolidado.

13. **`#ofertas` ou `#compras` ou `#achadinhos` ou `#manfroi` ou `#ioris` ou `#ecommerce`:**
   - Varre grupos de compras, ofertas e e-commerce segmentados por região (DDD 46 Sudoeste PR, DDDs 41-45 Paraná Demais Regiões e Nacional/Outros Estados).
   - Gera os 6 lotes e o ZIP consolidado.

14. **`#politica` ou `#noticias` ou `#eleicoes` ou `#debates`:**
   - Varre grupos de eleições 2026, debates partidários, jornais locais e notícias regionais (Site Revérbero, Notícias do Dia IB, Prestação de Serviços Eleições, etc.).
   - Gera os 4 lotes e o ZIP consolidado.

15. **`#ferramentas` ou `#apps` ou `#replic` ou `#igaming`:**
   - Varre grupos de clonadores de páginas, ferramentas web, desenvolvimento de aplicativos móveis e comunidades de iGaming/apps lucrativos.
   - Gera os 2 lotes e o ZIP consolidado.

16. **`#servicos` ou `#rifas` ou `#boleto` ou `#urbano46` ou `#mobilecar`:**
   - Varre grupos de consumidores de boleto parcelado, usuários e motoristas de mobilidade/rastreamento veicular e participantes de rifas/sorteios regionais.
   - Gera os 3 lotes e o ZIP consolidado.

17. **`#mapa` ou `#inventario`:**
   - Mapeia todos os grupos da conta (1.086 grupos).
   - Exporta `inventario_grupos.csv` com total de membros e status de administrador.

18. **`#extrair [termo]`:**
   - Extrai um nicho livre sob demanda (ex: `#extrair saude`).

---

## 💻 Gatilhos HTTP Internos (Para Execuções Automatizadas)

O servidor bridge expõe endpoints internos na porta 3000 para que scripts locais ou fluxos do n8n possam disparar a extração sem intervenção humana:

```bash
# Executado dentro do container hermes:
curl -s http://localhost:3000/api/extract-lotes
curl -s http://localhost:3000/api/extract-tech
curl -s http://localhost:3000/api/extract-robotica
curl -s http://localhost:3000/api/extract-escolas
curl -s http://localhost:3000/api/extract-negocios
curl -s http://localhost:3000/api/extract-regional
curl -s http://localhost:3000/api/extract-turismo
curl -s http://localhost:3000/api/extract-empregos
curl -s http://localhost:3000/api/extract-saude
curl -s http://localhost:3000/api/extract-pos
curl -s http://localhost:3000/api/extract-mmn
curl -s http://localhost:3000/api/extract-cripto
curl -s http://localhost:3000/api/extract-ofertas
curl -s http://localhost:3000/api/extract-politica
curl -s http://localhost:3000/api/extract-ferramentas
curl -s http://localhost:3000/api/extract-servicos
```

---

## 🔧 Procedimentos de Operação e Manutenção na VPS

* **Caminho dos Scripts no Host:** `/opt/hermes-agent/data/scripts/whatsapp-bridge/`
* **Caminho dos Scripts no Container:** `/opt/data/scripts/whatsapp-bridge/`
* **Diretório Público de Downloads:** `/opt/hermes-agent/data/downloads/`
* **URL Pública de Acesso:** `https://hermes.acessaronline.com.br/downloads/`

### Como recarregar o bridge após alterar códigos:
```bash
CID=$(docker ps -q -f name=hermes_hermes | head -n 1)
docker exec $CID pkill -f "node.*bridge.js"
# O supervisor s6 reinicia o processo automaticamente em 1 a 2 segundos
```

### Como checar saúde da conexão WhatsApp:
```bash
CID=$(docker ps -q -f name=hermes_hermes | head -n 1)
docker exec $CID curl -s http://localhost:3000/health
# Deve retornar: {"status":"connected", ...}
```
