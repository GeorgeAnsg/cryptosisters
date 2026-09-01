#!/bin/bash
# Arranca V14 (live) y V14 shadow con desfase para evitar sobrecarga al inicio.
# V14 es el proceso principal — si muere, el contenedor sale y Coolify lo reinicia.
# V14 shadow es secundario — si falla, el contenedor sigue vivo (solo deja de logear).

echo "[start] Arrancando V14 live (BTC+ETH+LINK+AAVE+INJ, modo QuantFury)..."
python -u -m v12.main 2>&1 &
MAIN_PID=$!

echo "[start] Esperando 30s antes de arrancar V14 shadow..."
sleep 30

echo "[start] Arrancando V14 shadow (heatmap filter)..."
python -u -m v12.shadow 2>&1 &

echo "[start] PID principal=$MAIN_PID — esperando..."

# Esperar proceso principal. Si termina (crash o parada), Coolify reinicia el contenedor.
wait $MAIN_PID
exit $?
