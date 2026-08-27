#!/usr/bin/env bash
# launch.sh — arranca los bots de trading v6
# Uso: ./v6/launch.sh [--dry-run]
#
# Bots que lanza:
#   - BTC/USDT:USDT intraday  (15m, conservative)
#   - BTC/USDT:USDT intraday  (15m, aggressive)
#   - ETH/USDT:USDT intraday  (15m, conservative)
#   - ETH/USDT:USDT intraday  (15m, aggressive)
#   - BTC/USDT:USDT swing     (1h,  conservative)
#   - BTC/USDT:USDT swing     (1h,  aggressive)
#
# Arranque escalonado: 30s entre cada bot.
# Logs: ./logs/v6/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$ROOT_DIR/logs/v6"
mkdir -p "$LOG_DIR"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "[dry-run] Solo mostrando comandos, sin ejecutar."
fi

launch_bot() {
    local name="$1"; shift
    local cmd="$*"
    local logfile="$LOG_DIR/${name}.log"

    echo "Iniciando $name → $logfile"
    if [ "$DRY_RUN" = true ]; then
        echo "  [dry-run] $cmd"
    else
        nohup bash -c "$cmd >> '$logfile' 2>&1" &
        echo "  PID: $!"
    fi
}

PYTHON="${PYTHON:-python}"
V6_MOD="$ROOT_DIR"   # directorio raíz para que los imports v6.* funcionen

cd "$V6_MOD"

# --- INTRADAY ---
launch_bot "btc_intraday_conservative" \
    "$PYTHON -m v6.main --pair BTC/USDT:USDT --strategy 15m --profile moderate"
sleep 30

launch_bot "btc_15m_aggressive" \
    "$PYTHON -m v6.main --pair BTC/USDT:USDT --strategy 15m --profile aggressive"
sleep 30

launch_bot "eth_15m_moderate" \
    "$PYTHON -m v6.main --pair ETH/USDT:USDT --strategy 15m --profile moderate"
sleep 30

launch_bot "eth_15m_aggressive" \
    "$PYTHON -m v6.main --pair ETH/USDT:USDT --strategy 15m --profile aggressive"
sleep 30

# --- 1h ---
launch_bot "btc_1h_moderate" \
    "$PYTHON -m v6.main --pair BTC/USDT:USDT --strategy 1h --profile moderate"
sleep 30

launch_bot "btc_1h_aggressive" \
    "$PYTHON -m v6.main --pair BTC/USDT:USDT --strategy 1h --profile aggressive"

echo ""
echo "Todos los bots arrancados. Logs en: $LOG_DIR"
