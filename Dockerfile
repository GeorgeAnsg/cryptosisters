FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY trading_bot_v3.py trading_bot_v4.py compare_profiles.py launch_profiles.sh news_btc_1y.json ./

RUN chmod +x launch_profiles.sh && mkdir -p /app/data

# Estados y logs van a /app/data (montado como volumen persistente en Coolify)
ENV STATE_DIR=/app/data

# Variables de entorno obligatorias (definir en Coolify):
# TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

CMD ["bash", "launch_profiles.sh"]
