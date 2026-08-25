"""
Resumen diario de todos los bots en papel — envía tabla por Telegram.
Se ejecuta como proceso independiente en segundo plano desde launch_profiles.sh.

Comportamiento:
- Envía resumen a la hora configurada (SUMMARY_HOUR, por defecto 20 UTC)
- Corre indefinidamente en un bucle de 60s
- Lee todos los paper_*_state.json del STATE_DIR

Uso:
    python3 daily_summary.py
    SUMMARY_HOUR=8 python3 daily_summary.py
"""

import json
import os
import time
import requests
from pathlib import Path
from datetime import datetime, timezone


STATE_DIR    = Path(os.environ.get("STATE_DIR", "."))
SUMMARY_HOUR = int(os.environ.get("SUMMARY_HOUR", "20"))  # hora UTC para enviar


def _tg(text: str):
    token   = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print(text)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"[daily_summary] Telegram error: {e}")


def build_summary() -> str:
    states = sorted(STATE_DIR.glob("paper_*_state.json"))
    if not states:
        return "📊 No hay bots activos (ningún paper_*_state.json encontrado)"

    lines = [
        f"📊 <b>Resumen Diario</b> — {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC",
        "",
    ]

    total_pnl    = 0.0
    open_pos     = 0
    total_trades = 0
    wins_total   = 0

    for sf in states:
        try:
            state = json.loads(sf.read_text())
        except Exception:
            continue

        name   = sf.stem.replace("paper_", "").replace("_state", "")
        stats  = state.get("stats", {})
        pnl    = stats.get("total_pnl", 0.0)
        wins   = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        trades = wins + losses
        wr     = wins / trades * 100 if trades else 0.0
        pos    = state.get("position")

        pos_str  = f"📍{pos['side'].upper()}" if pos else "—"
        pnl_icon = "🟢" if pnl >= 0 else "🔴"
        lines.append(
            f"{pnl_icon} <b>{name}</b>: {pnl:+.2f}$ | WR:{wr:.0f}% ({trades}t) | {pos_str}"
        )

        total_pnl    += pnl
        total_trades += trades
        wins_total   += wins
        if pos:
            open_pos += 1

    global_wr   = wins_total / total_trades * 100 if total_trades else 0.0
    total_icon  = "🟢" if total_pnl >= 0 else "🔴"
    lines += [
        "",
        f"{total_icon} <b>TOTAL PnL: {total_pnl:+.2f} USDT</b>",
        f"   WR global: {global_wr:.1f}% | Trades: {total_trades} | Posiciones abiertas: {open_pos}",
    ]
    return "\n".join(lines)


def main():
    print(f"[daily_summary] Arrancado. Resumen a las {SUMMARY_HOUR}:00 UTC. STATE_DIR={STATE_DIR}")
    sent_today = None

    while True:
        now = datetime.now(timezone.utc)
        today = now.date()

        if now.hour == SUMMARY_HOUR and now.minute < 5 and sent_today != today:
            summary = build_summary()
            _tg(summary)
            print(f"[daily_summary] Resumen enviado: {today}")
            sent_today = today

        time.sleep(60)


if __name__ == "__main__":
    main()
