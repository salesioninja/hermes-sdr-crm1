# 🚀 GUIA DEFINITIVO: Como Ativar a Google Agenda no Hermes para Novos Clientes em Escala

Este guia documenta o padrão oficial da integração **Hermes Agent + Google Calendar** desenvolvido para máxima estabilidade, segurança e velocidade de implantação em escala comercial.

---

## 💡 O Grande Segredo para Escalar Rápido (Onboarding em 30 Segundos):

> [!TIP]
> **Você NÃO precisa criar um projeto no Google Cloud para cada novo cliente!**
> A mesma conta de serviço (**Service Account**) que criamos (`hermes-agenda@hermes-vps-suporte1.iam.gserviceaccount.com`) pode gerenciar a agenda de **quantos clientes você quiser**.

### Como funciona para um Novo Cliente:
1. Você pede o e-mail Google do cliente (ex: `cliente@gmail.com` ou `contato@empresa.com.br`).
2. O cliente entra no Google Agenda dele e compartilha a agenda principal com:
   `hermes-agenda@hermes-vps-suporte1.iam.gserviceaccount.com`
   com permissão: **"Fazer alterações nos eventos"**.
3. Na VPS do cliente, você roda o instalador automático:
   ```bash
   bash install_google_calendar_client.sh "cliente@gmail.com" "/opt/hermes-agent/data/service_account.json"
   ```
4. **Pronto!** O Hermes do cliente já passa a consultar, agendar, reagendar e cancelar compromissos instantaneamente no WhatsApp e no Painel Web.

---

## 📦 Arquitetura Blindada (Por que nunca mais vai quebrar):

1. **Permissões de Arquivo (`chmod 644`):**
   * O arquivo `service_account.json` fica com permissão de leitura para o usuário `hermes` (UID 10000). Não ocorre mais o erro `Permission denied`.
2. **Auto-injeção de dependências no Python:**
   * O script `hermes_calendar.py` injeta no topo do código os caminhos dos pacotes instalados no ambiente virtual do Hermes (`/opt/hermes/.venv/lib/python3.14/site-packages`).
   * Não importa se o Hermes executa `agenda`, `python3`, ou `/opt/data/hermes_calendar.py`: o Google API Client é sempre carregado com sucesso.
3. **Persistência Global no Sistema (`docker-compose.yml`):**
   * O executável `agenda` está mapeado nos volumes do `docker-compose.yml` para `/usr/local/bin/agenda:ro` e `/usr/bin/agenda:ro`. Mesmo que o container seja reiniciado, atualizado ou recriado, o comando permanece no `PATH` padrão do Linux.
4. **Instruções no SOUL.md e instructions.md:**
   * O agente tem regras rígidas separando **Agenda Google** de **Lembretes rápidos (`lembretes.md`)**, eliminando qualquer confusão ou resposta desnecessária no WhatsApp.

---

## 🛠️ Comandos Disponíveis no Terminal do Hermes

| Comando | Descrição | Exemplo |
| :--- | :--- | :--- |
| `agenda list hoje` | Lista todos os eventos de hoje (00h às 23h59) | `agenda list hoje` |
| `agenda list amanha` | Lista os eventos do dia seguinte | `agenda list amanha` |
| `agenda list 7` | Lista os próximos N dias | `agenda list 7` |
| `agenda add` | Cria compromisso com trava anti-conflito | `agenda add "Apresentação Lead" "14:30" hoje 45` |
| `agenda move` | Muda o horário de um evento existente sem duplicar | `agenda move "Apresentação Lead" "16:00" hoje` |
| `agenda del` | Exclui evento por nome/horário ou por ID | `agenda del "Apresentação Lead" hoje` |

---

## 📋 Checklist de Deploy para Novo Cliente (1 Minuto)

1. **Obter Chave:** Usar o mesmo `service_account.json` mestre.
2. **Pedir Acesso:** Cliente adiciona `hermes-agenda@hermes-vps-suporte1.iam.gserviceaccount.com` na Google Agenda dele.
3. **Executar na VPS do Cliente:**
   ```bash
   cd /opt/hermes-agent/data
   bash install_google_calendar_client.sh "email_do_cliente@gmail.com" "service_account.json"
   ```
4. **Validar no WhatsApp do Cliente:**
   * Digite `/new` no WhatsApp do cliente.
   * Pergunte: *"O que eu tenho para hoje na agenda?"*.
