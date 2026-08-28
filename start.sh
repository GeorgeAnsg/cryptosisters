#!/bin/bash
# Arranca V8 (live) y V9 (shadow) con desfase para evitar sobrecarga al inicio.
# V8 es el proceso principal — si muere, el contenedor sale y Coolify lo reinicia.
# V9 shadow es secundario — si falla, el contenedor sigue vivo (solo deja de logear).

echo "[start] Arrancando V10 live..."
python -m v10.main &
V8_PID=$!

echo "[start] Esperando 30s antes de arrancar V9 shadow..."
sleep 30

echo "[start] Arrancando V9 shadow..."
python -m v9.main &

echo "[start] V8 PID=$V8_PID — esperando..."

# Esperar V8. Si V8 termina (crash o parada), el script termina
# y Coolify reinicia el contenedor completo.
wait $V8_PID
exit $?
