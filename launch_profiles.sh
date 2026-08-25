#!/bin/bash
# launch_profiles.sh — 18 bots en paralelo (6 pares × 3 perfiles) + resumen diario
# Params optimizados para BULL MARKET (optimizer oct 2023 – mar 2024)
#
# Perfiles y parámetros:
#   conservative : MS=50 EA=10 SL=2.5 TP=3.0
#   moderate     : MS=50 EA=10 SL=2.5 TP=3.0
#   aggressive   : MS=50 EA=25 SL=2.5 TP=5.0
#
# Uso:
#   ./launch_profiles.sh              # bull market (por defecto)
#   REGIME=bear ./launch_profiles.sh  # bear market

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT="python3 $SCRIPT_DIR/trading_bot_v4.py"

REGIME="${REGIME:-auto}"   # auto = detecta bull/bear por EMA diaria

# 6 pares más líquidos en Bybit
PAIRS=("BTC/USDT" "ETH/USDT" "SOL/USDT" "BNB/USDT" "XRP/USDT" "DOGE/USDT")

# Parámetros por perfil (bull market optimized)
declare -A MS=([conservative]=50  [moderate]=50  [aggressive]=50)
declare -A EA=([conservative]=10  [moderate]=10  [aggressive]=25)
declare -A SL=([conservative]=2.5 [moderate]=2.5 [aggressive]=2.5)
declare -A TP=([conservative]=3.0 [moderate]=3.0 [aggressive]=5.0)

PROFILES=("conservative" "moderate" "aggressive")

echo "============================================================"
echo "  🚀 Lanzando 18 bots — Régimen: $REGIME"
echo "  Pares: ${PAIRS[*]}"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================================"

# Notificación de arranque por Telegram
if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
    python3 - <<'PYEOF'
import os, requests
token   = os.environ["TELEGRAM_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]
msg = (
    "🤖 <b>Bot v4 arrancado — 18 bots en paralelo</b>\n"
    "📊 6 pares × 3 perfiles (conservative / moderate / aggressive)\n"
    "⚡ Régimen: " + os.environ.get("REGIME", "auto") + "\n"
    "🔔 Resumen diario a las 20:00 UTC\n"
    "Funcionalidades activas:\n"
    "  • HTF 4h scoring\n"
    "  • Doble techo / doble suelo\n"
    "  • Canal de precio\n"
    "  • Funding rate\n"
    "  • Order book walls\n"
    "  • Auto-régimen (EMA20/50 diaria)\n"
    "  • Modo silencioso (resumen diario)"
)
requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
    timeout=10
)
PYEOF
fi

# Lanzar los 18 bots en paralelo (--silent: sin notificaciones por trade)
for PAIR in "${PAIRS[@]}"; do
    PAIR_SLUG="${PAIR/\//_}"   # BTC/USDT → BTC_USDT
    for PROFILE in "${PROFILES[@]}"; do
        NAME="${PAIR_SLUG}_${PROFILE}"
        CMD="$BOT \
            --pair $PAIR \
            --risk $PROFILE \
            --regime $REGIME \
            --min-score ${MS[$PROFILE]} \
            --entry-advantage ${EA[$PROFILE]} \
            --stop-loss ${SL[$PROFILE]} \
            --take-profit ${TP[$PROFILE]} \
            --name $NAME \
            --silent"
        echo "▶  $NAME"
        eval "$CMD" >> "${STATE_DIR:-.}/${NAME}.log" 2>&1 &
    done
done

# Resumen diario independiente
echo "▶  daily_summary (20:00 UTC)"
python3 "$SCRIPT_DIR/daily_summary.py" >> "${STATE_DIR:-.}/daily_summary.log" 2>&1 &

echo ""
echo "✅ 19 procesos lanzados (18 bots + 1 resumen diario)"
echo "   Logs en: ${STATE_DIR:-.}/"
echo "   Para ver todos: tail -f ${STATE_DIR:-.}/BTC_USDT_aggressive.log"

# Espera a que terminen (o Ctrl+C para parar todos)
wait
