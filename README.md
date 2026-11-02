# ⚡ Hermes SDR & CRM — Agente Autônomo de Vendas, Prospecção e Copilot com IA para WhatsApp

> **Desenvolvido por Salesio Ninja**  
> Plataforma integrada de **SDR Autônomo (Sales Development Representative)**, **CRM Conversacional** e **Live Chat Copilot** para prospecção ativa, qualificação de leads e agendamento automático de demonstrações via WhatsApp com inteligência artificial.

---

## 🌟 O que o Agente Hermes SDR & CRM é capaz de fazer?

O **Hermes SDR** não é um chatbot tradicional baseado em árvores de decisão engessadas. Trata-se de um **agente de inteligência artificial autônomo e contextual** com proteções ativas anti-bloqueio, integrado a calendários, pipelines em tempo real e interface responsiva para celular e computador.

### 1. 🎯 Prospecção Ativa Humanizada (Outbound SDR)
- **Spintax Recursivo Multinível:** Gera variações textuais infinitas a partir de modelos como `{Olá|Oi|Tudo bem}{nome}?`, tornando cada mensagem única aos olhos do algoritmo do WhatsApp.
- **Saudação Contextual Temporal:** Ajusta automaticamente para *"Bom dia"*, *"Boa tarde"* ou *"Boa noite"* conforme o fuso horário local e horário de envio.
- **Higienização de Nomes e Títulos:** Remove prefixos, caracteres de fórmulas de planilhas (`="55..."`) e limpa nomenclaturas como *"Prof."*, *"Professor"*, isolando o primeiro nome com pontuação e maiúsculas corretas.
- **Disparo de Teste Manual Seguro:** Permite colar números avulsos no painel para validar a abordagem e testar o fluxo sem risco.

### 2. 🛡️ Blindagem de Conta e Arquitetura Anti-Ban (Meta / WhatsApp)
- **Pacing Aleatório (Jitter):** Intervalo configurável e aleatório entre mensagens (ex.: 60 a 180 segundos) para reproduzir comportamento estritamente humano.
- **Horário Comercial Estrito:** O motor só dispara dentro da janela permitida (padrão: das 8h às 19h), pausando automaticamente fora do horário comercial.
- **Limite Diário Rigoroso:** Configuração de teto diário de novos contatos (ex.: 35 contatos/dia) para preservação de reputação de chip novo ou aquecido.
- **Simulação Prévia (Dry-Run):** Permite rodar toda a campanha em modo simulação no painel antes de acionar o envio real no WhatsApp.

### 3. 🧠 Qualificação Conversacional e Quebra de Objeções (Inbound AI)
- **Atendimento Autônomo com LLM (OpenRouter / GPT-4o-mini):** Quando o lead responde à mensagem fria, o Hermes SDR analisa todo o histórico anterior e formula respostas persuasivas, amigáveis e precisas.
- **Simulação de Digitação Humana (*Presence Composing*):** Aciona status de *"digitando..."* no WhatsApp por alguns segundos antes de disparar a resposta, transmitindo naturalidade e atenção pessoal.
- **Foco em Conversão:** Conduz o diálogo para o agendamento de uma demonstração de 10 minutos com o Salesio Ninja.
- **Detector de Desinteresse (*Opt-Out*):** Se o contato pedir para não ser mais contatado, o agente agradece cordialmente, atualiza o status para `OPT_OUT` e nunca mais envia mensagens para o contato.

### 4. 📅 Agendamento Inteligente com Google Calendar
- **Consulta de Agenda em Tempo Real:** Conecta-se à API da Agenda Google para verificar horários livres e compromissos confirmados.
- **Confirmação e Marcação de Horário:** Identifica propostas de data/hora na resposta do lead (ex.: *"pode ser amanhã às 10h"*), confirma o compromisso e atualiza o status do CRM para `SCHEDULED`.
- **Notificação Instantânea no WhatsApp do Dono:** Dispara um alerta prioritário para o WhatsApp do Salesio Ninja (`+55 46 99976-5576`) com o resumo do lead, o que ele disse e o horário agendado.

### 5. 💬 Live Chat & Copilot em Tempo Real (Server-Sent Events - SSE)
- **Monitoramento em Tela Única:** Acompanhe as respostas dos leads e as interações do Hermes SDR em tempo real, sem necessidade de recarregar a página.
- **Indicador de Digitação na Tela:** Visualização em tempo real quando o Hermes SDR está gerando uma resposta para um lead.
- **Auto-Sync Redundante:** O painel conta com sincronização periódica silenciosa para garantir integridade absoluta de dados mesmo em conexões oscilantes.

### 6. 👤 Intervenção Humana Instantânea (*Human Takeover*)
- **Pausa Seletiva do Agente:** Ao clicar em *"Assumir Atendimento Manual"* (ou simplesmente enviar uma mensagem pela barra inferior do chat), o Hermes SDR pausa o atendimento automático exclusivamente para aquele lead.
- **Envio Direto pelo Painel:** O operador digita no painel web/mobile e a mensagem sai instantaneamente pelo WhatsApp conectado, ficando catalogada como `👤 Salesio Ninja (Humano)`.
- **Devolução para a IA com 1 Clique:** Finalizada a intervenção, basta clicar em *"Devolver ao Hermes"* para reativar as respostas autônomas do agente.

### 7. 📊 Painel de Controle e Métricas de CRM (Desktop & Mobile)
- **Funil de Vendas Visual:** Contadores de Base de Leads, Contatos Realizados, Respostas Obtidas e Agendamentos Concluídos.
- **Segmentação por Campanhas:** Suporte a múltiplos nichos (Educação BNCC Paraná, Negócios/PLR, Tecnologia, Turismo, Regional PR/SC, etc.).
- **Interface Responsiva:** Otimizada com Tailwind CSS para abrir em qualquer smartphone com barra de ações rápidas ou em monitores desktop de alta resolução.

---

## 🏗️ Arquitetura do Sistema

```
[ WhatsApp ] <---> [ Baileys Bridge / Node.js ]
                            ^
                            | Webhooks & REST API
                            v
[ Hermes SDR Server (FastAPI + SQLite + EventSource SSE) ]
       |                            |                           |
       v                            v                           v
[ OpenRouter LLM ]         [ Google Calendar ]        [ Painel Web Vue 3 + Tailwind ]
 (GPT-4o-mini)             (Agenda em Tempo Real)     (Live Chat + Human Takeover)
```

---

## 📁 Estrutura de Arquivos

```
hermes-sdr-crm1/
├── sdr_server.py           # Backend FastAPI: Agente SDR, Anti-ban, Webhooks, SSE e CRM
├── sdr_ui/
│   └── index.html          # Frontend SPA responsivo: Dashboard, Métricas e Chat ao Vivo
├── skills/                 # Skills do agente Antigravity
│   ├── whatsapp-outbound-sdr/
│   └── whatsapp-lead-extractor/
├── requirements.txt        # Dependências Python
├── .env.example            # Modelo de configuração de variáveis
├── .gitignore              # Proteção de credenciais, logs e bases privadas
└── README.md               # Esta documentação
```

---

## 🚀 Como Executar

### 1. Requisitos
- Python 3.10 ou superior
- Instância do Baileys WhatsApp Bridge ativa (porta 3000)

### 2. Instalação das dependências
```bash
pip install -r requirements.txt
```

### 3. Configuração de Variáveis
Copie o arquivo `.env.example` para `.env` e preencha suas chaves:
```bash
cp .env.example .env
```

### 4. Inicialização do Servidor
```bash
python sdr_server.py
```
O painel estará disponível em:
👉 `http://localhost:8000/painel/` (ou pela URL configurada no proxy reverso).

---

## 🔒 Segurança e Privacidade
- O projeto conta com regras estritas no `.gitignore` para impedir o versionamento de listas de contatos sensíveis (`*.csv`, `*.zip`), chaves de API (`.env`, `service_account.json`) e bancos de dados SQLite locais.
- Todas as credenciais de produção devem ser injetadas exclusivamente via variáveis de ambiente.

---

*Desenvolvido com excelência técnica para o ecossistema Salesio Ninja.*
