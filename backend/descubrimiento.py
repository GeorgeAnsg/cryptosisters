"""
Descubrimiento de traders nuevos via el leaderboard publico de Hyperliquid.

No forma parte del ciclo de refresco de 5 minutos (ver refresher.py) -- esto
corre mucho menos a menudo (ciclo_descubrimiento llama cada
INTERVALO_SEGUNDOS, pensado para una vez a la semana: quien destaca o se
hunde en el leaderboard no cambia de un dia para otro, y evaluar un
candidato de verdad significa pedirle a Hyperliquid su año completo de
fills, igual que a los que ya se siguen -- varias llamadas por candidato.
"""
import json
import time
import traceback
import urllib.request

import db
import hyperliquid
import nombres
import refresher
import telegram

LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
INTERVALO_SEGUNDOS = 7 * 24 * 60 * 60

CUENTA_MINIMA = 10_000  # por debajo de esto no hay suficiente "piel en el juego"
# sin techo de cuenta: el riesgo de "ballena no replicable" es un problema de
# cuanto copiar, no de si el trader es bueno -- descartaba 785 cuentas de golpe
# sin mirar nada mas (ver conversacion 17-oct-2026)
ROI_MES_MINIMO = 0.05  # preseleccion rapida con el ROI del mes que ya da el leaderboard
MAX_CANDIDATOS_A_EVALUAR = 100  # cuantos candidatos se backtestean a fondo por ejecucion (cada uno son varias llamadas a la API)
PUNTUACION_MINIMA = 70  # umbral para considerarlo un descubrimiento real (trading o spot)
PUNTUACION_MINIMA_MANTENER = 50  # umbral para dejar de seguir -- mas bajo que el de descubrir, para no quitar a alguien por una mala racha puntual (histeresis)


def _descargar_leaderboard():
    req = urllib.request.Request(LEADERBOARD_URL)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["leaderboardRows"]


def _preseleccion(filas, direcciones_conocidas):
    """Filtro barato (sin pedir nada mas a Hyperliquid) usando solo lo que
    ya trae el leaderboard: tamaño de cuenta razonable y buen ROI este mes,
    exigiendo ademas que la semana y el historial completo tambien esten en
    positivo -- un solo mes bueno es ruido (puede ser una racha de suerte en
    una moneda volatil); pedir las tres ventanas en positivo favorece
    consistencia sobre un pico aislado. Reduce 40k+ filas a un puñado antes
    de gastar llamadas en backtests de verdad."""
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
    """Lo contrario del descubrimiento: trading y spot se dejan de seguir por
    SEPARADO -- si solo cae la faceta de trading por debajo del umbral de
    mantenimiento, se apaga solo sigue_trading (y se sigue teniendo su spot
    si lo tenia activo, y viceversa). (El veto por retorno catastrofico --
    hyperliquid.veto_catastrofico -- ya se aplica al refrescar, anulando
    SOLO la puntuacion de la faceta mala; aqui no hace falta mirarlo aparte,
    ya viene reflejado en puntuacion/puntuacion_spot.) La puntuacion ya la
    mantiene al dia el ciclo de refresco normal (cada 5 min) -- aqui solo se
    compara contra el umbral, sin pedir nada nuevo a Hyperliquid. Los
    'especulativo' nunca se dejan de seguir por esta via -- son apuestas
    curadas a mano, no traders a juzgar por backtest."""
    siguiendo = conn.execute(
        "SELECT address, puntuacion, puntuacion_spot, sigue_trading, sigue_spot FROM candidatos "
        "WHERE siguiendo=1 AND categoria!='especulativo'"
    ).fetchall()
    desestimados = []  # (addr, faceta, puntuacion_de_esa_faceta)
    for c in siguiendo:
        p, ps = c["puntuacion"], c["puntuacion_spot"]
        # p/ps en None (nunca se ha podido hacer backtest, p.ej. recien
        # seguido) nunca hace caer la faceta -- sin base para decidir
        cae_trading = c["sigue_trading"] and p is not None and p < PUNTUACION_MINIMA_MANTENER
        cae_spot = c["sigue_spot"] and ps is not None and ps < PUNTUACION_MINIMA_MANTENER
        if not cae_trading and not cae_spot:
            continue
        if cae_trading:
            conn.execute("UPDATE candidatos SET sigue_trading=0 WHERE address=?", (c["address"],))
            desestimados.append((c["address"], "trading", p))
        if cae_spot:
            conn.execute("UPDATE candidatos SET sigue_spot=0 WHERE address=?", (c["address"],))
            desestimados.append((c["address"], "spot", ps))
        conn.execute("UPDATE candidatos SET siguiendo=(sigue_trading OR sigue_spot) WHERE address=?", (c["address"],))
        conn.commit()
    return desestimados


def refrescar_no_seguidos(conn, spot_nombres, idx_por_nombre, precios):
    """Segundo escalon: a los que YA no se siguen (los originales que nunca
    se han seguido, y los que revisar_desestimados acaba de bajar) solo el
    ciclo de refresco de 5 min los deja al dia -- y ese SOLO toca a
    siguiendo=1. Sin esto, revisar_requisitos_permanencia juzgaria con
    puntuaciones congeladas en el momento en que se dejaron de seguir (o,
    para los nunca seguidos, con las del migrado original). Los 'especulativo'
    (apuestas curadas a mano, no traders a puntuar por backtest) se saltan --
    no tiene sentido evaluarlos ni dejar que acaben borrados por no pasar un
    umbral que no les corresponde."""
    direcciones = [r["address"] for r in conn.execute("SELECT address FROM candidatos WHERE siguiendo=0 AND categoria!='especulativo'")]
    for addr in direcciones:
        try:
            refresher.actualizar_datos_y_puntuacion(conn, addr, spot_nombres, idx_por_nombre, precios)
            conn.commit()
        except Exception:
            print(f"fallo refrescando (no seguido) {addr}:")
            traceback.print_exc()
        time.sleep(hyperliquid.SLEEP_ENTRE_LLAMADAS)


def revisar_requisitos_permanencia(conn, recien_desestimados):
    """Simetrico al descubrimiento: el mismo umbral que hace falta para
    ENTRAR en la lista (PUNTUACION_MINIMA) hace falta para seguir en ella --
    aplica a CUALQUIER candidato no seguido, sean los 25 originales o uno
    descubierto hace tiempo. Quien ya no lo cumple se borra de verdad (no
    solo se deja de seguir), con aviso previo por Telegram. (El veto por
    retorno catastrofico ya viene reflejado en puntuacion/puntuacion_spot
    desde que se refresco -- ver refresher.actualizar_datos_y_puntuacion.)

    'recien_desestimados' (los que revisar_desestimados acaba de bajar este
    mismo ciclo) tienen un ciclo entero de margen antes de poder ser
    borrados -- nadie se entera de que se le ha dejado de seguir Y
    desaparece de la lista en el mismo aviso. Los 'especulativo' nunca se
    borran por esta via (ver refrescar_no_seguidos)."""
    direcciones_con_margen = {a for a, *_ in recien_desestimados}
    filas = conn.execute(
        "SELECT address, puntuacion, puntuacion_spot, siguiendo FROM candidatos WHERE siguiendo=0 AND categoria!='especulativo'"
    ).fetchall()
    eliminados = []
    for c in filas:
        if c["address"] in direcciones_con_margen:
            continue
        p, ps = c["puntuacion"], c["puntuacion_spot"]
        if p is None and ps is None:
            continue  # nunca se le ha podido hacer backtest -- sin base para decidir
        if (p or 0) >= PUNTUACION_MINIMA or (ps or 0) >= PUNTUACION_MINIMA:
            continue
        conn.execute("DELETE FROM candidatos WHERE address=?", (c["address"],))
        conn.commit()
        eliminados.append((c["address"], p, ps))
    return eliminados


def descubrir_candidatos():
    """Un ciclo completo, en dos escalones de salida y uno de entrada:
    1. revisar_desestimados: a quien sigues y ya no rinde, se le deja de
       seguir solo (sigue en la lista).
    2. refrescar_no_seguidos + revisar_requisitos_permanencia: a TODO el que
       no se sigue (los originales nunca seguidos, y los que acaban de bajar
       del escalon 1) se le pone al dia la puntuacion y, si ya no cumple el
       mismo minimo por el que habria entrado, se borra de verdad de la lista.
    3. descubrimiento: baja el leaderboard, preselecciona por ROI del mes, y
       a los que pasan ese primer corte les hace el MISMO backtest riguroso
       (episodios, trading separado de spot, año completo) que a cualquier
       candidato ya existente -- nada entra sin pasar la misma verificacion."""
    conn = db.conectar()
    recien_desestimados = revisar_desestimados(conn)

    spot_nombres = hyperliquid.cargar_spot_meta()
    idx_por_nombre = hyperliquid.cargar_idx_por_nombre()
    precios = hyperliquid.fetch_json({"type": "allMids"})

    refrescar_no_seguidos(conn, spot_nombres, idx_por_nombre, precios)
    eliminados = revisar_requisitos_permanencia(conn, recien_desestimados)

    try:
        direcciones_conocidas = {r["address"].lower() for r in conn.execute("SELECT address FROM candidatos")}
        filas = _descargar_leaderboard()
    except Exception:
        print("fallo descargando el leaderboard:")
        traceback.print_exc()
        _enviar_resumen(conn, recien_desestimados, eliminados, [])
        conn.close()
        return []

    preseleccion = _preseleccion(filas, direcciones_conocidas)
    if not preseleccion:
        _enviar_resumen(conn, recien_desestimados, eliminados, [])
        conn.close()
        return []

    descubiertos = []
    for addr, cuenta, _roi_mes in preseleccion:
        try:
            datos = hyperliquid.datos_de_trader(addr, spot_nombres, idx_por_nombre, precios)
        except Exception:
            print(f"fallo evaluando {addr}:")
            traceback.print_exc()
            continue
        time.sleep(hyperliquid.SLEEP_ENTRE_LLAMADAS)

        ops = datos["operaciones_backtest"]
        # si una faceta (trading o spot) tiene un retorno catastrofico, esa
        # faceta concreta se anula (no cuenta) -- pero no descalifica al
        # candidato entero: si la OTRA faceta pasa el minimo, entra igual,
        # solo que por esa parte buena (ver hyperliquid.veto_catastrofico)
        bt = hyperliquid.backtest_trader(ops, cuenta, lados=("Long", "Short"))
        retorno_trading = bt["retorno_pct"] if bt else None
        puntuacion = hyperliquid.puntuacion_de(bt["retorno_pct"], bt["profit_factor"], -bt["drawdown"] * 100) if bt and retorno_trading is not None and not hyperliquid.veto_catastrofico(retorno_trading) else None
        bt_spot = hyperliquid.backtest_trader(ops, cuenta, lados=("Spot",))
        retorno_spot = bt_spot["retorno_pct"] if bt_spot else None
        puntuacion_spot = hyperliquid.puntuacion_de(bt_spot["retorno_pct"], bt_spot["profit_factor"], -bt_spot["drawdown"] * 100) if bt_spot and retorno_spot is not None and not hyperliquid.veto_catastrofico(retorno_spot) else None

        if (puntuacion or 0) < PUNTUACION_MINIMA and (puntuacion_spot or 0) < PUNTUACION_MINIMA:
            continue

        ahora = int(time.time() * 1000)
        conn.execute(
            """INSERT INTO candidatos (address, categoria, antiguedad, estilo, riesgo, cuenta, siguiendo,
               retorno_pct, profit_factor, puntuacion, win_rate, drawdown, puntuacion_spot, win_rate_spot,
               retorno_pct_spot, drawdown_spot, profit_factor_spot, posicion_actual, holdings_spot, operaciones_recientes, descubierto_ts)
               VALUES (?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
        time.sleep(hyperliquid.SLEEP_ENTRE_LLAMADAS)

    _enviar_resumen(conn, recien_desestimados, eliminados, descubiertos)
    conn.close()
    return descubiertos


def _enviar_resumen(conn, desestimados, eliminados, descubiertos):
    """Un solo aviso por ciclo (semanal) en vez de uno por trader -- antes
    una semana movida podia mandar media docena de mensajes sueltos. Se
    manda por Telegram Y se guarda en 'notificaciones' para el modal de la
    campanita en la web; si no ha pasado nada en todo el ciclo (lo normal
    la mayoria de semanas), no se manda ni se guarda nada."""
    if not desestimados and not eliminados and not descubiertos:
        return
    todas = [r[0] for r in conn.execute("SELECT address FROM candidatos").fetchall()]
    rank = lambda p: f"{p}/100" if p is not None else "sin dato"
    bloques = []
    if desestimados:
        lineas = "\n".join(f"• {nombres.nombre_de(addr, todas)} — {faceta} ({rank(p)})" for addr, faceta, p in desestimados)
        bloques.append(f"<b>Dejado de seguir ({len(desestimados)})</b>\n{lineas}")
    if eliminados:
        lineas = "\n".join(f"• {nombres.nombre_de(addr, todas)} — trading: {rank(p)} · spot: {rank(ps)}" for addr, p, ps in eliminados)
        bloques.append(f"<b>Eliminados de la lista ({len(eliminados)})</b>\n{lineas}")
    if descubiertos:
        lineas = "\n".join(f"• {nombres.nombre_de(addr, todas)} — trading: {rank(p)} · spot: {rank(ps)}" for addr, p, ps in descubiertos)
        bloques.append(f"<b>Nuevos descubiertos ({len(descubiertos)})</b>\n{lineas}")
    texto = "📋 <b>Resumen semanal de Seguimiento</b>\n\n" + "\n\n".join(bloques)
    telegram.enviar(texto)
    db.crear_notificacion(conn, texto)


def ciclo_descubrimiento():
    # un reinicio del proceso (cada deploy) no debe relanzar el descubrimiento
    # de golpe -- se guarda cuando se ejecuto de verdad por ultima vez y, si
    # no ha pasado una semana desde entonces, se espera lo que falte antes
    # del primer ciclo en vez de arrancar inmediatamente
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
