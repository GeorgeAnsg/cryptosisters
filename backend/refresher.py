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
           puntuacion_spot=?, win_rate_spot=?, retorno_pct_spot=?, drawdown_spot=?, profit_factor_spot=?
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
            bt_spot["profit_factor"] if bt_spot else None,
            addr,
        ),
    )

    candidato = {
        "cuenta": cuenta,
        "puntuacion": puntuacion, "win_rate": bt["win_rate"] if bt else None, "profit_factor": bt["profit_factor"] if bt else None, "retorno_pct": bt["retorno_pct"] if bt else None,
        "puntuacion_spot": puntuacion_spot, "win_rate_spot": bt_spot["win_rate"] if bt_spot else None, "profit_factor_spot": bt_spot["profit_factor"] if bt_spot else None, "retorno_pct_spot": bt_spot["retorno_pct"] if bt_spot else None,
    }
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
    fila = conn.execute(
        """SELECT sigue_trading, sigue_spot, cuenta,
           puntuacion, win_rate, profit_factor, retorno_pct,
           puntuacion_spot, win_rate_spot, profit_factor_spot, retorno_pct_spot
           FROM candidatos WHERE address=?""",
        (addr,),
    ).fetchone()
    # faltaba retorno_pct (y todo lo de spot) aqui -- por eso las alertas que
    # salen de este ciclo rapido (el que de verdad dispara los avisos) decian
    # "sin dato" aunque el candidato SI tuviera esos datos guardados
    candidato = dict(fila) if fila else {}
    # solo se avisa de "oportunidad nueva" en la faceta que de verdad se
    # sigue -- si solo se sigue su trading, no tiene sentido recibir avisos
    # de que ha comprado algo en spot, y viceversa
    sigue_trading = bool(fila and fila["sigue_trading"])
    sigue_spot = bool(fila and fila["sigue_spot"])
    posicion_para_alertas = posiciones if sigue_trading else []
    holdings_para_alertas = holdings if sigue_spot else []
    detectar_alertas(conn, addr, posicion_para_alertas, holdings_para_alertas, candidato, idx_por_nombre, precios, sigue_trading, sigue_spot)
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
    fila = conn.execute(
        """SELECT puntuacion, win_rate, profit_factor, retorno_pct,
           puntuacion_spot, win_rate_spot, profit_factor_spot, retorno_pct_spot
           FROM candidatos WHERE address=?""",
        (addr,),
    ).fetchone()
    candidato = dict(fila) if fila else {}
    avisar_posiciones_propias(conn, addr, posiciones, holdings, candidato)


def cabecera(conn, addr, candidato, faceta):
    """faceta: 'trading' o 'spot' -- cada una tiene su propia puntuacion/win
    rate/profit factor/retorno, nunca se mezclan (antes siempre se mostraban
    los datos de trading aunque la alerta fuera de spot). Va al FINAL del
    mensaje: lo primero que se lee es la posicion en si (ver detectar_alertas),
    esto es contexto de quien la abrio. Solo spot lleva etiqueta -- en trading
    no hace falta, por descarte (si no pone SPOT, es trading)."""
    todas = [r[0] for r in conn.execute("SELECT address FROM candidatos").fetchall()]
    nombre = nombres.nombre_de(addr, todas)
    sufijo = "_spot" if faceta == "spot" else ""
    puntuacion = candidato.get(f"puntuacion{sufijo}")
    win_rate = candidato.get(f"win_rate{sufijo}")
    profit_factor = candidato.get(f"profit_factor{sufijo}")
    retorno = candidato.get(f"retorno_pct{sufijo}")
    rank = f"{puntuacion}/100" if puntuacion is not None else "sin puntuación"
    wr = f"{win_rate*100:.0f}%" if win_rate is not None else "sin dato"
    pf_txt = f"{profit_factor:.2f}" if profit_factor is not None else ("sin dato" if puntuacion is None else "∞")
    ret_txt = f"{retorno:+.1f}%" if retorno is not None else "sin dato"
    etiqueta = "SPOT\n" if faceta == "spot" else ""
    return (
        f"{etiqueta}"
        f"{nombre} - {rank}\n"
        f"WR: {wr} · Retorno: {ret_txt} · PF: {pf_txt}"
    )


def detectar_alertas(conn, addr, posicion_actual, holdings_spot, candidato, idx_por_nombre, precios, sigue_trading=True, sigue_spot=True):
    """Compara lo que hay abierto AHORA contra lo que ya conociamos (guardado
    en 'alertas'): si la clave coin+lado no existia, es una posicion nueva;
    si existia con otro tamaño, es que ha añadido o reducido -- de eso se
    avisa en los dos sentidos (antes solo se avisaba de aumentos; una
    reduccion parcial tambien es informacion util sobre ese trader). Tanto
    posicion_actual como holdings_spot dejan de incluir del todo una moneda
    en cuanto se cierra/vende por completo (misma logica en
    hyperliquid.holdings_spot_de y posicion_actual_de), asi que un cierre
    TOTAL nunca pasaria por los bucles de abajo -- hay que detectarlo aparte,
    comparando contra lo que la tabla alertas ya sabia que habia."""
    avisos = []
    ahora = int(time.time() * 1000)

    def precio_de(coin_crudo, tipo="spot"):
        if tipo == "trading":
            p = precios.get(coin_crudo)
            return float(p) if p is not None else None
        idx = idx_por_nombre.get(coin_crudo)
        p = precios.get(f"@{idx}") if idx is not None else None
        return float(p) if p is not None else None

    for p in posicion_actual:
        id_ = f"{addr}_trading_{p['coin']}_{p['lado']}"
        fila = conn.execute("SELECT tamaño FROM alertas WHERE id=?", (id_,)).fetchone()
        invertido = p["tamaño"] * p["entryPx"]
        pct = f"{invertido/candidato['cuenta']*100:.1f}%" if candidato.get("cuenta") else "—"
        coin = hyperliquid.etiqueta_moneda(p["coin"])
        flecha = "↑" if p["lado"] == "Long" else "↓"
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
                f"🟢 <b>{p['lado']} en {coin} {flecha} (nueva posición)</b>\n"
                f"Precio de entrada: ${p['entryPx']}\n"
                f"$ invertido: ${invertido:,.0f} · % de su cartera: {pct}\n"
                f"{tpsl}\n"
                f"{cabecera(conn, addr, candidato, 'trading')}",
                id_,
            ))
        elif abs(fila["tamaño"] - p["tamaño"]) > max(1e-9, p["tamaño"] * 0.001):
            antes = fila["tamaño"]
            conn.execute("UPDATE alertas SET tamaño=?, tamaño_antes=?, precio=?, detectado=? WHERE id=?", (p["tamaño"], antes, p["entryPx"], ahora, id_))
            delta = (p["tamaño"] - antes) * p["entryPx"]
            signo = "+" if delta >= 0 else "-"
            avisos.append((
                f"🔵 <b>{p['lado']} en {coin} {flecha} ({signo}${abs(delta):,.0f})</b>\n"
                f"Precio de entrada: ${p['entryPx']}\n"
                f"% de su cartera: {pct}\n\n"
                f"{cabecera(conn, addr, candidato, 'trading')}",
                None,
            ))

    if sigue_trading:
        # cierre total: posicion_actual_de() ya no incluye una moneda+lado en
        # cuanto se cierra del todo, asi que no pasa por el bucle de arriba
        posiciones_actuales = {(p["coin"], p["lado"]) for p in posicion_actual}
        previas = conn.execute("SELECT id, coin, lado, tamaño, precio FROM alertas WHERE addr=? AND tipo='trading' AND tamaño>0", (addr,)).fetchall()
        for prev in previas:
            if (prev["coin"], prev["lado"]) in posiciones_actuales:
                continue
            coin = hyperliquid.etiqueta_moneda(prev["coin"])
            flecha = "↑" if prev["lado"] == "Long" else "↓"
            precio_cierre = precio_de(prev["coin"], "trading") or prev["precio"]
            invertido_cerrado = prev["tamaño"] * precio_cierre if precio_cierre is not None else None
            conn.execute("UPDATE alertas SET tamaño=0, tamaño_antes=?, detectado=? WHERE id=?", (prev["tamaño"], ahora, prev["id"]))
            avisos.append((
                f"⚪ <b>{prev['lado']} en {coin} {flecha} (cerrada)</b>\n"
                f"{f'$ cerrado: ${invertido_cerrado:,.0f}' if invertido_cerrado is not None else 'Sin dato de precio para calcular lo cerrado'}\n\n"
                f"{cabecera(conn, addr, candidato, 'trading')}",
                None,
            ))

    for h in holdings_spot:
        id_ = f"{addr}_spot_{h['coin']}"
        fila = conn.execute("SELECT tamaño FROM alertas WHERE id=?", (id_,)).fetchone()
        coin = hyperliquid.etiqueta_moneda(h["coin"])
        precio = (h["valorActual"] / h["tamaño"]) if (h.get("valorActual") is not None and h["tamaño"]) else precio_de(h["coin"])
        precio_txt = f"${precio:,.0f}" if precio is not None else "sin dato"
        ahora_dolares = h["valorActual"] if h.get("valorActual") is not None else (h["tamaño"] * precio if precio is not None else None)
        ahora_txt = f"${ahora_dolares:,.0f}" if ahora_dolares is not None else "sin dato"
        if fila is None:
            conn.execute(
                "INSERT INTO alertas (id, tipo, addr, coin, tamaño, coste, estado, detectado) VALUES (?,?,?,?,?,?,?,?)",
                (id_, "spot", addr, h["coin"], h["tamaño"], h.get("costeBase"), "pendiente", ahora),
            )
            avisos.append((
                f"🟣 <b>Nuevo en spot: {coin} ({'+'+ahora_txt if ahora_dolares is not None else 'sin dato'})</b>\n"
                f"Precio (en ese momento): {precio_txt}\n\n"
                f"{cabecera(conn, addr, candidato, 'spot')}",
                id_,
            ))
        elif abs(fila["tamaño"] - h["tamaño"]) > max(1e-9, h["tamaño"] * 0.001):
            antes = fila["tamaño"]
            conn.execute("UPDATE alertas SET tamaño=?, tamaño_antes=?, detectado=? WHERE id=?", (h["tamaño"], antes, ahora, id_))
            antes_dolares = antes * precio if precio is not None else None
            antes_txt = f"${antes_dolares:,.0f}" if antes_dolares is not None else "sin dato"
            aumenta = h["tamaño"] > antes
            delta_dolares = (ahora_dolares - antes_dolares) if (ahora_dolares is not None and antes_dolares is not None) else None
            delta_txt = f"{'+' if aumenta else '-'}${abs(delta_dolares):,.0f}" if delta_dolares is not None else "sin dato"
            titulo = "Añadido en spot" if aumenta else "Reducido en spot"
            avisos.append((
                f"🟣 <b>{titulo}: {coin} ({delta_txt})</b>\n"
                f"Precio (en ese momento): {precio_txt}\n"
                f"Antes: {antes_txt} · Ahora: {ahora_txt}\n\n"
                f"{cabecera(conn, addr, candidato, 'spot')}",
                None,
            ))

    if sigue_spot:
        # eliminado del todo: holdings_spot_de() ya no incluye una moneda en
        # cuanto baja a ~0, asi que no pasa por el bucle de arriba -- hay que
        # comparar contra lo que la tabla alertas ya sabia que tenia
        monedas_actuales = {h["coin"] for h in holdings_spot}
        previos = conn.execute("SELECT id, coin, tamaño FROM alertas WHERE addr=? AND tipo='spot' AND tamaño>0", (addr,)).fetchall()
        for prev in previos:
            if prev["coin"] in monedas_actuales:
                continue
            coin = hyperliquid.etiqueta_moneda(prev["coin"])
            precio = precio_de(prev["coin"])
            precio_txt = f"${precio:,.0f}" if precio is not None else "sin dato"
            antes_dolares = prev["tamaño"] * precio if precio is not None else None
            antes_txt = f"${antes_dolares:,.0f}" if antes_dolares is not None else "sin dato"
            conn.execute("UPDATE alertas SET tamaño=0, tamaño_antes=?, detectado=? WHERE id=?", (prev["tamaño"], ahora, prev["id"]))
            avisos.append((
                f"🟣 <b>Eliminado de spot: {coin} ({f'-{antes_txt}' if antes_dolares is not None else 'sin dato'})</b>\n"
                f"Precio (en ese momento): {precio_txt}\n\n"
                f"{cabecera(conn, addr, candidato, 'spot')}",
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
    avisos = []

    for mp in propias:
        faceta = mp["tipo"]  # 'trading' o 'spot'
        if faceta == "trading":
            actual = trading_actual.get((mp["coin"], mp["lado"]))
            etiqueta = f"{(mp['lado'] or '').upper()} {hyperliquid.etiqueta_moneda(mp['coin'])}"
        else:
            actual = spot_actual.get(mp["coin"])
            etiqueta = hyperliquid.etiqueta_moneda(mp["coin"])
        visto = mp["tamaño_trader_visto"]

        if actual is None:
            if visto:  # None o 0 = ya avisamos de este cierre, no repetir cada ciclo
                avisos.append(
                    f"🔴 TU POSICIÓN COPIADA\n{cabecera(conn, addr, candidato, faceta)}\n\n"
                    f"{etiqueta}: el trader la ha CERRADO del todo.\n"
                    f"Tú la sigues teniendo abierta con tu propio tamaño — decide si la cierras también."
                )
                conn.execute("UPDATE mis_posiciones SET tamaño_trader_visto=0 WHERE id=?", (mp["id"],))
        elif visto is not None and abs(actual - visto) > max(1e-9, visto * 0.001):
            aumenta = actual > visto
            avisos.append(
                f"{'🔵' if aumenta else '🟠'} TU POSICIÓN COPIADA\n{cabecera(conn, addr, candidato, faceta)}\n\n"
                f"{etiqueta}: el trader ha {'AUMENTADO' if aumenta else 'REDUCIDO'} la suya.\n"
                f"Antes: {visto}\n"
                f"Ahora: {actual}"
            )
            conn.execute("UPDATE mis_posiciones SET tamaño_trader_visto=? WHERE id=?", (actual, mp["id"]))
        elif visto is None:
            # primera vez que tenemos el tamaño del trader para esta copia (p.ej. se abrio sin ese dato) -- solo fija la base, no avisa
            conn.execute("UPDATE mis_posiciones SET tamaño_trader_visto=? WHERE id=?", (actual, mp["id"]))

    for texto in avisos:
        telegram.enviar(texto)


VENTANA_CONSENSO_MS = 72 * 60 * 60 * 1000


def detectar_consenso(conn):
    """Consenso = 2+ traders seguidos con la misma coin+lado abierta/añadida
    (entrando), reducida mientras sigue abierta (reduciendo) o cerrada del
    todo (cerrando) en las ultimas 72h. Solo avisa cuando el grupo CRECE
    respecto a la ultima vez que se aviso de esa clave (si no, cada ciclo de
    5 min repetiria el mismo aviso sin novedad real)."""
    ahora = int(time.time() * 1000)
    desde = ahora - VENTANA_CONSENSO_MS
    grupos = {}
    for fila in conn.execute(
        "SELECT coin, lado, addr FROM alertas WHERE tipo='trading' AND tamaño>0 AND detectado>=? "
        "AND (tamaño_antes IS NULL OR tamaño>tamaño_antes)", (desde,)
    ):
        grupos.setdefault(("entrando", fila["coin"], fila["lado"]), set()).add(fila["addr"])
    for fila in conn.execute(
        "SELECT coin, lado, addr FROM alertas WHERE tipo='trading' AND tamaño>0 AND detectado>=? "
        "AND tamaño_antes IS NOT NULL AND tamaño<tamaño_antes", (desde,)
    ):
        grupos.setdefault(("reduciendo", fila["coin"], fila["lado"]), set()).add(fila["addr"])
    for fila in conn.execute(
        "SELECT coin, lado, addr FROM alertas WHERE tipo='trading' AND tamaño=0 AND detectado>=?", (desde,)
    ):
        grupos.setdefault(("cerrando", fila["coin"], fila["lado"]), set()).add(fila["addr"])

    verbos = {"entrando": "en", "reduciendo": "reduciendo en", "cerrando": "cerrando"}
    for (tipo_grupo, coin, lado), direcciones in grupos.items():
        n = len(direcciones)
        if n < 2:
            continue
        clave = f"{tipo_grupo}|{coin}|{lado}"
        visto = conn.execute("SELECT n FROM consenso_visto WHERE clave=?", (clave,)).fetchone()
        if visto is not None and visto["n"] >= n:
            continue
        conn.execute(
            "INSERT INTO consenso_visto (clave, n) VALUES (?,?) ON CONFLICT(clave) DO UPDATE SET n=excluded.n",
            (clave, n),
        )
        etiqueta = hyperliquid.etiqueta_moneda(coin)
        flecha = "↑" if lado == "Long" else "↓"
        texto = f"🟠 Consenso: {n} traders {lado} {verbos[tipo_grupo]} {etiqueta} {flecha} (últimas 72h)"
        telegram.enviar(texto)
        db.crear_notificacion(conn, texto)
    conn.commit()


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
                try:
                    detectar_consenso(conn)
                except Exception:
                    print("fallo detectando consenso:")
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
