import json
import threading
import time
import traceback

import db
import hyperliquid
import telegram

INTERVALO_SEGUNDOS = 5 * 60


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

    candidato = {"cuenta": cuenta, "puntuacion": puntuacion, "win_rate": bt["win_rate"] if bt else None}
    detectar_alertas(conn, addr, datos["posicion_actual"], datos["holdings_spot"], candidato)


def cabecera(addr, candidato):
    rank = f"{candidato['puntuacion']}/100" if candidato.get("puntuacion") is not None else "sin puntuación"
    wr = f"{candidato['win_rate']*100:.0f}%" if candidato.get("win_rate") is not None else "sin dato"
    return f"{addr[:10]}... · Ranking: {rank} · Win rate: {wr}"


def detectar_alertas(conn, addr, posicion_actual, holdings_spot, candidato):
    """Compara lo que hay abierto AHORA contra lo que ya conociamos (guardado
    en 'alertas'): si la clave coin+lado no existia, es una posicion nueva;
    si existia con otro tamaño, es que ha añadido o reducido -- de eso solo
    avisamos cuando AUMENTA (reducir/cerrar no lo pidio el usuario)."""
    avisos = []
    ahora = int(time.time() * 1000)
    fecha = hyperliquid.formatear_time(ahora)

    for p in posicion_actual:
        id_ = f"{addr}_trading_{p['coin']}_{p['lado']}"
        fila = conn.execute("SELECT tamaño FROM alertas WHERE id=?", (id_,)).fetchone()
        invertido = p["tamaño"] * p["entryPx"]
        pct = f"{invertido/candidato['cuenta']*100:.1f}%" if candidato.get("cuenta") else "—"
        if fila is None:
            conn.execute(
                "INSERT INTO alertas (id, tipo, addr, coin, lado, tamaño, precio, estado, detectado) VALUES (?,?,?,?,?,?,?,?,?)",
                (id_, "trading", addr, p["coin"], p["lado"], p["tamaño"], p["entryPx"], "pendiente", ahora),
            )
            avisos.append(
                f"🟢 Nueva posición — {cabecera(addr, candidato)}\n\n"
                f"{p['lado'].upper()} {p['coin']}\n"
                f"$ invertido: ${invertido:,.0f}\n"
                f"% de su cartera: {pct}\n"
                f"Entrada: ${p['entryPx']}\n"
                f"Hora: {fecha}"
            )
        elif abs(fila["tamaño"] - p["tamaño"]) > max(1e-9, p["tamaño"] * 0.001):
            antes = fila["tamaño"]
            conn.execute("UPDATE alertas SET tamaño=?, precio=? WHERE id=?", (p["tamaño"], p["entryPx"], id_))
            avisos.append(
                f"🔵 Ha añadido — {cabecera(addr, candidato)}\n\n"
                f"{p['lado'].upper()} {p['coin']}\n"
                f"Antes: {antes}\n"
                f"Ahora: {p['tamaño']}\n"
                f"$ invertido ahora: ${invertido:,.0f}\n"
                f"% de su cartera: {pct}\n"
                f"Entrada: ${p['entryPx']}\n"
                f"Hora: {fecha}"
            )

    for h in holdings_spot:
        id_ = f"{addr}_spot_{h['coin']}"
        fila = conn.execute("SELECT tamaño FROM alertas WHERE id=?", (id_,)).fetchone()
        if fila is None:
            conn.execute(
                "INSERT INTO alertas (id, tipo, addr, coin, tamaño, coste, estado, detectado) VALUES (?,?,?,?,?,?,?,?)",
                (id_, "spot", addr, h["coin"], h["tamaño"], h.get("costeBase"), "pendiente", ahora),
            )
            avisos.append(
                f"🟢 Nueva compra spot — {cabecera(addr, candidato)}\n\n"
                f"{h['coin']}\n"
                f"Tamaño: {h['tamaño']}\n"
                f"Hora: {fecha}"
            )
        elif abs(fila["tamaño"] - h["tamaño"]) > max(1e-9, h["tamaño"] * 0.001):
            antes = fila["tamaño"]
            conn.execute("UPDATE alertas SET tamaño=? WHERE id=?", (h["tamaño"], id_))
            avisos.append(
                f"🔵 Ha añadido a su cartera spot — {cabecera(addr, candidato)}\n\n"
                f"{h['coin']}\n"
                f"Antes: {antes}\n"
                f"Ahora: {h['tamaño']}\n"
                f"Hora: {fecha}"
            )

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
