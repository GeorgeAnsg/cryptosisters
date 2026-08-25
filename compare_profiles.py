"""
Compara los perfiles de paper trading corriendo en paralelo.

Uso:
    python3 compare_profiles.py
    python3 compare_profiles.py --watch        # se refresca cada 60s
"""

import json
import time
import argparse
from pathlib import Path
from datetime import datetime


def load_profile(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
        return data
    except Exception:
        return None


def format_table(profiles: list[dict]) -> str:
    if not profiles:
        return "  (sin perfiles activos)"

    lines = []
    header = (
        f"  {'Perfil':<22} {'Balance':>9} {'PnL':>9} {'WR%':>6} "
        f"{'Trades':>7} {'Wins':>5} {'Losses':>7} {'Drawdown':>9}"
    )
    sep = "  " + "-" * (len(header) - 2)
    lines.append(header)
    lines.append(sep)

    for p in profiles:
        name   = p["name"]
        state  = p["state"]
        stats  = state.get("stats", {})
        bal    = state.get("balance_usdt", 1000.0)
        pnl    = stats.get("total_pnl", 0)
        wins   = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total  = wins + losses
        wr     = wins / total * 100 if total > 0 else 0
        peak   = state.get("peak_balance", bal)
        dd     = (peak - bal) / peak * 100 if peak > 0 else 0
        lines.append(
            f"  {name:<22} {bal:>9.2f} {pnl:>+9.2f} {wr:>6.1f} "
            f"{total:>7} {wins:>5} {losses:>7} {dd:>8.1f}%"
        )

    lines.append(sep)
    best_pnl = max(profiles, key=lambda x: x["state"].get("stats", {}).get("total_pnl", 0))
    lines.append(f"  Lider actual: {best_pnl['name']}")
    return "\n".join(lines)


def scan_profiles() -> list[dict]:
    profiles = []
    for path in sorted(Path(".").glob("paper_*_state.json")):
        state = load_profile(path)
        if state is None:
            continue
        name = path.stem.removeprefix("paper_").removesuffix("_state")
        # Incluye los parametros del perfil si estan guardados en el estado
        profiles.append({"name": name, "path": str(path), "state": state})
    return profiles


def show_params(profiles: list[dict]) -> str:
    lines = []
    for p in profiles:
        state = p["state"]
        risk  = state.get("risk_profile", {})
        if risk:
            lines.append(
                f"  {p['name']:<22} ms={risk.get('min_score','?')} "
                f"sl={risk.get('stop_loss_atr_mult','?')}x "
                f"tp={risk.get('take_profit_atr_mult','?')}x"
            )
    return "\n".join(lines) if lines else "  (parametros no guardados en estado)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true",
                        help="Refresca cada 60 segundos")
    parser.add_argument("--interval", type=int, default=60,
                        help="Segundos entre refrescos (con --watch)")
    args = parser.parse_args()

    while True:
        profiles = scan_profiles()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n{'='*70}")
        print(f"  TORNEO DE PERFILES — {now}")
        print(f"  {len(profiles)} perfil(es) activo(s)")
        print(f"{'='*70}")
        print(format_table(profiles))

        if not args.watch:
            break

        print(f"\n  (Refrescando en {args.interval}s — Ctrl+C para salir)")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n  Saliendo.")
            break


if __name__ == "__main__":
    main()
