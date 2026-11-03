---
name: whatsapp-messenger
version: 1.0.0
author: Hermes Agent & Salesio Ninja
description: "Disparo e Agendamento Executivo de Mensagens WhatsApp via ferramenta oficial 'wpp'. Permite enviar mensagens imediatas, agendar mensagens para qualquer horario (ex: 'as 06:50', 'as 19:00', 'amanha 10h', 'em 30 min'), listar e cancelar agendamentos para qualquer numero de telefone."
metadata:
  hermes:
    tags: [whatsapp, wpp, mensagem, mensagens, agendar, agendamento, programar, envio, enviar, celular, disparo, contato, torpedo]
---

# WhatsApp Messenger & Scheduler - Modulo Executivo Hermes

Esta skill permite ao **Hermes Agent** enviar e programar/agendar o envio de mensagens no WhatsApp para qualquer contato ou numero de telefone solicitado pelo Salesio.

O utilitario oficial executivo e `wpp`, disponivel no terminal em `/opt/data/.local/bin/wpp`, `/opt/hermes/bin/wpp` e `/usr/local/bin/wpp`.

---

## Comandos Disponiveis via Terminal (Hermes CLI)

### 1. Agendar Mensagem para um Horario Especifico (`wpp schedule`)
Quando o Salesio pedir para agendar ou enviar em determinado horario ("as 06:50", "as 19h", "amanha as 10:00", etc.):

```bash
# Sintaxe:
wpp schedule <numero_telefone> "<mensagem_completa>" "<horario>"

# Exemplos:
wpp schedule 46999087711 "Bom dia! Desejo um excelente e produtivo dia para voce!" "06:50"
wpp schedule 46999087711 "Ola Eloiza, conforme combinamos, segue o link do material." "19:00"
wpp schedule 46999087711 "Bom dia! Tudo bem com voce?" "amanha 10:00"
wpp schedule 46999087711 "Ola! Passando para confirmar nossa reuniao." "em 30 minutos"
```

### 2. Enviar Mensagem Imediatamente (`wpp send`)
Quando o Salesio pedir para mandar agora / ja / imediatamente:

```bash
# Sintaxe:
wpp send <numero_telefone> "<mensagem_completa>"

# Exemplo:
wpp send 46999087711 "Ola! O relatorio foi concluido com sucesso."
```

### 3. Consultar Mensagens Agendadas (`wpp list`)
Exibe a lista de mensagens na fila de espera com horario previsto e ID:
```bash
wpp list
```

### 4. Cancelar Mensagem Agendada (`wpp cancel`)
Cancela o envio de uma mensagem pendente pelo seu ID:
```bash
wpp cancel <id>
```

---

## Regras Cruciais para o Agente Hermes:
1. **NUNCA use `sleep` nem invente funcoes como `send_message_to_number(...)`.**
2. **Execute SEMPRE o comando `wpp schedule` ou `wpp send` no terminal usando a ferramenta `terminal`.**
3. Se o Salesio pedir uma "mensagem personalizada de bom dia" ou "uma mensagem sobre osteopatia":
   - Crie o texto humanizado e persuasivo.
   - Execute o comando: `wpp schedule <numero> "<texto criado>" "<horario>"`.
4. Apos executar o comando no terminal, confirme para o Salesio mostrando o numero, o horario agendado e o texto que sera entregue.
