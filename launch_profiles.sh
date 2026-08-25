#!/bin/bash
# Lanza el bot en paper trading para múltiples pares en paralelo.
# Todos usan sentimiento de BTC como proxy de mercado.
# Parámetros: ganador del optimizer (ms=55 sl=1.5 tp=4.0 ea=10 regime=bull)
#
# Uso:          bash launch_profiles.sh
# Comparar:     python3 compare_profiles.py --watch
# Detener todo: pkill -f 'trading_bot_v3.py'

# Activar entorno virtual
source "$(dirname "$0")/venv/bin/activate"

TIMEFRAME="15m"
INTERVAL=60   # segundos entre ciclos
MS=55; SL=1.5; TP=4.0; EA=10; REGIME=bull

echo "Lanzando bots para 6 pares..."
echo "Logs: paper_*.log  |  Estados: paper_*_state.json"
echo "Para comparar: python3 compare_profiles.py --watch"
echo ""

python3 trading_bot_v3.py \
  --pair BTC/USDT --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name btc \
  > /dev/null 2>&1 &
echo "  [PID $!] BTC/USDT"

python3 trading_bot_v3.py \
  --pair ETH/USDT --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name eth \
  > /dev/null 2>&1 &
echo "  [PID $!] ETH/USDT"

python3 trading_bot_v3.py \
  --pair SOL/USDT --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name sol \
  > /dev/null 2>&1 &
echo "  [PID $!] SOL/USDT"

python3 trading_bot_v3.py \
  --pair HYPE/USDT --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name hype \
  > /dev/null 2>&1 &
echo "  [PID $!] HYPE/USDT"

python3 trading_bot_v3.py \
  --pair AAVE/USDT --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name aave \
  > /dev/null 2>&1 &
echo "  [PID $!] AAVE/USDT"

python3 trading_bot_v3.py \
  --pair XRP/USDT --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name xrp \
  > /dev/null 2>&1 &
echo "  [PID $!] XRP/USDT"

echo ""
echo "Todos arrancados. Para ver comparativa:"
echo "  python3 compare_profiles.py --watch"
