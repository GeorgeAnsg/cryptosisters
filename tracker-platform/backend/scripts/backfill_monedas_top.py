"""Backfill de monedas_top para candidatos descubiertos ANTES de que esa
columna existiera (migracion 9961eb7, 20-oct-2026): sin esto se quedarian sin
tags hasta que les tocase su turno en el ciclo semanal de no-seguidos.
Usa el operaciones_recientes YA GUARDADO (sin pedir nada a Hyperliquid) --
es un recorte de los ultimos ~2000 fills, no el año completo que usa el
calculo normal, así que es una aproximacion razonable para un backfill
puntual, no un reemplazo del calculo real (que se sigue haciendo en cada
refresco diario/semanal con el año completo de verdad)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import database as db
from app.services import hyperliquid


def main():
    with db.conectar() as conn:
        filas = conn.execute("SELECT address, operaciones_recientes, posicion_actual, holdings_spot FROM candidatos WHERE monedas_top='[]' OR monedas_top IS NULL").fetchall()
        spot_nombres = hyperliquid.cargar_spot_meta()
        actualizados = 0
        for f in filas:
            ops = json.loads(f["operaciones_recientes"] or "[]")
            pa = json.loads(f["posicion_actual"] or "[]")
            hs = json.loads(f["holdings_spot"] or "[]")
            monedas_top = hyperliquid.monedas_mas_usadas(ops, pa, hs, spot_nombres)
            if monedas_top:
                conn.execute("UPDATE candidatos SET monedas_top=? WHERE address=?", (json.dumps(monedas_top, ensure_ascii=False), f["address"]))
                actualizados += 1
        conn.commit()
        print(f"{actualizados}/{len(filas)} candidatos backfilled")


if __name__ == "__main__":
    main()
