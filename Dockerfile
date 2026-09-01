FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código fuente
COPY v6/ ./v6/
COPY v7/ ./v7/
COPY v8/ ./v8/
COPY v9/ ./v9/
COPY v10/ ./v10/
COPY v11/ ./v11/
COPY v12/ ./v12/
COPY v13/ ./v13/
COPY v14/ ./v14/

# Script de arranque (V12 live + V12 shadow con 30s de desfase)
COPY start.sh ./start.sh
RUN chmod +x start.sh

# Datos de miedo/avaricia y otros auxiliares
COPY data/fear_greed_historical.json ./data/
COPY data/funding_rate_historical.csv ./data/

# Estados y logs van a /app/data (montado como volumen persistente en Coolify)
ENV STATE_DIR=/app/data

# Variables de entorno obligatorias (definir en Coolify):
# BYBIT_API_KEY, BYBIT_API_SECRET
# TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
# HEATMAP_URL  — URL base del endpoint de orderbook heatmap
#                ej: http://tu0mtnondcwqlyno8q2ewx5p.46.224.182.44.sslip.io
# WALL_MIN_NOTIONAL — notional mínimo para considerar muro (default: 1000000)
# EXCHANGE_MODE     — quantfury (default) | bybit
# QUANTFURY_DEPOSIT — euros depositados en QuantFury (default: 100)
# QUANTFURY_RISK_PCT— % del depósito a arriesgar por trade (default: 2)

CMD ["bash", "start.sh"]
