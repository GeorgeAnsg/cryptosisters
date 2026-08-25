FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY trading_bot_v3.py compare_profiles.py launch_profiles.sh news_btc_1y.json ./

RUN chmod +x launch_profiles.sh

# Variables de entorno obligatorias (definir en Coolify):
# TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

CMD ["bash", "launch_profiles.sh"]
