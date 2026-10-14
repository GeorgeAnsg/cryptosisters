import json
import threading
import time
import traceback

import db
import hyperliquid
import telegram

INTERVALO_SEGUNDOS = 5 * 60


def nombre_planta_o_addr(conn, addr):
    row = conn.execute("SELECT categoria FROM candidatos WHERE address=?", (addr,)).fetchone()
    return addr[:10] if row is None else addr[:10]


def refrescar_uno(conn, addr, spot_nombres, idx_por_nombre, precios):
    datos = hyperliquid.datos_de_trader(addr, spot_nombres, idx_por_nombre, precios)
    fila = conn.execute("SELECT cuenta FROM candidatos WHERE address=?", (addr,)).fetchone()
    cuenta = fila["cuenta"] if fila else None

    bt = hyperliquid.backtest_trader(datos["operaciones_recientes"], cuenta)
    puntuacion = None
    if bt and bt["retorno_pct"] is not None:
        puntuacion = hyperliquid.puntuacion_de(bt["retorno_pct"], bt["profit_factor"], -bt["drawdown"] * 100)

    conn.execute(
        """UPDATE candidatos SET posicion_actual=?, holdings_spot=?, operaciones_recientes=?,
           retorno_pct=?, profit_factor=?, win_rate=?, drawdown=?, puntuacion=?
           WHERE address=?""",
        (
            json.dumps(datos["posicion_actual"], ensure_ascii=False),
            json.dumps(datos["holdings_spot"], ensure_ascii=False),
            json.dumps(datos["operaciones_recientes"], ensure_ascii=False),
            bt["retorno_pct"] if bt else None,
            bt["profit_factor"] if bt else None,
            bt["win_rate"] if bt else None,
            bt["drawdown"] if bt else None,
            puntuacion,
            addr,
        ),
    )

    detectar_alertas(conn, addr, datos["posicion_actual"], datos["holdings_spot"])


def detectar_alertas(conn, addr, posicion_actual, holdings_spot):
    """Misma logica que tenia el front en JS (detectarAlertas): compara lo
    que hay abierto AHORA contra lo que ya conociamos, y lo nuevo se guarda
    como alerta pendiente + aviso de Telegram."""
    avisos = []
    for p in posicion_actual:
        id_ = f"{addr}_trading_{p['coin']}_{p['lado']}"
        existe = conn.execute("SELECT 1 FROM alertas WHERE id=?", (id_,)).fetchone()
        if existe:
            continue
        conn.execute(
            "INSERT INTO alertas (id, tipo, addr, coin, lado, tamaño, precio, estado, detectado) VALUES (?,?,?,?,?,?,?,?,?)",
            (id_, "trading", addr, p["coin"], p["lado"], p["tamaño"], p["entryPx"], "pendiente", int(time.time() * 1000)),
        )
        avisos.append(f"Nueva posicion {p['lado']} en {p['coin']} (trader {addr[:10]}...)")

    for h in holdings_spot:
        id_ = f"{addr}_spot_{h['coin']}"
        existe = conn.execute("SELECT 1 FROM alertas WHERE id=?", (id_,)).fetchone()
        if existe:
            continue
        conn.execute(
            "INSERT INTO alertas (id, tipo, addr, coin, tamaño, coste, estado, detectado) VALUES (?,?,?,?,?,?,?,?)",
            (id_, "spot", addr, h["coin"], h["tamaño"], h.get("costeBase"), "pendiente", int(time.time() * 1000)),
        )
        avisos.append(f"Nueva compra spot de {h['coin']} (trader {addr[:10]}...)")

    for texto in avisos:
        telegram.enviar(texto)


def ciclo_refresco():
    while True:
        try:
            conn = db.conectar()
            direcciones = [r["address"] for r in conn.execute("SELECT address FROM candidatos WHERE siguiendo=1")]
            if direcciones:
                spot_nombres = hyperliquid.cargar_spot_meta()
                idx_por_nombre = {v: k[1:] for k, v in spot_nombres.items()}
                precios = hyperliquid.fetch_json({"type": "allMids"})
                for addr in direcciones:
                    try:
                        refrescar_uno(conn, addr, spot_nombres, idx_por_nombre, precios)
                        conn.commit()
                    except Exception:
                        print(f"fallo refrescando {addr}:")
                        traceback.print_exc()
            conn.close()
        except Exception:
            print("fallo en el ciclo de refresco:")
            traceback.print_exc()
        time.sleep(INTERVALO_SEGUNDOS)


def arrancar_en_segundo_plano():
    hilo = threading.Thread(target=ciclo_refresco, daemon=True)
    hilo.start()
