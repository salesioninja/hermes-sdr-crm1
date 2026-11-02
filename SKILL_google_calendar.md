---
name: google-calendar
version: 2.0.0
author: Hermes Agent & Salesio Ninja
description: "Integração oficial completa com o Google Calendar via Service Account 24/7. Permite consultar agenda, listar compromissos do dia/semana, agendar eventos com trava anti-conflito, alterar/reagendar horários e excluir eventos de forma 100% autônoma."
metadata:
  hermes:
    tags: [calendar, google-calendar, agenda, reuniao, agendamento, sdr, closer, secretária]
---

# 📅 Google Calendar - Módulo Oficial Hermes (Service Account 24/7)

Esta skill permite ao **Hermes Agent** interagir diretamente com a Google Agenda do usuário de forma 100% autônoma, sem navegadores, sem portas expostas e sem expiração de token OAuth.

A conexão utiliza uma **Service Account do Google Cloud** com permissão delegada de edição na agenda principal (`suporteninja1@gmail.com` ou a agenda do cliente configurada em `HERMES_CALENDAR_ID`).

---

## 🛠️ Comandos Disponíveis via Terminal (Hermes CLI)

O utilitário oficial está instalado globalmente no sistema em `/usr/local/bin/agenda` (apontando para `/opt/data/hermes_calendar.py`).

### 1. Consultar Compromissos (`list`)
Exibe os eventos do período solicitado com data legível, horário de início/término, ID único e link oficial do Google Calendar.
```bash
# Consultar hoje (cobre das 00:00 às 23:59):
agenda list hoje

# Consultar amanhã:
agenda list amanha

# Consultar próximos 7 dias:
agenda list 7

# Consultar próximos 30 dias:
agenda list 30
```

### 2. Agendar Novo Compromisso (`add`)
Cria um novo evento no Google Calendar. **Possui trava anti-conflito automática:** se já existir outro compromisso no horário solicitado, a operação é bloqueada e informa o conflito.
```bash
# Sintaxe:
agenda add "<Título do Evento>" "<Horário>" [hoje|amanha|YYYY-MM-DD] [duração_min]

# Exemplos:
agenda add "Apresentação com Lead" "14:30" hoje 45
agenda add "Reunião de Alinhamento" "10:00" amanha 60
agenda add "Call Estratégica" "16:00" 2026-11-05 30

# Forçar agendamento ignorando conflitos (se expressamente solicitado pelo usuário):
agenda add "Evento Especial" "12:00" hoje 60 --force
```

### 3. Alterar / Mudar / Reagendar Horário (`move`)
Muda o horário de um evento existente diretamente no Google Calendar sem duplicar o compromisso.
```bash
# Sintaxe:
agenda move "<Título ou ID>" "<Novo_Horário>" [hoje|amanha|YYYY-MM-DD]

# Exemplos:
agenda move "Café da Manhã" "10:30" hoje
agenda move "Apresentação com Lead" "16:00" amanha
agenda move nfk3gpj3bsuqvbn6bkj85v3keo "11:00" hoje
```

### 4. Excluir / Cancelar Compromisso (`del`)
Remove o evento do Google Calendar pelo nome, horário ou pelo ID único do evento.
```bash
# Sintaxe:
agenda del "<Título ou ID>" [horário] [hoje|amanha|YYYY-MM-DD]

# Exemplos:
agenda del "Café da Manhã" 08:00 hoje
agenda del "Reunião de Teste" hoje
agenda del nfk3gpj3bsuqvbn6bkj85v3keo
```

---

## 🐍 Integração Direta em Python (Código Interno)

Você também pode importar o módulo diretamente em qualquer script ou tarefa Python dentro do Hermes:
```python
import sys
sys.path.append('/opt/data')
from hermes_calendar import (
    list_upcoming_events,
    create_event,
    smart_move,
    smart_delete,
    check_conflict
)

# 1. Listar compromissos de hoje
eventos = list_upcoming_events(filter_mode='hoje')
for ev in eventos:
    print(f"- {ev['summary']} das {ev['start']} às {ev['end']} (ID: {ev['id']})")

# 2. Criar com verificação de conflito
res = create_event("Reunião VIP", "15:00", duration_minutes=45)
if res['conflict']:
    print("Conflito detectado:", res['message'])
else:
    print("Criado com sucesso! Link:", res['htmlLink'])

# 3. Mudar horário
res_move = smart_move("Reunião VIP", "16:30", date_str="hoje")

# 4. Excluir
res_del = smart_delete("Reunião VIP", time_str="16:30", date_str="hoje")
```

---

## ⚙️ Variáveis de Ambiente e Arquivos de Configuração

- `HERMES_CALENDAR_ID`: E-mail da agenda a gerenciar (ex: `suporteninja1@gmail.com`).
- `HERMES_GOOGLE_KEY`: Caminho da chave JSON da Service Account (padrão: `/opt/data/service_account.json`).
- `Fuso Horário`: `America/Sao_Paulo` (UTC-3).
- `Permissão do JSON`: Deve estar com permissão de leitura `chmod 644` para o usuário `hermes`.

---

## 🔒 Regras de Comportamento para o Agente (WhatsApp & Web)

1. **NUNCA simule que agendou ou alterou sem executar o comando no Terminal.**
2. **NUNCA crie arquivos em `/opt/data/cache/scratch/` ou use cron interno para registrar compromissos de agenda.**
3. **NUNCA use `lembretes.md` para compromissos com horário.** `lembretes.md` é exclusivo para notas e anotações sem horário fixo.
4. **Sempre retorne uma resposta limpa, direta e amigável**, contendo a data, horário de início/término e o link oficial do Google Calendar.
