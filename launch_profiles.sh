#!/bin/bash
# Lanza el bot en paper trading para múltiples pares en paralelo.
# Todos usan sentimiento de BTC como proxy de mercado.
# Parámetros: ganador del optimizer (ms=55 sl=1.5 tp=4.0 ea=10 regime=bull)
#
# Uso:          bash launch_profiles.sh
# Comparar:     python3 compare_profiles.py --watch
# Detener todo: pkill -f 'trading_bot_v3.py'

# En Docker: STATE_DIR=/app/data (volumen persistente). En local: directorio actual.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${STATE_DIR:-$SCRIPT_DIR}"
mkdir -p "$STATE_DIR"
cd "$STATE_DIR"

BOT="python3 $SCRIPT_DIR/trading_bot_v4.py"
TIMEFRAME="15m"
INTERVAL=60
MS=55; SL=1.5; TP=4.0; EA=10; REGIME=bull

echo "Lanzando bots para 6 pares..."
echo "Logs: $STATE_DIR/paper_*.log"
echo "Para comparar: python3 compare_profiles.py --watch"
echo ""

$BOT --pair BTC/USDT  --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name btc  > /dev/null 2>&1 &
echo "  [PID $!] BTC/USDT"

$BOT --pair ETH/USDT  --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name eth  > /dev/null 2>&1 &
echo "  [PID $!] ETH/USDT"

$BOT --pair SOL/USDT  --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name sol  > /dev/null 2>&1 &
echo "  [PID $!] SOL/USDT"

$BOT --pair HYPE/USDT --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name hype > /dev/null 2>&1 &
echo "  [PID $!] HYPE/USDT"

$BOT --pair AAVE/USDT --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name aave > /dev/null 2>&1 &
echo "  [PID $!] AAVE/USDT"

$BOT --pair XRP/USDT  --timeframe $TIMEFRAME --interval $INTERVAL \
  --regime $REGIME --min-score $MS --stop-loss $SL --take-profit $TP \
  --entry-advantage $EA --name xrp  > /dev/null 2>&1 &
echo "  [PID $!] XRP/USDT"

echo ""
echo "Todos arrancados."

# Notificación Telegram de arranque
if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_CHAT_ID}" \
    -d parse_mode="HTML" \
    -d text="🟢 <b>Bot v4 arrancado</b>
6 pares activos: BTC · ETH · SOL · HYPE · AAVE · XRP
Régimen: auto (EMA20/50 diarias) | ms=55 sl=1.5x tp=4.0x
Nuevo: HTF activo · doble techo/suelo · canal · funding · order book
Esperando señales..." > /dev/null
fi

# Mantener el proceso vivo (necesario en Docker)
wait
