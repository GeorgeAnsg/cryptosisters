import json
from pathlib import Path

import db

SEED_PATH = Path(__file__).parent / "seed_data.json"


def sembrar_si_vacio():
    conn = db.conectar()
    hay_datos = conn.execute("SELECT 1 FROM candidatos LIMIT 1").fetchone()
    if hay_datos or not SEED_PATH.exists():
        conn.close()
        return

    seed = json.loads(SEED_PATH.read_text())
    for c in seed["candidatos"]:
        conn.execute(
            """INSERT INTO candidatos (address, categoria, prioridad, antiguedad, estilo, riesgo, monedas,
               cuenta, siguiendo, retorno_pct, profit_factor, puntuacion, win_rate, drawdown,
               posicion_actual, holdings_spot, operaciones_recientes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                c["address"], c.get("categoria"), c.get("prioridad"), c.get("antiguedad"),
                c.get("estilo"), c.get("riesgo"), c.get("monedas"), c.get("cuenta"),
                int(bool(c.get("siguiendo"))), c.get("retorno_pct"), c.get("profit_factor"),
                c.get("puntuacion"), c.get("win_rate"), c.get("drawdown"),
                json.dumps(c.get("posicion_actual", []), ensure_ascii=False),
                json.dumps(c.get("holdings_spot", []), ensure_ascii=False),
                json.dumps(c.get("operaciones_recientes", []), ensure_ascii=False),
            ),
        )
    for a in seed.get("alertas", []):
        conn.execute(
            """INSERT INTO alertas (id, tipo, addr, coin, lado, tamaño, precio, coste, estado, detectado)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (a["id"], a.get("tipo"), a.get("addr"), a.get("coin"), a.get("lado"), a.get("tamaño"),
             a.get("precio"), a.get("coste"), a.get("estado", "pendiente"), a.get("detectado")),
        )
    for m in seed.get("mis_posiciones", []):
        conn.execute(
            """INSERT INTO mis_posiciones (id, addr, tipo, coin, lado, estado, fecha_apertura, fecha_cierre, pnl, alerta_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (m["id"], m.get("addr"), m.get("tipo"), m.get("coin"), m.get("lado"), m.get("estado", "abierta"),
             m.get("fecha_apertura"), m.get("fecha_cierre"), m.get("pnl"), m.get("alerta_id")),
        )
    conn.commit()
    conn.close()
    print(f"Sembrado: {len(seed['candidatos'])} candidatos, {len(seed.get('alertas', []))} alertas")
