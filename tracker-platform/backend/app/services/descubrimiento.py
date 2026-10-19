"""
Descubrimiento de traders nuevos via el leaderboard publico de Hyperliquid.

Porte de backend/descubrimiento.py (la app vieja) -- misma logica de
preseleccion/backtest/umbrales, adaptada a que aqui el seguimiento es por
usuario (usuario_sigue), no un flag unico en candidatos: en vez de
"dejar de seguir" a un trader que cae de puntuacion, se marca
desestimado_motivo/fecha para que cada usuario que lo seguia reciba su propia
notificacion (ver NotificacionesService en el frontend), sin tocar su lista
de seguidos.

No forma parte del ciclo de refresco de 5 minutos (ver refresher.py) -- esto
corre mucho menos a menudo (pensado para una vez a la semana).
"""
import json
import time
import traceback
import urllib.request

from app.db import database as db
from app.services import hyperliquid, telegram

LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
INTERVALO_SEGUNDOS = 7 * 24 * 60 * 60

ESTADO = {"corriendo": False, "fase": None, "total": 0, "evaluados": 0, "descubiertos": 0, "actual": None, "inicio_ts": None}

CUENTA_MINIMA = 10_000
ROI_MES_MINIMO = 0.05
MAX_CANDIDATOS_A_EVALUAR = None
PUNTUACION_MINIMA = 70
PUNTUACION_MINIMA_MANTENER = 50


def _descargar_leaderboard():
    req = urllib.request.Request(LEADERBOARD_URL)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["leaderboardRows"]


def _preseleccion(filas, direcciones_conocidas):
    candidatos = []
    for f in filas:
        addr = f["ethAddress"].lower()
        if addr in direcciones_conocidas:
            continue
        try:
            cuenta = float(f["accountValue"])
        except (TypeError, ValueError):
            continue
        if cuenta < CUENTA_MINIMA:
            continue
        ventanas = dict(f["windowPerformances"])
        semana, mes, total = ventanas.get("week"), ventanas.get("month"), ventanas.get("allTime")
        if not (semana and mes and total):
            continue
        try:
            roi_semana, roi_mes, pnl_mes, roi_total = (
                float(semana["roi"]), float(mes["roi"]), float(mes["pnl"]), float(total["roi"]),
            )
        except (TypeError, ValueError):
            continue
        if roi_mes < ROI_MES_MINIMO or pnl_mes <= 0 or roi_semana <= 0 or roi_total <= 0:
            continue
        candidatos.append((addr, cuenta, roi_mes))
    candidatos.sort(key=lambda c: -c[2])
    return candidatos[:MAX_CANDIDATOS_A_EVALUAR]


def _antiguedad_dias(operaciones):
    if not operaciones:
        return None
    mas_vieja = min(o["ts"] for o in operaciones)
    return round((time.time() * 1000 - mas_vieja) / 86400000)


def revisar_desestimados(conn):
    """Marca desestimado_motivo/fecha en quien cae por debajo del umbral de
    mantenimiento en AMBAS facetas (trading y spot) -- a diferencia de la app
    vieja, no desactiva ningun flag de seguimiento (eso es responsabilidad de
    cada usuario, no del ciclo de descubrimiento). 'especulativo' nunca se
    desestima por esta via."""
    filas = conn.execute(
        "SELECT address, puntuacion, puntuacion_spot FROM candidatos WHERE categoria!='especulativo' OR categoria IS NULL"
    ).fetchall()
    desestimados = []
    ahora = int(time.time() * 1000)
    for c in filas:
        p, ps = c["puntuacion"], c["puntuacion_spot"]
        if p is None and ps is None:
            continue
        cae_trading = p is None or p < PUNTUACION_MINIMA_MANTENER
        cae_spot = ps is None or ps < PUNTUACION_MINIMA_MANTENER
        if not (cae_trading and cae_spot):
            continue
        motivo = f"puntuación por debajo de {PUNTUACION_MINIMA_MANTENER} (mantener)"
        conn.execute(
            "UPDATE candidatos SET desestimado_motivo=?, desestimado_fecha=? WHERE address=?",
            (motivo, ahora, c["address"]),
        )
        desestimados.append((c["address"], motivo, p, ps))
    conn.commit()
    return desestimados


def refrescar_no_seguidos(conn, spot_nombres, idx_por_nombre, precios, seguidos_por_alguien):
    """A todo candidato que nadie sigue solo lo pone al dia este ciclo
    semanal -- el de 5 minutos (refresher.ciclo_refresco) solo toca a quien
    sigue alguien."""
    direcciones = [
        r["address"] for r in conn.execute("SELECT address FROM candidatos WHERE categoria!='especulativo' OR categoria IS NULL")
        if r["address"] not in seguidos_por_alguien
    ]
    ESTADO["total"] = len(direcciones)
    ESTADO["evaluados"] = 0
    for addr in direcciones:
        ESTADO["actual"] = addr
        try:
            from app.services import refresher
            refresher.actualizar_datos_y_puntuacion(conn, addr, spot_nombres, idx_por_nombre, precios)
            conn.commit()
        except Exception:
            print(f"fallo refrescando (no seguido) {addr}:")
            traceback.print_exc()
        ESTADO["evaluados"] += 1
        time.sleep(hyperliquid.SLEEP_ENTRE_LLAMADAS)


def revisar_requisitos_permanencia(conn, recien_desestimados, seguidos_por_alguien):
    """Quien ya no cumple el minimo para entrar en la lista Y nadie lo sigue
    se borra de verdad. A quien SI sigue alguien no se le borra nunca aqui --
    aunque haya caido de puntuacion, sigue siendo una posicion real de algun
    usuario (ya recibio su aviso de desestimado via revisar_desestimados)."""
    direcciones_con_margen = {a for a, *_ in recien_desestimados}
    filas = conn.execute(
        "SELECT address, puntuacion, puntuacion_spot FROM candidatos WHERE categoria!='especulativo' OR categoria IS NULL"
    ).fetchall()
    eliminados = []
    for c in filas:
        if c["address"] in direcciones_con_margen or c["address"] in seguidos_por_alguien:
            continue
        p, ps = c["puntuacion"], c["puntuacion_spot"]
        if p is None and ps is None:
            continue
        if (p or 0) >= PUNTUACION_MINIMA or (ps or 0) >= PUNTUACION_MINIMA:
            continue
        conn.execute("DELETE FROM candidatos WHERE address=?", (c["address"],))
        conn.commit()
        eliminados.append((c["address"], p, ps))
    return eliminados


def descubrir_candidatos():
    ESTADO.update(corriendo=True, fase="desestimando", total=0, evaluados=0, descubiertos=0, actual=None, inicio_ts=time.time())
    try:
        conn = db.conectar()
        seguidos_por_alguien = db.direcciones_seguidas_por_alguien(conn)
        recien_desestimados = revisar_desestimados(conn)

        spot_nombres = hyperliquid.cargar_spot_meta()
        idx_por_nombre = hyperliquid.cargar_idx_por_nombre()
        precios = hyperliquid.fetch_json({"type": "allMids"})

        ESTADO["fase"] = "refrescando_no_seguidos"
        refrescar_no_seguidos(conn, spot_nombres, idx_por_nombre, precios, seguidos_por_alguien)
        eliminados = revisar_requisitos_permanencia(conn, recien_desestimados, seguidos_por_alguien)

        ESTADO["fase"] = "descargando_leaderboard"
        try:
            direcciones_conocidas = {r["address"].lower() for r in conn.execute("SELECT address FROM candidatos")}
            filas = _descargar_leaderboard()
        except Exception:
            print("fallo descargando el leaderboard:")
            traceback.print_exc()
            _enviar_resumen(recien_desestimados, eliminados, [])
            conn.close()
            return []

        preseleccion = _preseleccion(filas, direcciones_conocidas)
        ESTADO["fase"] = "evaluando"
        ESTADO["total"] = len(preseleccion)
        ESTADO["evaluados"] = 0
        if not preseleccion:
            _enviar_resumen(recien_desestimados, eliminados, [])
            conn.close()
            return []

        descubiertos = []
        MAX_INTENTOS_POR_FALLO_RED = 3
        intentos_de = {}
        pendientes = list(preseleccion)
        while pendientes:
            addr, cuenta, _roi_mes = pendientes.pop(0)
            ESTADO["actual"] = addr
            try:
                datos = hyperliquid.datos_de_trader(addr, spot_nombres, idx_por_nombre, precios)
            except Exception:
                print(f"fallo evaluando {addr}:")
                traceback.print_exc()
                intentos_de[addr] = intentos_de.get(addr, 0) + 1
                if intentos_de[addr] < MAX_INTENTOS_POR_FALLO_RED:
                    pendientes.append((addr, cuenta, _roi_mes))
                else:
                    print(f"{addr}: descartado tras {MAX_INTENTOS_POR_FALLO_RED} fallos de red")
                    ESTADO["evaluados"] += 1
                continue
            time.sleep(hyperliquid.SLEEP_ENTRE_LLAMADAS)

            ops = datos["operaciones_backtest"]
            bt = hyperliquid.backtest_trader(ops, cuenta, lados=("Long", "Short"))
            retorno_trading = bt["retorno_pct"] if bt else None
            puntuacion = hyperliquid.puntuacion_de(bt["retorno_pct"], bt["profit_factor"], -bt["drawdown"] * 100) if bt and retorno_trading is not None and not hyperliquid.veto_catastrofico(retorno_trading) else None
            bt_spot = hyperliquid.backtest_trader(ops, cuenta, lados=("Spot",))
            retorno_spot = bt_spot["retorno_pct"] if bt_spot else None
            puntuacion_spot = hyperliquid.puntuacion_de(bt_spot["retorno_pct"], bt_spot["profit_factor"], -bt_spot["drawdown"] * 100) if bt_spot and retorno_spot is not None and not hyperliquid.veto_catastrofico(retorno_spot) else None

            if (puntuacion or 0) < PUNTUACION_MINIMA and (puntuacion_spot or 0) < PUNTUACION_MINIMA:
                ESTADO["evaluados"] += 1
                continue

            ahora = int(time.time() * 1000)
            conn.execute(
                """INSERT INTO candidatos (address, categoria, antiguedad, estilo, riesgo, cuenta,
                   retorno_pct, profit_factor, puntuacion, win_rate, drawdown, puntuacion_spot, win_rate_spot,
                   retorno_pct_spot, drawdown_spot, profit_factor_spot, posicion_actual, holdings_spot, operaciones_recientes, descubierto_ts)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    addr, "descubierto", _antiguedad_dias(ops), "activo", "moderado", cuenta,
                    bt["retorno_pct"] if bt else None, bt["profit_factor"] if bt else None,
                    puntuacion, bt["win_rate"] if bt else None, bt["drawdown"] if bt else None,
                    puntuacion_spot, bt_spot["win_rate"] if bt_spot else None, retorno_spot,
                    bt_spot["drawdown"] if bt_spot else None, bt_spot["profit_factor"] if bt_spot else None,
                    json.dumps(datos["posicion_actual"], ensure_ascii=False),
                    json.dumps(datos["holdings_spot"], ensure_ascii=False),
                    json.dumps(datos["operaciones_recientes"], ensure_ascii=False),
                    ahora,
                ),
            )
            conn.commit()
            descubiertos.append((addr, puntuacion, puntuacion_spot))
            ESTADO["evaluados"] += 1
            ESTADO["descubiertos"] = len(descubiertos)
            time.sleep(hyperliquid.SLEEP_ENTRE_LLAMADAS)

        _enviar_resumen(recien_desestimados, eliminados, descubiertos)
        conn.close()
        return descubiertos
    finally:
        ESTADO.update(corriendo=False, fase=None, actual=None)


def _enviar_resumen(desestimados, eliminados, descubiertos):
    """Resumen semanal -- solo por Telegram (aviso operativo), nunca al
    frontend: el usuario decidio explicitamente que el resumen semanal de
    descubrimiento no es una notificacion de producto ('no es interesante, a
    no ser que se encuentre alguno super top'), asi que esto no escribe nada
    que el frontend vaya a leer."""
    if not desestimados and not eliminados and not descubiertos:
        return
    rank = lambda p: f"{p}/100" if p is not None else "sin dato"
    bloques = []
    if desestimados:
        lineas = "\n".join(f"• {addr[:8]} — {motivo}" for addr, motivo, p, ps in desestimados)
        bloques.append(f"<b>Desestimados ({len(desestimados)})</b>\n{lineas}")
    if eliminados:
        lineas = "\n".join(f"• {addr[:8]} — trading: {rank(p)} · spot: {rank(ps)}" for addr, p, ps in eliminados)
        bloques.append(f"<b>Eliminados de la lista ({len(eliminados)})</b>\n{lineas}")
    if descubiertos:
        lineas = "\n".join(f"• {addr[:8]} — trading: {rank(p)} · spot: {rank(ps)}" for addr, p, ps in descubiertos)
        bloques.append(f"<b>Nuevos descubiertos ({len(descubiertos)})</b>\n{lineas}")
    texto = "📋 <b>Resumen semanal de descubrimiento</b>\n\n" + "\n\n".join(bloques)
    telegram.enviar(texto)


def ciclo_descubrimiento():
    conn = db.conectar()
    ultima = db.meta_get(conn, "ultimo_descubrimiento")
    conn.close()
    if ultima:
        falta = INTERVALO_SEGUNDOS - (time.time() - float(ultima))
        if falta > 0:
            time.sleep(falta)

    while True:
        try:
            descubrir_candidatos()
        except Exception:
            print("fallo en el ciclo de descubrimiento:")
            traceback.print_exc()
        finally:
            conn = db.conectar()
            db.meta_set(conn, "ultimo_descubrimiento", str(time.time()))
            conn.close()
        time.sleep(INTERVALO_SEGUNDOS)
