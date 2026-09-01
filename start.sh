#!/bin/bash
# Arranca V12 (live) y V12 shadow con desfase para evitar sobrecarga al inicio.
# V12 es el proceso principal — si muere, el contenedor sale y Coolify lo reinicia.
# V12 shadow es secundario — si falla, el contenedor sigue vivo (solo deja de logear).

echo "[start] Arrancando V14 live (BTC+ETH+LINK+AAVE+INJ, modo QuantFury)..."
python -m v12.main &
MAIN_PID=$!

echo "[start] Esperando 30s antes de arrancar V12 shadow..."
sleep 30

echo "[start] Arrancando V14 shadow (heatmap filter)..."
python -m v12.shadow &

echo "[start] PID principal=$MAIN_PID — esperando..."

# Esperar proceso principal. Si termina (crash o parada), Coolify reinicia el contenedor.
wait $MAIN_PID
exit $?
