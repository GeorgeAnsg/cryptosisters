FROM python:3.12-slim

RUN pip install --no-cache-dir pandas pandas_ta numpy tzdata

WORKDIR /app
COPY . /app

# Persistencia: monta el volumen de Coolify en /app/data. Los scripts
# escriben ahi (datos_vivos/ y logs/ dentro) en vez de en el propio
# codigo copiado por el build, para que un redespliegue no borre el
# historial acumulado.
ENV CORVUS4_DATA_ROOT=/app/data

# Notificaciones de Telegram (opcional): si no se definen estas dos vars
# de entorno en Coolify, notificar_resumen.py simplemente no envia nada
# y no falla.
#   TELEGRAM_TOKEN=...
#   TELEGRAM_CHAT_ID=...

# Aviso de arranque una vez, luego bucle: corre los tres ciclos (12 cripto
# + oro + 3 acciones) cada 4 horas, y tras cada vuelta comprueba si toca
# mandar el resumen nocturno. No expone ningun puerto -- no es un servicio
# web, es un bucle de fondo.
CMD ["sh", "-c", "python3 ejecucion/paper_trading/notificar_resumen.py --inicio; while true; do \
    python3 ejecucion/paper_trading/bot_grid_papel.py; \
    python3 ejecucion/paper_trading/bot_grid_papel_oro.py; \
    python3 ejecucion/paper_trading/bot_grid_papel_acciones.py; \
    python3 ejecucion/paper_trading/notificar_resumen.py; \
    sleep 14400; \
done"]
