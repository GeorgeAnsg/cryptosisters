import json
import threading
import time
import traceback

import db
import hyperliquid
import nombres
import telegram

INTERVALO_SEGUNDOS = 5 * 60


def actualizar_datos_y_puntuacion(conn, addr, spot_nombres, idx_por_nombre, precios):
    """La parte 'cara' (llamadas a Hyperliquid + backtest) de refrescar a un
    trader, sin las alertas -- se reutiliza tanto para los que se siguen
    (refrescar_uno) como para re-evaluar a los que NO se siguen antes de
    decidir si siguen teniendo sitio en la lista (ver descubrimiento.py)."""
    datos = hyperliquid.datos_de_trader(addr, spot_nombres, idx_por_nombre, precios)
    fila = conn.execute("SELECT cuenta FROM candidatos WHERE address=?", (addr,)).fetchone()
    cuenta = fila["cuenta"] if fila else None

    # si una faceta (trading o spot) tiene un retorno catastrofico, esa
    # faceta concreta se queda sin puntuacion (no cuenta para nada) -- pero
    # NO descalifica al candidato entero: si la otra faceta va bien, se
    # queda en la lista solo por esa parte buena (ver hyperliquid.veto_catastrofico)
    bt = hyperliquid.backtest_trader(datos["operaciones_backtest"], cuenta, lados=("Long", "Short"))
    puntuacion = None
    if bt and bt["retorno_pct"] is not None and not hyperliquid.veto_catastrofico(bt["retorno_pct"]):
        puntuacion = hyperliquid.puntuacion_de(bt["retorno_pct"], bt["profit_factor"], -bt["drawdown"] * 100)

    bt_spot = hyperliquid.backtest_trader(datos["operaciones_backtest"], cuenta, lados=("Spot",))
    puntuacion_spot = None
    if bt_spot and bt_spot["retorno_pct"] is not None and not hyperliquid.veto_catastrofico(bt_spot["retorno_pct"]):
        puntuacion_spot = hyperliquid.puntuacion_de(bt_spot["retorno_pct"], bt_spot["profit_factor"], -bt_spot["drawdown"] * 100)

    conn.execute(
        """UPDATE candidatos SET posicion_actual=?, holdings_spot=?, operaciones_recientes=?,
           retorno_pct=?, profit_factor=?, win_rate=?, drawdown=?, puntuacion=?,
           puntuacion_spot=?, win_rate_spot=?, retorno_pct_spot=?, drawdown_spot=?
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
            puntuacion_spot,
            bt_spot["win_rate"] if bt_spot else None,
            bt_spot["retorno_pct"] if bt_spot else None,
            bt_spot["drawdown"] if bt_spot else None,
            addr,
        ),
    )

    candidato = {"cuenta": cuenta, "puntuacion": puntuacion, "win_rate": bt["win_rate"] if bt else None, "profit_factor": bt["profit_factor"] if bt else None}
    return datos, candidato


def refrescar_uno(conn, addr, idx_por_nombre, precios):
    """El ciclo de 5 minutos: SOLO estado en vivo (2 llamadas baratas), para
    detectar una posicion nueva o un cambio lo antes posible. El backtest
    completo (caro, pide un año de fills) no hace falta repetirlo cada 5
    minutos -- eso lo hace ciclo_backtest_diario, una vez al dia."""
    posiciones, holdings = hyperliquid.posicion_y_holdings_de(addr, idx_por_nombre, precios)
    conn.execute(
        "UPDATE candidatos SET posicion_actual=?, holdings_spot=? WHERE address=?",
        (json.dumps(posiciones, ensure_ascii=False), json.dumps(holdings, ensure_ascii=False), addr),
    )
    fila = conn.execute("SELECT sigue_trading, sigue_spot, puntuacion, win_rate, profit_factor, cuenta FROM candidatos WHERE address=?", (addr,)).fetchone()
    candidato = {"cuenta": fila["cuenta"], "puntuacion": fila["puntuacion"], "win_rate": fila["win_rate"], "profit_factor": fila["profit_factor"]} if fila else {}
    # solo se avisa de "oportunidad nueva" en la faceta que de verdad se
    # sigue -- si solo se sigue su trading, no tiene sentido recibir avisos
    # de que ha comprado algo en spot, y viceversa
    posicion_para_alertas = posiciones if (fila and fila["sigue_trading"]) else []
    holdings_para_alertas = holdings if (fila and fila["sigue_spot"]) else []
    detectar_alertas(conn, addr, posicion_para_alertas, holdings_para_alertas, candidato)
    avisar_posiciones_propias(conn, addr, posiciones, holdings, candidato)


def refrescar_uno_backtest(conn, addr, spot_nombres, idx_por_nombre, precios):
    """El backtest completo (caro: un año de fills paginado) -- antes corria
    cada 5 minutos para todo el mundo que se sigue, lo cual era pedir un año
    entero de historial constantemente para una puntuacion que no cambia de
    un momento a otro. Ahora solo lo lanza ciclo_backtest_diario, una vez al
    dia por trader seguido."""
    actualizar_datos_y_puntuacion(conn, addr, spot_nombres, idx_por_nombre, precios)


def refrescar_solo_posicion_propia(conn, addr, idx_por_nombre, precios):
    """Para una direccion que ya NO se sigue (desestimada) o que incluso se
    ha borrado del todo de candidatos (ver descubrimiento.revisar_requisitos_permanencia),
    pero de la que el usuario sigue teniendo una copia abierta en
    mis_posiciones -- la alerta de 'tu posicion copiada ha cambiado' es la
    mas importante de todas y no puede depender de seguir vigilando al
    trader por otros motivos. No hace falta el backtest de 1 año aqui (caro,
    son varias llamadas paginadas) -- solo el estado EN VIVO, que es lo unico
    que necesita avisar_posiciones_propias. Sin detectar_alertas tampoco: no
    tiene sentido avisar de 'oportunidad nueva' de alguien que ya no se esta
    vigilando para eso."""
    posiciones, holdings = hyperliquid.posicion_y_holdings_de(addr, idx_por_nombre, precios)
    fila = conn.execute("SELECT puntuacion, win_rate, profit_factor FROM candidatos WHERE address=?", (addr,)).fetchone()
    candidato = {"puntuacion": fila["puntuacion"] if fila else None, "win_rate": fila["win_rate"] if fila else None, "profit_factor": fila["profit_factor"] if fila else None}
    avisar_posiciones_propias(conn, addr, posiciones, holdings, candidato)


def cabecera(conn, addr, candidato):
    todas = [r[0] for r in conn.execute("SELECT address FROM candidatos").fetchall()]
    nombre = nombres.nombre_de(addr, todas)
    rank = f"{candidato['puntuacion']}/100" if candidato.get("puntuacion") is not None else "sin puntuación"
    wr = f"{candidato['win_rate']*100:.0f}%" if candidato.get("win_rate") is not None else "sin dato"
    pf = candidato.get("profit_factor")
    pf_txt = f"{pf:.2f}" if pf is not None else ("sin dato" if candidato.get("puntuacion") is None else "∞")
    return f"{nombre} ({addr[:8]}...) · Ranking: {rank} · Win rate: {wr} · Profit factor: {pf_txt}"


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
        tpsl = ""
        if p.get("takeProfit") is not None:
            tpsl += f"Take profit: ${p['takeProfit']}\n"
        if p.get("stopLoss") is not None:
            tpsl += f"Stop loss: ${p['stopLoss']}\n"
        if fila is None:
            conn.execute(
                "INSERT INTO alertas (id, tipo, addr, coin, lado, tamaño, precio, estado, detectado) VALUES (?,?,?,?,?,?,?,?,?)",
                (id_, "trading", addr, p["coin"], p["lado"], p["tamaño"], p["entryPx"], "pendiente", ahora),
            )
            avisos.append((
                f"🟢 Nueva posición — {cabecera(conn, addr, candidato)}\n\n"
                f"{p['lado'].upper()} {p['coin']}\n"
                f"$ invertido: ${invertido:,.0f}\n"
                f"% de su cartera: {pct}\n"
                f"Entrada: ${p['entryPx']}\n"
                f"{tpsl}"
                f"Hora: {fecha}",
                id_,
            ))
        elif abs(fila["tamaño"] - p["tamaño"]) > max(1e-9, p["tamaño"] * 0.001):
            antes = fila["tamaño"]
            conn.execute("UPDATE alertas SET tamaño=?, precio=? WHERE id=?", (p["tamaño"], p["entryPx"], id_))
            avisos.append((
                f"🔵 Ha añadido — {cabecera(conn, addr, candidato)}\n\n"
                f"{p['lado'].upper()} {p['coin']}\n"
                f"Antes: {antes}\n"
                f"Ahora: {p['tamaño']}\n"
                f"$ invertido ahora: ${invertido:,.0f}\n"
                f"% de su cartera: {pct}\n"
                f"Entrada: ${p['entryPx']}\n"
                f"Hora: {fecha}",
                None,
            ))

    for h in holdings_spot:
        id_ = f"{addr}_spot_{h['coin']}"
        fila = conn.execute("SELECT tamaño FROM alertas WHERE id=?", (id_,)).fetchone()
        if fila is None:
            conn.execute(
                "INSERT INTO alertas (id, tipo, addr, coin, tamaño, coste, estado, detectado) VALUES (?,?,?,?,?,?,?,?)",
                (id_, "spot", addr, h["coin"], h["tamaño"], h.get("costeBase"), "pendiente", ahora),
            )
            avisos.append((
                f"🟢 Nueva compra spot — {cabecera(conn, addr, candidato)}\n\n"
                f"{h['coin']}\n"
                f"Tamaño: {h['tamaño']}\n"
                f"Hora: {fecha}",
                id_,
            ))
        elif abs(fila["tamaño"] - h["tamaño"]) > max(1e-9, h["tamaño"] * 0.001):
            antes = fila["tamaño"]
            conn.execute("UPDATE alertas SET tamaño=? WHERE id=?", (h["tamaño"], id_))
            avisos.append((
                f"🔵 Ha añadido a su cartera spot — {cabecera(conn, addr, candidato)}\n\n"
                f"{h['coin']}\n"
                f"Antes: {antes}\n"
                f"Ahora: {h['tamaño']}\n"
                f"Hora: {fecha}",
                None,
            ))

    for texto, boton_id in avisos:
        telegram.enviar(texto, boton_id)


def avisar_posiciones_propias(conn, addr, posicion_actual, holdings_spot, candidato):
    """La alerta mas importante: si el usuario tiene abierta una COPIA de una
    posicion de este trader (tabla mis_posiciones), avisa cuando esa posicion
    en concreto cambia -- el trader la cierra del todo, la aumenta o la
    reduce. A diferencia de detectar_alertas() (oportunidades nuevas que
    mirar), esto es sobre algo que el usuario YA tiene en juego."""
    propias = conn.execute("SELECT * FROM mis_posiciones WHERE addr=? AND estado='abierta'", (addr,)).fetchall()
    if not propias:
        return

    trading_actual = {(p["coin"], p["lado"]): p["tamaño"] for p in posicion_actual}
    spot_actual = {h["coin"]: h["tamaño"] for h in holdings_spot}
    ahora = int(time.time() * 1000)
    fecha = hyperliquid.formatear_time(ahora)
    avisos = []

    for mp in propias:
        if mp["tipo"] == "trading":
            actual = trading_actual.get((mp["coin"], mp["lado"]))
            etiqueta = f"{(mp['lado'] or '').upper()} {mp['coin']}"
        else:
            actual = spot_actual.get(mp["coin"])
            etiqueta = mp["coin"]
        visto = mp["tamaño_trader_visto"]

        if actual is None:
            if visto:  # None o 0 = ya avisamos de este cierre, no repetir cada ciclo
                avisos.append(
                    f"🔴 TU POSICIÓN COPIADA — {cabecera(conn, addr, candidato)}\n\n"
                    f"{etiqueta}: el trader la ha CERRADO del todo.\n"
                    f"Tú la sigues teniendo abierta con tu propio tamaño — decide si la cierras también.\n"
                    f"Hora: {fecha}"
                )
                conn.execute("UPDATE mis_posiciones SET tamaño_trader_visto=0 WHERE id=?", (mp["id"],))
        elif visto is not None and abs(actual - visto) > max(1e-9, visto * 0.001):
            aumenta = actual > visto
            avisos.append(
                f"{'🔵' if aumenta else '🟠'} TU POSICIÓN COPIADA — {cabecera(conn, addr, candidato)}\n\n"
                f"{etiqueta}: el trader ha {'AUMENTADO' if aumenta else 'REDUCIDO'} la suya.\n"
                f"Antes: {visto}\n"
                f"Ahora: {actual}\n"
                f"Hora: {fecha}"
            )
            conn.execute("UPDATE mis_posiciones SET tamaño_trader_visto=? WHERE id=?", (actual, mp["id"]))
        elif visto is None:
            # primera vez que tenemos el tamaño del trader para esta copia (p.ej. se abrio sin ese dato) -- solo fija la base, no avisa
            conn.execute("UPDATE mis_posiciones SET tamaño_trader_visto=? WHERE id=?", (actual, mp["id"]))

    for texto in avisos:
        telegram.enviar(texto)


def ciclo_refresco():
    while True:
        try:
            conn = db.conectar()
            siguiendo = {r["address"] for r in conn.execute("SELECT address FROM candidatos WHERE siguiendo=1")}
            # direcciones de las que el usuario tiene una copia abierta, pero
            # ya no se siguen (desestimadas, o incluso borradas del todo) --
            # siguen necesitando vigilancia para la alerta de "tu posicion
            # copiada ha cambiado", la mas importante de todas
            con_posicion_propia = {r["addr"] for r in conn.execute("SELECT DISTINCT addr FROM mis_posiciones WHERE estado='abierta'")}
            solo_posicion_propia = con_posicion_propia - siguiendo
            if siguiendo or solo_posicion_propia:
                spot_nombres = hyperliquid.cargar_spot_meta()
                idx_por_nombre = {v: k[1:] for k, v in spot_nombres.items()}
                precios = hyperliquid.fetch_json({"type": "allMids"})
                for addr in siguiendo:
                    try:
                        refrescar_uno(conn, addr, idx_por_nombre, precios)
                        conn.commit()
                    except Exception:
                        print(f"fallo refrescando {addr}:")
                        traceback.print_exc()
                for addr in solo_posicion_propia:
                    try:
                        refrescar_solo_posicion_propia(conn, addr, idx_por_nombre, precios)
                        conn.commit()
                    except Exception:
                        print(f"fallo refrescando (solo posicion propia) {addr}:")
                        traceback.print_exc()
            conn.close()
        except Exception:
            print("fallo en el ciclo de refresco:")
            traceback.print_exc()
        time.sleep(INTERVALO_SEGUNDOS)


INTERVALO_BACKTEST_SEGUNDOS = 24 * 60 * 60  # el backtest de 1 año (caro) solo hace falta repetirlo una vez al dia por trader seguido


def ciclo_backtest_diario():
    # igual que ciclo_descubrimiento: un reinicio del proceso no debe
    # relanzar el backtest caro de todo el mundo de golpe si ya se hizo hoy
    conn = db.conectar()
    ultima = db.meta_get(conn, "ultimo_backtest_diario")
    conn.close()
    if ultima:
        falta = INTERVALO_BACKTEST_SEGUNDOS - (time.time() - float(ultima))
        if falta > 0:
            time.sleep(falta)

    while True:
        try:
            conn = db.conectar()
            siguiendo = [r["address"] for r in conn.execute("SELECT address FROM candidatos WHERE siguiendo=1")]
            if siguiendo:
                spot_nombres = hyperliquid.cargar_spot_meta()
                idx_por_nombre = {v: k[1:] for k, v in spot_nombres.items()}
                precios = hyperliquid.fetch_json({"type": "allMids"})
                for addr in siguiendo:
                    try:
                        refrescar_uno_backtest(conn, addr, spot_nombres, idx_por_nombre, precios)
                        conn.commit()
                    except Exception:
                        print(f"fallo en el backtest diario de {addr}:")
                        traceback.print_exc()
            db.meta_set(conn, "ultimo_backtest_diario", str(time.time()))
            conn.close()
        except Exception:
            print("fallo en el ciclo de backtest diario:")
            traceback.print_exc()
        time.sleep(INTERVALO_BACKTEST_SEGUNDOS)


def arrancar_en_segundo_plano():
    threading.Thread(target=ciclo_refresco, daemon=True).start()
    threading.Thread(target=ciclo_backtest_diario, daemon=True).start()
