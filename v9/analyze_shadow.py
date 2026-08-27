"""
V9 — Análisis del log shadow.

Lee data/v9_shadow.jsonl y muestra:
  - Cuántos trades V8 habría hecho vs V9 habría bloqueado
  - Cuántos TP V9 habría ajustado vs V8
  - A qué precio cerró el mercado después (para saber si el bloqueo fue correcto)

Uso:
    python v9/analyze_shadow.py
    python v9/analyze_shadow.py --log data/v9_shadow.jsonl
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default=str(ROOT / "data" / "v9_shadow.jsonl"))
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"Log no encontrado: {log_path}")
        sys.exit(1)

    records = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print("Log vacío — sin datos aún.")
        return

    blocked    = [r for r in records if r["event"] == "BLOCKED"]
    adjusted   = [r for r in records if r["event"] == "TP_ADJUSTED"]
    passed     = [r for r in records if r["event"] == "PASS"]

    total_signals = len(blocked) + len(adjusted) + len(passed)

    print(f"\n{'='*60}")
    print(f"  V9 SHADOW ANALYSIS — {len(records)} registros")
    print(f"{'='*60}")
    print(f"  Señales totales:     {total_signals}")
    print(f"  Sin diferencia:      {len(passed)}  ({len(passed)/total_signals*100:.1f}%)")
    print(f"  TP ajustado:         {len(adjusted)}  ({len(adjusted)/total_signals*100:.1f}%)")
    print(f"  Trade bloqueado:     {len(blocked)}  ({len(blocked)/total_signals*100:.1f}%)")

    if blocked:
        print(f"\n── TRADES BLOQUEADOS ──")
        for r in blocked[-10:]:  # últimos 10
            print(f"  {r['ts'][:16]} | {r['pair']} {r['side'].upper()} @ {r['entry_price']:,.0f}"
                  f"  | Muro {r['wall_price']:,.0f} ({r['wall_notional']/1e6:.1f}M)"
                  f"  | {r['reason']}")

    if adjusted:
        print(f"\n── TP AJUSTADOS ──")
        for r in adjusted[-10:]:
            pct = (r['adjusted_tp'] - r['original_tp']) / r['original_tp'] * 100
            print(f"  {r['ts'][:16]} | {r['pair']} {r['side'].upper()} @ {r['entry_price']:,.0f}"
                  f"  | TP {r['original_tp']:,.0f} → {r['adjusted_tp']:,.0f} ({pct:+.1f}%)"
                  f"  | Muro {r['wall_price']:,.0f} ({r['wall_notional']/1e6:.1f}M)")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
