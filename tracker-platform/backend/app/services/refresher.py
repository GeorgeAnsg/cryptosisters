"""
Porte de backend/refresher.py (la app vieja) -- mismo comportamiento, menos
avisar_posiciones_propias (dependia de 'mis_posiciones', una funcionalidad de
copy-trading propia que esta app todavia no tiene). Las alertas/consenso
siguen siendo globales (vienen de 'candidatos', el pool de descubrimiento
compartido); lo que cambia con usuarios es solo que el refresco intensivo
(cada 5 min + backtest diario) se dedica a quien sigue ALGUIEN, no a un
unico flag 'siguiendo'.
"""
import json
import threading
import time
import traceback

from app.db import database as db
from app.services import hyperliquid, nombres, telegram

INTERVALO_SEGUNDOS = 5 * 60


def actualizar_datos_y_puntuacion(conn, addr, spot_nombres, idx_por_nombre, precios):
    datos = hyperliquid.datos_de_trader(addr, spot_nombres, idx_por_nombre, precios)
    fila = conn.execute("SELECT cuenta FROM candidatos WHERE address=?", (addr,)).fetchone()
    cuenta = fila["cuenta"] if fila else None

    bt = hyperliquid.backtest_trader(datos["operaciones_backtest"], cuenta, lados=("Long", "Short"))
    puntuacion = None
    if bt and bt["retorno_pct"] is not None and not hyperliquid.veto_catastrofico(bt["retorno_pct"]):
        puntuacion = hyperliquid.puntuacion_de(bt["retorno_pct"], bt["profit_factor"], -bt["drawdown"] * 100)

    bt_spot = hyperliquid.backtest_trader(datos["operaciones_backtest"], cuenta, lados=("Spot",))
    puntuacion_spot = None
    if bt_spot and bt_spot["retorno_pct"] is not None and not hyperliquid.veto_catastrofico(bt_spot["retorno_pct"]):
        puntuacion_spot = hyperliquid.puntuacion_de(bt_spot["retorno_pct"], bt_spot["profit_factor"], -bt_spot["drawdown"] * 100)

    monedas_top = hyperliquid.monedas_mas_usadas(datos["operaciones_backtest"], datos["posicion_actual"], datos["holdings_spot"], spot_nombres)

    conn.execute(
        """UPDATE candidatos SET posicion_actual=?, holdings_spot=?, operaciones_recientes=?, monedas_top=?,
           retorno_pct=?, profit_factor=?, win_rate=?, drawdown=?, puntuacion=?,
           puntuacion_spot=?, win_rate_spot=?, retorno_pct_spot=?, drawdown_spot=?, profit_factor_spot=?
           WHERE address=?""",
        (
            json.dumps(datos["posicion_actual"], ensure_ascii=False),
            json.dumps(datos["holdings_spot"], ensure_ascii=False),
            json.dumps(datos["operaciones_recientes"], ensure_ascii=False),
            json.dumps(monedas_top, ensure_ascii=False),
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
    """Ciclo de 5 minutos: solo estado en vivo (barato), para detectar una
    posicion nueva o un cambio lo antes posible."""
    posiciones, holdings = hyperliquid.posicion_y_holdings_de(addr, idx_por_nombre, precios)
    conn.execute(
        "UPDATE candidatos SET posicion_actual=?, holdings_spot=? WHERE address=?",
        (json.dumps(posiciones, ensure_ascii=False), json.dumps(holdings, ensure_ascii=False), addr),
    )
    fila = conn.execute(
        """SELECT cuenta, puntuacion, win_rate, profit_factor, retorno_pct,
           puntuacion_spot, win_rate_spot, profit_factor_spot, retorno_pct_spot
           FROM candidatos WHERE address=?""",
        (addr,),
    ).fetchone()
    candidato = dict(fila) if fila else {}
    detectar_alertas(conn, addr, posiciones, holdings, candidato, idx_por_nombre, precios)


def refrescar_uno_backtest(conn, addr, spot_nombres, idx_por_nombre, precios):
    """Backtest completo (caro, un año de fills) -- una vez al dia por
    trader seguido (ver ciclo_backtest_diario)."""
    actualizar_datos_y_puntuacion(conn, addr, spot_nombres, idx_por_nombre, precios)


def cabecera(conn, addr, candidato, faceta):
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
    return f"{etiqueta}{nombre} - {rank}\nWR: {wr} · Retorno: {ret_txt} · PF: {pf_txt}"


def detectar_alertas(conn, addr, posicion_actual, holdings_spot, candidato, idx_por_nombre, precios):
    """Igual que la app vieja, sin el filtro por sigue_trading/sigue_spot
    (aqui no hay un unico flag; el pool entero se refresca para quien sigue
    alguien, y las alertas alimentan tanto el Telegram operativo como la
    tabla 'alertas' que consume /candidatos/consenso y las notificaciones por
    usuario en el frontend)."""
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
        if fila is None:
            conn.execute(
                "INSERT INTO alertas (id, tipo, addr, coin, lado, tamaño, precio, estado, detectado) VALUES (?,?,?,?,?,?,?,?,?)",
                (id_, "trading", addr, p["coin"], p["lado"], p["tamaño"], p["entryPx"], "pendiente", ahora),
            )
            avisos.append((
                f"🟢 <b>{p['lado']} en {coin} {flecha} (nueva posición)</b>\n"
                f"Precio de entrada: ${p['entryPx']}\n"
                f"$ invertido: ${invertido:,.0f} · % de su cartera: {pct}\n\n"
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

    posiciones_actuales = {(p["coin"], p["lado"]) for p in posicion_actual}
    previas = conn.execute("SELECT id, coin, lado, tamaño, precio FROM alertas WHERE addr=? AND tipo='trading' AND tamaño>0", (addr,)).fetchall()
    for prev in previas:
        if (prev["coin"], prev["lado"]) in posiciones_actuales:
            continue
        coin = hyperliquid.etiqueta_moneda(prev["coin"])
        flecha = "↑" if prev["lado"] == "Long" else "↓"
        precio_cierre = precio_de(prev["coin"], "trading") or prev["precio"]
        invertido_cerrado = prev["tamaño"] * precio_cierre if precio_cierre is not None else None
        conn.execute("UPDATE alertas SET tamaño=0, tamaño_antes=?, precio=?, detectado=? WHERE id=?", (prev["tamaño"], precio_cierre, ahora, prev["id"]))
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
            conn.execute("UPDATE alertas SET tamaño=?, tamaño_antes=?, precio=?, detectado=? WHERE id=?", (h["tamaño"], antes, precio, ahora, id_))
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
        conn.execute("UPDATE alertas SET tamaño=0, tamaño_antes=?, precio=?, detectado=? WHERE id=?", (prev["tamaño"], precio, ahora, prev["id"]))
        avisos.append((
            f"🟣 <b>Eliminado de spot: {coin} ({f'-{antes_txt}' if antes_dolares is not None else 'sin dato'})</b>\n"
            f"Precio (en ese momento): {precio_txt}\n\n"
            f"{cabecera(conn, addr, candidato, 'spot')}",
            None,
        ))

    for texto, boton_id in avisos:
        telegram.enviar(texto, boton_id)


VENTANA_CONSENSO_MS = 72 * 60 * 60 * 1000


def detectar_consenso(conn):
    """Igual que la app vieja -- solo manda Telegram cuando el grupo CRECE;
    el estado "actual" (para el endpoint que consume el frontend) se calcula
    aparte, en vivo, desde la tabla 'alertas' (ver routers/candidatos.py)."""
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
        texto = f"🟠 Consenso: {n} traders {lado} {verbos[tipo_grupo]} {etiqueta} {flecha}"
        telegram.enviar(texto)
    conn.commit()


def ciclo_refresco():
    while True:
        try:
            conn = db.conectar()
            seguidos = db.direcciones_seguidas_por_alguien(conn)
            if seguidos:
                spot_nombres = hyperliquid.cargar_spot_meta()
                idx_por_nombre = hyperliquid.cargar_idx_por_nombre()
                precios = hyperliquid.fetch_json({"type": "allMids"})
                for addr in seguidos:
                    try:
                        refrescar_uno(conn, addr, idx_por_nombre, precios)
                        conn.commit()
                    except Exception:
                        print(f"fallo refrescando {addr}:")
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


INTERVALO_BACKTEST_SEGUNDOS = 24 * 60 * 60


def ciclo_backtest_diario():
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
            seguidos = db.direcciones_seguidas_por_alguien(conn)
            if seguidos:
                spot_nombres = hyperliquid.cargar_spot_meta()
                idx_por_nombre = hyperliquid.cargar_idx_por_nombre()
                precios = hyperliquid.fetch_json({"type": "allMids"})
                for addr in seguidos:
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
