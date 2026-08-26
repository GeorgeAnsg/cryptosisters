#!/bin/bash
# launch_profiles.sh — 6 bots (BTC + ETH + HYPE) × (moderate + aggressive)
# Params optimizados para BULL MARKET
# v5: grid bot automatico cuando auto-regimen detecta mercado neutral/lateral
#
# moderate   : MS=50 EA=25 SL=1.5 TP=3.0
# aggressive : MS=45 EA=25 SL=2.0 TP=4.0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT="python3 $SCRIPT_DIR/trading_bot_v4.py"
REGIME="${REGIME:-auto}"
PAIRS=("BTC/USDT" "ETH/USDT" "HYPE/USDT")
PROFILES=("moderate" "aggressive")

declare -A MS=([moderate]=50  [aggressive]=45)
declare -A EA=([moderate]=25  [aggressive]=25)
declare -A SL=([moderate]=1.5 [aggressive]=2.0)
declare -A TP=([moderate]=3.0 [aggressive]=4.0)

# Limpieza de archivos de bots anteriores (pares ya no usados)
DATA_DIR="${STATE_DIR:-.}"
echo "🧹 Limpiando archivos antiguos en $DATA_DIR..."
find "$DATA_DIR" -maxdepth 1 -name "paper_*.json" -o -name "paper_*.log" \
    -o -name "*.log" ! -name "daily_summary.log" | while read f; do
    echo "   Borrando: $(basename $f)"
    rm -f "$f"
done

echo "============================================================"
echo "  🚀 Lanzando 6 bots — Régimen: $REGIME"
echo "  BTC/USDT + ETH/USDT + HYPE/USDT × moderate + aggressive"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================================"

if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
    python3 - <<'PYEOF'
import os, requests
token   = os.environ["TELEGRAM_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]
msg = (
    "🤖 <b>Bot v5 arrancado — 6 bots</b>\n"
    "📊 BTC · ETH · HYPE/USDT × moderate + aggressive\n"
    "⚡ Régimen: " + os.environ.get("REGIME", "auto") + "\n"
    "🔔 Resumen diario a las 20:00 UTC\n"
    "Funcionalidades: HTF 4h · Doble techo/suelo · Canal · Funding · OB · Auto-régimen · Grid bot"
)
requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
    timeout=10
)
PYEOF
fi

# Arranque escalonado: 30s entre cada bot para no saturar CPU/RAM
BOT_NUM=0
for PAIR in "${PAIRS[@]}"; do
    PAIR_SLUG="${PAIR/\//_}"
    for PROFILE in "${PROFILES[@]}"; do
        NAME="${PAIR_SLUG}_${PROFILE}"
        if [ $BOT_NUM -gt 0 ]; then
            echo "  ⏳ Esperando 30s..."
            sleep 30
        fi
        echo "▶  $NAME"
        # aggressive: notificaciones Telegram activadas; moderate: silencioso
        SILENT_FLAG="--silent"
        [ "$PROFILE" = "aggressive" ] && SILENT_FLAG=""
        (cd "${STATE_DIR:-.}" && $BOT \
            --pair "$PAIR" \
            --risk "$PROFILE" \
            --regime "$REGIME" \
            --min-score "${MS[$PROFILE]}" \
            --entry-advantage "${EA[$PROFILE]}" \
            --stop-loss "${SL[$PROFILE]}" \
            --take-profit "${TP[$PROFILE]}" \
            --name "$NAME" \
            $SILENT_FLAG \
            >> "${STATE_DIR:-.}/${NAME}.log" 2>&1) &
        BOT_NUM=$((BOT_NUM + 1))
    done
done

# Resumen diario a las 20:00 UTC
echo "▶  daily_summary"
python3 "$SCRIPT_DIR/daily_summary.py" >> "${STATE_DIR:-.}/daily_summary.log" 2>&1 &

echo ""
echo "✅ 7 procesos lanzados (6 bots + resumen diario)"
echo "   Arranque completo en ~2.5 min (30s entre bots)"
wait
