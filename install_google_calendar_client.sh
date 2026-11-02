#!/bin/bash
# ==============================================================================
# Script de Instalação e Configuração Automática do Google Calendar no Hermes
# Desenvolvido por: Salesio Ninja & Antigravity
# Uso: bash install_google_calendar_client.sh [email_cliente] [caminho_chave_json]
# ==============================================================================

set -e

DATA_DIR="/opt/hermes-agent/data"
COMPOSE_FILE="/opt/hermes-agent/docker-compose.yml"
ENV_FILE="$DATA_DIR/.env"

echo "=================================================================="
echo "🚀 INSTALADOR AUTOMÁTICO GOOGLE CALENDAR PARA HERMES AGENT"
echo "=================================================================="

# 1. Obter e-mail da agenda do cliente
CLIENT_EMAIL="$1"
if [ -z "$CLIENT_EMAIL" ]; then
    read -p "👉 Informe o e-mail da Google Agenda do Cliente (ex: cliente@gmail.com): " CLIENT_EMAIL
fi

if [ -z "$CLIENT_EMAIL" ]; then
    echo "❌ Erro: O e-mail da agenda é obrigatório."
    exit 1
fi

# 2. Obter caminho da chave JSON
KEY_PATH="$2"
if [ -z "$KEY_PATH" ]; then
    read -p "👉 Informe o caminho da chave JSON da Service Account (ex: /root/chave.json): " KEY_PATH
fi

if [ ! -f "$KEY_PATH" ]; then
    echo "❌ Erro: Arquivo de chave não encontrado em: $KEY_PATH"
    exit 1
fi

echo "📦 1. Configurando permissões da chave Service Account..."
if [ "$(realpath "$KEY_PATH" 2>/dev/null || echo "$KEY_PATH")" != "$(realpath "$DATA_DIR/service_account.json" 2>/dev/null || echo "$DATA_DIR/service_account.json")" ]; then
    cp "$KEY_PATH" "$DATA_DIR/service_account.json"
fi
chmod 644 "$DATA_DIR/service_account.json"
echo "   Chave pronta em $DATA_DIR/service_account.json (chmod 644)."

echo "📦 2. Configurando o executável 'agenda' e o motor Python..."
mkdir -p "$DATA_DIR/.local/bin"
mkdir -p "$DATA_DIR/skills/google-calendar"

cat << 'EOF' > "$DATA_DIR/.local/bin/agenda"
#!/bin/bash
exec /opt/hermes/.venv/bin/python /opt/data/hermes_calendar.py "$@"
EOF
chmod +x "$DATA_DIR/.local/bin/agenda"
chmod +x "$DATA_DIR/hermes_calendar.py"

echo "📦 3. Atualizando variáveis de ambiente (.env)..."
touch "$ENV_FILE"
grep -q "HERMES_CALENDAR_ID=" "$ENV_FILE" && sed -i "s|HERMES_CALENDAR_ID=.*|HERMES_CALENDAR_ID=$CLIENT_EMAIL|" "$ENV_FILE" || echo "HERMES_CALENDAR_ID=$CLIENT_EMAIL" >> "$ENV_FILE"
grep -q "HERMES_GOOGLE_KEY=" "$ENV_FILE" && sed -i "s|HERMES_GOOGLE_KEY=.*|HERMES_GOOGLE_KEY=/opt/data/service_account.json|" "$ENV_FILE" || echo "HERMES_GOOGLE_KEY=/opt/data/service_account.json" >> "$ENV_FILE"

echo "📦 4. Verificando montagens no docker-compose.yml..."
if [ -f "$COMPOSE_FILE" ]; then
    if ! grep -q "/usr/local/bin/agenda" "$COMPOSE_FILE"; then
        echo "   Injetando montagem do executável agenda no docker-compose.yml..."
        sed -i '/\/opt\/data/a \      - /opt/hermes-agent/data/.local/bin/agenda:/usr/local/bin/agenda:ro\n      - /opt/hermes-agent/data/.local/bin/agenda:/usr/bin/agenda:ro' "$COMPOSE_FILE"
        docker stack deploy -c "$COMPOSE_FILE" hermes >/dev/null 2>&1 || true
    fi
fi

# Garantir symlinks dentro do container ativo atual
CONTAINER_ID=$(docker ps -q --filter name=hermes_hermes | head -n 1)
if [ -n "$CONTAINER_ID" ]; then
    docker exec "$CONTAINER_ID" ln -sf /opt/data/.local/bin/agenda /usr/local/bin/agenda 2>/dev/null || true
    docker exec "$CONTAINER_ID" ln -sf /opt/data/.local/bin/agenda /usr/bin/agenda 2>/dev/null || true
    docker exec "$CONTAINER_ID" ln -sf /opt/data/.local/bin/agenda /opt/hermes/bin/agenda 2>/dev/null || true
fi

echo "🔍 5. Testando conexão com a Google Agenda do Cliente..."
sleep 3
TEST_OUTPUT=$(docker exec --user hermes "$CONTAINER_ID" agenda list hoje 2>&1 || true)

if echo "$TEST_OUTPUT" | grep -q "Agenda Google"; then
    echo "=================================================================="
    echo "✅ SUCESSO! A INTEGRAÇÃO COM O GOOGLE CALENDAR ESTÁ 100% ATIVA!"
    echo "Agenda vinculada: $CLIENT_EMAIL"
    echo "Resultado do teste:"
    echo "$TEST_OUTPUT"
    echo "=================================================================="
else
    echo "⚠️ ATENÇÃO: O comando rodou mas retornou o seguinte aviso:"
    echo "$TEST_OUTPUT"
    echo ""
    echo "👉 Verifique se o e-mail da Service Account (ex: hermes-agenda@...iam.gserviceaccount.com)"
    echo "   foi adicionado na agenda $CLIENT_EMAIL com a permissão 'Fazer alterações nos eventos'."
fi
