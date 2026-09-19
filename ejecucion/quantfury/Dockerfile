FROM python:3.12-slim

RUN pip install --no-cache-dir pandas numpy

WORKDIR /app
COPY . /app

# Persistencia: monta el volumen de Coolify en /app/data, igual que
# ejecucion/paper_trading/ (mismo `CORVUS4_DATA_ROOT` -- una sola
# convencion en todo el proyecto). Los scripts escriben ahi
# (datos_vivos/, estado_paper.json, registro_paper.csv) en vez de en el
# propio codigo copiado por el build, para que un redespliegue no borre
# el historial ni el contador interno.
ENV CORVUS4_DATA_ROOT=/app/data

# Variables de entorno obligatorias en Coolify para que mande avisos:
#   TELEGRAM_TOKEN=...
#   TELEGRAM_CHAT_ID=...   (el ID del chat O GRUPO donde quieres los avisos --
#                           un grupo tiene un chat_id NEGATIVO, ej. -1001234567890;
#                           el codigo no distingue grupo de chat privado, es el
#                           mismo campo. Para conseguirlo: añade el bot al grupo,
#                           manda cualquier mensaje ahi, y lee
#                           https://api.telegram.org/bot<TOKEN>/getUpdates --
#                           el "chat":{"id":...} de ese mensaje es el que va aqui.
#                           El comando /balance funciona igual en un grupo: los
#                           comandos con barra SI llegan a los bots aunque el
#                           grupo tenga el "modo privacidad" activado en BotFather.)
# Si faltan, el bot sigue corriendo pero no manda ni recibe nada por Telegram
# (ver `enviar_telegram`/`leer_actualizaciones` en alertas_telegram.py).

# Corre una vez al arrancar (para ver el aviso de arranque enseguida) y
# luego se ancla SIEMPRE a las 00:05 UTC del dia siguiente -- justo
# despues del cierre de la vela diaria de Binance, que es la asuncion de
# la que depende toda la logica de salidas (ver docstring de bot_paper.py).
# Un `sleep` de duracion fija (ej. 86400s) NO vale aqui: si el contenedor
# se reinicia a media tarde, se quedaria corriendo siempre a esa misma
# hora, mirando la vela de "hoy" todavia sin cerrar en vez de la de ayer
# ya cerrada -- se recalcula la espera cada vuelta contra el reloj real,
# nunca se acumula deriva.
#
# 19-sept-2026: se probo (y se revirtio) una comprobacion adicional cada
# 12h de solo stop-loss/take-profit -- resulto ser inutil en Corvus IV
# porque el usuario coloca el stop-loss/take-profit como orden REAL en
# QuantFury al abrir la posicion, y la propia plataforma la ejecuta al
# instante sin ayuda del bot. Una vez al dia sigue siendo lo correcto
# para todo lo demas (entradas + las 6 mecanicas de salida) -- verlo mas
# a menudo no generaliza, ver laboratorio/patrones/pendiente_acelerada_4h.py.
CMD ["sh", "-c", "python3 ejecucion/quantfury/bot_paper.py; while true; do \
    python3 -c \"import time, datetime; ahora = datetime.datetime.now(datetime.timezone.utc); proxima = (ahora + datetime.timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0); time.sleep((proxima - ahora).total_seconds())\"; \
    python3 ejecucion/quantfury/bot_paper.py; \
done"]
