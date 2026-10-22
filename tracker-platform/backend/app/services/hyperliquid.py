"""
Logica de Hyperliquid portada de copytrading/actualizar_posiciones.py y
copytrading/backtest_traders.py -- mismo comportamiento, solo movido aqui
para que el backend pueda refrescarse solo en bucle en vez de a mano.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ZONA_USUARIO = ZoneInfo("Europe/Madrid")

INFO_URL = "https://api.hyperliquid.xyz/info"
SLEEP_ENTRE_LLAMADAS = 0.3
DIAS_BACKTEST = 365  # un año de historial para puntuar a un trader (menos si no lleva tanto operando)
MAX_LOTES_FILLS = 10  # tope de llamadas paginando por si alguien es hiperactivo (10 x 2000 = 20000 fills, de sobra para un año)
MAX_FILLS_GUARDADOS = 2000  # cuantos fills se guardan en la BD para mostrar en el detalle -- el backtest usa TODOS los que haya en la ventana de 365 dias, no este limite (ver obtener_fills)
MIN_CIERRES_PARA_PUNTUAR = 10  # menos que esto es una muestra demasiado pequeña -- una buena/mala racha domina el resultado
MIN_DIAS_HISTORIAL_PARA_PUNTUAR = 30  # necesitamos verlo operar en mas de una sola racha/sesion, no solo "tuvo una buena tarde"
MAX_DIAS_INACTIVO_PARA_PUNTUAR = 21  # si su ultimo cierre es mas viejo que esto, ya no esta operando AHORA -- un historial genial de hace meses no sirve para copiarlo hoy
MIN_VALOR_HOLDING_SPOT = 5  # $ -- restos de centimos en la cartera (polvo/airdrops) no se muestran como si fueran una posicion real
UMBRAL_RETORNO_VETO = -15  # retorno (%) por debajo de esto descalifica del todo, aunque la otra faceta (trading/spot) vaya genial -- sangrar asi de mal en una no se compensa con ir bien en la otra
MIN_NOTIONAL_SPOT_PARA_CONTAR = 10  # $ -- ventas de shitcoins en centimos (polvo/airdrops) no cuentan como "trade": inflan el win rate y el profit factor sin representar capital real asignado
# se probo tambien exigir que la moneda fuera de una lista "seria" (BTC/ETH/
# acciones conocidas), pero en la practica nadie en spot cumple 10 cierres
# solo con eso -- la actividad real de esta gente es casi toda en altcoins
# pequeñas. El problema real nunca fue el NOMBRE de la moneda, fue contar
# centimos como trade -- eso ya lo resuelve MIN_NOTIONAL_SPOT_PARA_CONTAR solo.
MESES_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
STABLES = {"USDC", "USDT0", "USDH", "USDE"}


MAX_ESPERA_RATE_LIMIT = 30  # segundos -- techo del backoff, pero el 429 se reintenta sin limite de intentos


def fetch_json(payload, intentos=3):
    """intentos limita los fallos 'normales' (red, timeout) -- un 429 (rate
    limit) es distinto: no es un error real, es que hay que esperar, asi que
    se reintenta SIN limite de intentos (con backoff creciente) en vez de
    tirar al candidato entero. Preferimos tardar mucho a perder informacion."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(INFO_URL, data=body, headers={"Content-Type": "application/json"})
    i = 0
    intento_rate_limit = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            intento_rate_limit += 1
            time.sleep(min(MAX_ESPERA_RATE_LIMIT, 2 * intento_rate_limit))
        except (urllib.error.URLError, TimeoutError):
            if i == intentos - 1:
                raise
            time.sleep(1.5 * (i + 1))
            i += 1


def obtener_fills(address, desde_ms):
    """userFillsByTime devuelve como mucho ~2000 fills por llamada (en orden
    cronologico ascendente) -- para un trader activo, 2000 fills pueden
    cubrir muchos menos dias que DIAS_BACKTEST. Se pagina avanzando el
    startTime al ultimo fill recibido hasta cubrir toda la ventana o agotar
    MAX_LOTES_FILLS (tope de seguridad, no deberia alcanzarse en un año salvo
    actividad extrema)."""
    todos = []
    cursor = desde_ms
    ahora_ms = int(time.time() * 1000)
    for _ in range(MAX_LOTES_FILLS):
        lote = fetch_json({"type": "userFillsByTime", "user": address, "startTime": cursor})
        if not lote:
            break
        todos.extend(lote)
        ultimo_ts = max(f["time"] for f in lote)
        if ultimo_ts <= cursor or ultimo_ts >= ahora_ms or len(lote) < 2000:
            break  # no avanza, llegamos a "ahora", o el lote no estaba lleno -> no hay mas
        cursor = ultimo_ts + 1
        time.sleep(SLEEP_ENTRE_LLAMADAS)
    return todos


# UBTC/UETH/USOL en spot son el mismo activo que BTC/ETH/SOL (tokenizado via
# Unit) -- mismo alias que ya usa el frontend (ALIAS_MONEDA en index.html)
# para no dar la impresion de que son monedas distintas
ALIAS_MONEDA = {"UBTC": "BTC", "UETH": "ETH", "USOL": "SOL"}


def etiqueta_moneda(coin):
    # "xyz2:SP500", "hyna:BTC"... el prefijo es solo de que builder-dex
    # (HIP-3) lista ese mercado -- routing interno, nunca info util para
    # quien lo ve (ver CATEGORIA_* mas abajo para el mismo prefijo)
    _prefijo, _, base = coin.partition(":")
    base = base or coin
    return ALIAS_MONEDA.get(base, base)


_ALIAS_INVERSO = {alias: crudo for crudo, alias in ALIAS_MONEDA.items()}


def precio_actual(coin, tipo="trading"):
    """coin puede venir ya aliasado (ej. 'BTC' en vez del token spot real
    'UBTC', ver etiqueta_moneda) -- si el nombre directo no esta en el
    universo spot, se prueba con el ticker crudo que el alias esconde."""
    precios = fetch_json({"type": "allMids"})
    if tipo == "spot":
        idx_por_nombre = cargar_idx_por_nombre()
        idx = idx_por_nombre.get(coin) or idx_por_nombre.get(_ALIAS_INVERSO.get(coin))
        clave = f"@{idx}" if idx is not None else None
    else:
        clave = coin
    return float(precios[clave]) if clave and clave in precios else None


def cargar_spot_meta():
    data = fetch_json({"type": "spotMeta"})
    tokens = {t["index"]: t["name"] for t in data["tokens"]}
    nombres = {}
    for u in data["universe"]:
        base, _quote = u["tokens"]
        nombres[f"@{u['index']}"] = tokens.get(base, u["name"])
    return nombres


# Hyperliquid, via HIP-3, deja a terceros ("builders") listar sus propios
# mercados perpetuos con prefijo "dex:TICKER" (p.ej. "xyz:CRWV") -- la
# mayoria son replicas de acciones, pero no hay forma de saberlo por la API
# sola: algunos builders (p.ej. hyna) listan cripto bajo su propio prefijo.
# Por eso el criterio es: si el ticker (sin prefijo) ya existe en el
# universo cripto nativo de Hyperliquid (perp o spot), es cripto aunque
# venga con prefijo de builder; si no, se clasifica por palabra clave
# (materia prima / divisa / indice) y lo que sobra son acciones, que es la
# inmensa mayoria de lo que listan estos builders.
CATEGORIA_MATERIAS_PRIMAS = {
    "GOLD", "SILVER", "PLATINUM", "PALLADIUM", "COPPER", "ALUMINIUM", "URANIUM", "URNM",
    "OIL", "USOIL", "WTI", "BRENTOIL", "CL", "HO", "NATGAS", "GAS",
    "CORN", "WHEAT", "SOY", "GLDMINE", "GOLDJM", "SILVERJM",
}
CATEGORIA_DIVISAS = {"EUR", "GBP", "JPY", "KRW", "DXY"}
CATEGORIA_INDICES = {
    "SP500", "US500", "USA500", "XYZ100", "USTECH", "SMALL2000", "NIFTY", "IBOV", "KR200",
    "JP225", "VIX", "VOL", "MAG7", "SEMIS", "SEMI", "NUCLEAR", "DEFENSE", "BIOTECH", "INFOTECH",
    "ROBOT", "ENERGY", "USENERGY", "TLT", "USBOND", "10Y", "2Y", "30Y", "OTHERS", "TOTAL2", "BTCD",
}


def categoria_de(coin):
    """Clasifica un ticker (crudo, tal cual llega en los fills -- con o sin
    prefijo de builder-dex) en Cripto/Materia prima/Divisa/Índice/Acción,
    sin llamadas a Hyperliquid: si NO lleva prefijo ("xyz2:", "hyna:"...),
    es un mercado nativo de Hyperliquid, y eso es cripto el 100% de las
    veces hoy. Si lleva prefijo, se clasifica por palabra clave sobre el
    ticker base contra las listas de arriba; lo que no encaja en ninguna
    es Acción, que es la inmensa mayoria de lo que listan los builders."""
    _prefijo, separador, base = coin.partition(":")
    if not separador:
        return "Cripto"
    if base in CATEGORIA_MATERIAS_PRIMAS:
        return "Materia prima"
    if base in CATEGORIA_DIVISAS:
        return "Divisa"
    if base in CATEGORIA_INDICES:
        return "Índice"
    return "Acción"


def cargar_idx_por_nombre():
    """Nombre de moneda spot -> indice de su par, para precios.get(f"@{idx}").
    Algunas monedas (p.ej. UBTC) cotizan en mas de un par (UBTC/USDC Y
    UBTC/USDH) -- invertir cargar_spot_meta() a lo bruto (ultimo que aparezca
    en la lista gana) podia quedarse con el par equivocado, mas iliquido y con
    precio distinto al de verdad (bug real detectado: se cogia @234 UBTC/USDH,
    ~4000$ mas bajo que @142 UBTC/USDC, en una alerta de "añadido en spot").
    Aqui se prioriza siempre el par cotizado en USDC, el canonico."""
    data = fetch_json({"type": "spotMeta"})
    tokens = {t["index"]: t["name"] for t in data["tokens"]}
    idx_por_nombre = {}
    for u in data["universe"]:
        base, quote = u["tokens"]
        nombre = tokens.get(base, u["name"])
        es_usdc = tokens.get(quote) == "USDC"
        if nombre not in idx_por_nombre or es_usdc:
            idx_por_nombre[nombre] = str(u["index"])
    return idx_por_nombre


def formatear_time(ms):
    # en hora del usuario (Madrid), no UTC -- el servidor corre en UTC pero
    # el usuario esta en España, tanto en la web (ver fechaLocal en el
    # frontend) como en los avisos de Telegram
    dt = datetime.fromtimestamp(ms / 1000, tz=ZONA_USUARIO)
    return f"{dt.day:02d}-{MESES_EN[dt.month-1]} {dt.hour:02d}:{dt.minute:02d}"


def convertir_fill(f):
    d = f.get("dir", "")
    if d.startswith("Open"):
        accion, lado = "Abre", ("Long" if "Long" in d else "Short")
    elif d.startswith("Close"):
        accion, lado = "Cierra", ("Long" if "Long" in d else "Short")
    elif d == "Buy":
        accion, lado = "Abre", "Spot"
    elif d == "Sell":
        accion, lado = "Cierra", "Spot"
    else:
        accion, lado = "", ""
    sz, px = float(f["sz"]), float(f["px"])
    return {
        "coin": f["coin"], "lado": lado, "accion": accion, "px": px, "sz": sz,
        "notional": round(sz * px, 2), "time": formatear_time(f["time"]), "ts": f["time"],
        "closedPnl": round(float(f.get("closedPnl", 0) or 0), 2),
    }


def monedas_mas_usadas(operaciones_backtest, posicion_actual, holdings_spot, spot_nombres, n=5):
    """Top N monedas por frecuencia real de uso (sobre el AÑO completo del
    backtest, no solo los 2000 fills guardados) -- las que tiene abiertas
    ahora mismo van primero, da igual su frecuencia, y dentro de cada grupo
    se ordena por nº de operaciones. Esto es lo que se enseña como "tags"
    en el listado masivo de traders (ver candidatos.py _candidato_dict).

    La categoria hay que calcularla AQUI, sobre el ticker crudo (con su
    prefijo de builder-dex si lo tiene, ej. "xyz2:SP500") -- etiqueta_moneda
    ya lo quita para mostrar, y categoria_de necesita verlo para distinguir
    Nvidia/Gold/SP500 de una cripto nativa."""
    frecuencia: dict[str, int] = {}
    categorias: dict[str, str] = {}
    for o in operaciones_backtest:
        crudo = spot_nombres.get(o["coin"], o["coin"]) if o["lado"] == "Spot" else o["coin"]
        nombre = etiqueta_moneda(crudo)
        frecuencia[nombre] = frecuencia.get(nombre, 0) + 1
        categorias.setdefault(nombre, categoria_de(crudo))
    abiertas = {etiqueta_moneda(p["coin"]) for p in posicion_actual} | {etiqueta_moneda(h["coin"]) for h in holdings_spot}
    ordenadas = sorted(frecuencia, key=lambda m: (m not in abiertas, -frecuencia[m]))
    return [{"nombre": m, "categoria": categorias[m]} for m in ordenadas[:n]]


def tpsl_por_moneda(address):
    """Las ordenes stop-loss/take-profit son publicas igual que todo en
    Hyperliquid (frontendOpenOrders, isPositionTpsl=true) -- se devuelven
    agrupadas por moneda, cada una con su precio de disparo, sin decidir
    todavia si es SL o TP (eso depende de si esta por encima o por debajo
    del precio de entrada, que se sabe en posicion_actual_de)."""
    ordenes = fetch_json({"type": "frontendOpenOrders", "user": address})
    por_moneda = {}
    for o in ordenes:
        if not o.get("isPositionTpsl"):
            continue
        por_moneda.setdefault(o["coin"], []).append(round(float(o["triggerPx"]), 6))
    return por_moneda


def posicion_actual_de(address):
    data = fetch_json({"type": "clearinghouseState", "user": address})
    tpsl = tpsl_por_moneda(address)
    posiciones = []
    for ap in data.get("assetPositions", []):
        p = ap.get("position", {})
        szi = float(p.get("szi", 0) or 0)
        if abs(szi) < 1e-9:
            continue
        lado = "Long" if szi > 0 else "Short"
        entry_px = round(float(p.get("entryPx", 0) or 0), 6)
        stop_loss = take_profit = None
        for trigger_px in tpsl.get(p.get("coin"), []):
            # Long: SL por debajo de la entrada, TP por encima. Short: al reves.
            es_stop = (trigger_px < entry_px) if lado == "Long" else (trigger_px > entry_px)
            if es_stop:
                stop_loss = trigger_px
            else:
                take_profit = trigger_px
        posiciones.append({
            "coin": etiqueta_moneda(p.get("coin")), "lado": lado,
            "tamaño": round(abs(szi), 8), "entryPx": entry_px,
            "pnlNoRealizado": round(float(p.get("unrealizedPnl", 0) or 0), 2),
            "valorPosicion": round(abs(float(p.get("positionValue", 0) or 0)), 2),
            "stopLoss": stop_loss, "takeProfit": take_profit,
        })
    return posiciones


def holdings_spot_de(address, idx_por_nombre, precios):
    data = fetch_json({"type": "spotClearinghouseState", "user": address})
    holdings = []
    for b in data.get("balances", []):
        total = float(b.get("total", 0) or 0)
        if total < 1e-9 or b["coin"] in STABLES:
            continue
        coste = float(b.get("entryNtl", 0) or 0)
        idx = idx_por_nombre.get(b["coin"])
        precio_actual = precios.get(f"@{idx}") if idx is not None else None
        valor_actual = total * float(precio_actual) if precio_actual is not None else None
        # polvo: restos de airdrops/memecoins que valen centimos -- mostrarlos
        # como si fueran "la cartera" es enganoso (parece activo cuando no lo
        # esta). Si no sabemos el valor (precio_actual None) se deja pasar,
        # mejor mostrar de mas que ocultar algo real por falta de dato.
        if valor_actual is not None and valor_actual < MIN_VALOR_HOLDING_SPOT:
            continue
        holdings.append({
            "coin": etiqueta_moneda(b["coin"]), "tamaño": round(total, 8),
            "costeBase": round(coste, 2) if coste > 1e-9 else None,
            "valorActual": round(valor_actual, 2) if valor_actual is not None else None,
            "pnlNoRealizado": round(valor_actual - coste, 2) if (valor_actual is not None and coste > 1e-9) else None,
        })
    return holdings


def posicion_y_holdings_de(address, idx_por_nombre, precios):
    """La parte barata de datos_de_trader (2 llamadas en vivo, sin pedir el
    año de fills) -- lo unico que hace falta para detectar una posicion
    nueva o un cambio, que es lo que de verdad necesita mirarse cada 5
    minutos. El backtest completo (obtener_fills + puntuacion) no cambia de
    un momento a otro, no hace falta repetirlo tan a menudo (ver
    refresher.ciclo_backtest_diario)."""
    posiciones = posicion_actual_de(address)
    time.sleep(SLEEP_ENTRE_LLAMADAS)
    holdings = holdings_spot_de(address, idx_por_nombre, precios)
    time.sleep(SLEEP_ENTRE_LLAMADAS)
    return posiciones, holdings


def datos_de_trader(address, spot_nombres, idx_por_nombre, precios):
    """Todo lo que necesitamos de un trader en una pasada: fills, posicion
    actual y holdings spot -- lo que antes escribia actualizar_posiciones.py
    a un fichero, aqui se devuelve directamente."""
    desde_ms = int((time.time() - DIAS_BACKTEST * 86400) * 1000)
    fills = obtener_fills(address, desde_ms)
    time.sleep(SLEEP_ENTRE_LLAMADAS)
    posiciones = posicion_actual_de(address)
    time.sleep(SLEEP_ENTRE_LLAMADAS)
    holdings = holdings_spot_de(address, idx_por_nombre, precios)
    time.sleep(SLEEP_ENTRE_LLAMADAS)

    fills_utiles = [f for f in fills if f.get("dir") != "Spot Dust Conversion"]
    fills_ordenados = sorted(fills_utiles, key=lambda f: -f["time"])
    operaciones_todas = [convertir_fill(f) for f in fills_ordenados]
    return {
        # el backtest necesita TODO el año para puntuar bien
        "operaciones_backtest": operaciones_todas,
        # pero solo se guarda en la BD un recorte reciente (son las que se
        # muestran en el detalle de la UI; un año entero de fills no hace
        # falta guardarlo completo, solo usarlo para calcular la puntuacion)
        "operaciones_recientes": operaciones_todas[:MAX_FILLS_GUARDADOS],
        "posicion_actual": posiciones,
        "holdings_spot": holdings,
    }


def construir_episodios(operaciones):
    """Agrupa los fills por moneda+lado en episodios -- una posicion completa
    desde que se abre (neto 0 -> algo) hasta que se cierra del todo (neto
    vuelve a 0), pasando por cuantos añadidos/reducciones haya en medio.
    Mismo algoritmo que construirBloques() en el frontend (static/index.html)."""
    cronologico = list(reversed(operaciones))
    episodios = []
    abierto_por_clave = {}
    for o in cronologico:
        lado = o.get("lado")
        if lado not in ("Long", "Short", "Spot"):
            continue
        clave = (o["coin"], lado)
        idx = abierto_por_clave.get(clave)
        if idx is None:
            idx = len(episodios)
            episodios.append({"coin": o["coin"], "lado": lado, "filas": [], "neto": 0.0,
                               "abierta": True, "truncada": o["accion"] == "Cierra"})
            abierto_por_clave[clave] = idx
        ep = episodios[idx]
        ep["filas"].append(o)
        ep["neto"] = round(ep["neto"] + (o["sz"] if o["accion"] == "Abre" else -o["sz"]), 8)
        if abs(ep["neto"]) < 0.00001:
            ep["abierta"] = False
            del abierto_por_clave[clave]
    return episodios


def backtest_trader(operaciones, cuenta=None, lados=("Long", "Short")):
    """Agrupa los fills en episodios por posicion (un episodio = desde que se
    abre hasta que se cierra del todo, incluyendo los añadidos/reducciones de
    en medio -- no solo el primer y el ultimo fill) y puntua cada episodio YA
    CERRADO como un trade. Uno todavia abierto no cuenta: no tiene pnl
    realizado del todo, y contarlo seria mirar un resultado que aun no ha
    pasado. 'lados' separa trading (Long/Short) de spot -- Hyperliquid tambien
    reporta closedPnl != 0 en ventas spot, y mezclarlo con trading contaminaba
    la puntuacion con una actividad que no es lo que se copia con 'Abrir'.

    En spot NO se agrupa por episodio: una cartera spot casi nunca vuelve a
    quedarse en 0 (dust, rebalanceos continuos), asi que exigir que el
    episodio se cierre del todo dejaba 0 trades cerrados siempre -- cada
    venta realizada cuenta por si sola, como pnl ya materializado que es."""
    if lados == ("Spot",):
        eventos = [
            (o["ts"], o["closedPnl"]) for o in operaciones
            if o["accion"] == "Cierra" and o["lado"] == "Spot" and o["closedPnl"] != 0
            and abs(o["notional"]) >= MIN_NOTIONAL_SPOT_PARA_CONTAR
        ]
    else:
        cerrados = [e for e in construir_episodios(operaciones) if not e["abierta"] and e["lado"] in lados]
        # un episodio se lista por cuando se ABRIO, no por cuando se cerro --
        # para la curva de equity/drawdown necesitamos el orden de cuando se
        # REALIZA cada pnl, que es el momento del ultimo fill (el que lo deja
        # en neto 0)
        eventos = [(e["filas"][-1]["ts"], round(sum(f["closedPnl"] for f in e["filas"]), 2)) for e in cerrados]
    eventos.sort(key=lambda t: t[0])
    eventos_no_cero = [(ts, v) for ts, v in eventos if v != 0]
    cierres = [round(v, 2) for _, v in eventos_no_cero]
    if len(cierres) < MIN_CIERRES_PARA_PUNTUAR:
        return None  # una o dos operaciones sueltas es una moneda al aire, no una puntuacion fiable
    dias_cubiertos = (eventos_no_cero[-1][0] - eventos_no_cero[0][0]) / 86400000
    if dias_cubiertos < MIN_DIAS_HISTORIAL_PARA_PUNTUAR:
        return None  # necesitamos verlo actuar en mas de una racha/sesion, no solo una buena tarde
    dias_desde_ultimo_cierre = (time.time() * 1000 - eventos_no_cero[-1][0]) / 86400000
    if dias_desde_ultimo_cierre > MAX_DIAS_INACTIVO_PARA_PUNTUAR:
        return None  # lleva demasiado sin operar -- un historial bueno de hace meses no dice nada de si lo esta haciendo bien AHORA
    pnl_total = sum(cierres)
    ganadores = [c for c in cierres if c > 0]
    perdedores = [c for c in cierres if c < 0]
    win_rate = len(ganadores) / len(cierres)
    ganancia_bruta = sum(ganadores)
    perdida_bruta = abs(sum(perdedores))
    profit_factor = (ganancia_bruta / perdida_bruta) if perdida_bruta > 0 else None

    acumulado = pico = max_dd = 0.0
    for c in cierres:  # ya en orden cronologico ascendente
        acumulado += c
        pico = max(pico, acumulado)
        max_dd = min(max_dd, acumulado - pico)

    return {
        "pnl_total": round(pnl_total, 2),
        "retorno_pct": round(pnl_total / cuenta * 100, 1) if cuenta else None,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "drawdown": round(min(abs(max_dd) / cuenta, 1.0), 4) if cuenta else None,
    }


def puntuacion_de(retorno_pct, profit_factor, drawdown_pct):
    if retorno_pct is None or drawdown_pct is None:
        return None
    p_retorno = max(0, min(100, 50 + retorno_pct))
    p_pf = max(0, min(100, (profit_factor if profit_factor is not None else 10) * 10))
    p_dd = max(0, min(100, 100 + drawdown_pct * 2))
    return round(p_retorno * 0.4 + p_pf * 0.3 + p_dd * 0.3)


def veto_catastrofico(retorno_pct):
    """True si hay suficiente muestra (retorno_pct viene de un bt que ya paso
    el minimo de cierres/dias) y ese retorno es un desastre -- esto
    descalifica sin importar lo bien que vaya la otra faceta (trading/spot).
    None (sin datos suficientes) nunca veta -- falta de muestra no es lo
    mismo que mal resultado."""
    return retorno_pct is not None and retorno_pct < UMBRAL_RETORNO_VETO


def _demo():
    DIA = 86400000
    # todo el demo usa ts relativos pequeños (0, DIA, 2*DIA...) como si fuera
    # 1970 -- con el nuevo filtro de inactividad (MAX_DIAS_INACTIVO_PARA_PUNTUAR)
    # eso haria que todo pareciera "inactivo desde hace 56 años" y nada
    # puntuara. BASE ancla el final de la linea de tiempo sintetica a hace
    # pocos dias (el timeline mas largo del demo no pasa de ~50*DIA).
    BASE = int(time.time() * 1000) - 60 * DIA

    def fill(coin, lado, accion, sz, closed_pnl, ts):
        return {"coin": coin, "lado": lado, "accion": accion, "sz": sz, "px": 1,
                "notional": sz, "time": "x", "ts": BASE + ts, "closedPnl": closed_pnl}

    def relleno(n, lado, ts_inicio, paso_ms, pnl_cada_uno=1):
        """n episodios triviales open+close en monedas distintas, solo para
        superar el minimo de cierres/dias que exige backtest_trader sin
        interferir con el episodio bajo prueba."""
        ops = []
        sz = 20  # notional=sz*px=20 con px=1, por encima de MIN_NOTIONAL_SPOT_PARA_CONTAR
        for i in range(n):
            ts = ts_inicio + i * paso_ms
            # en spot no hace falta moneda distinta por iteracion (no se
            # agrupa en episodios); usamos una de la allowlist para que
            # el filtro de MONEDAS_SPOT_RELEVANTES no la descarte
            coin = "BTC" if lado == "Spot" else f"FILL{i}"
            ops.append(fill(coin, lado, "Abre", sz, 0, ts))
            ops.append(fill(coin, lado, "Cierra", sz, pnl_cada_uno, ts + 1))
        return list(reversed(ops))  # mas reciente primero, como lo entrega Hyperliquid

    # episodio bajo prueba: abre, añade, reduce parcial, cierra del todo --
    # 4 fills, 1 solo trade (no 2 "cierres" sueltos)
    ops_prueba = [
        fill("BTC", "Long", "Cierra", 2, 50, 3 * DIA),   # cierra del todo (neto llega a 0)
        fill("BTC", "Long", "Cierra", 1, 10, 2 * DIA),   # reduce parcial
        fill("BTC", "Long", "Abre", 1, 0, DIA),          # añade
        fill("BTC", "Long", "Abre", 2, 0, 0),            # abre (inicio)
    ]
    episodios = construir_episodios(ops_prueba)
    assert len(episodios) == 1, episodios
    assert not episodios[0]["abierta"]
    assert len(episodios[0]["filas"]) == 4

    # por debajo del minimo de cierres/dias no debe puntuar, aunque el pnl sea bueno
    assert backtest_trader(ops_prueba, cuenta=1000, lados=("Long", "Short")) is None

    relleno_trading = relleno(10, "Long", 10 * DIA, 4 * DIA)  # 11 cierres en total, ~46 dias de span
    ops = ops_prueba + relleno_trading
    bt = backtest_trader(ops, cuenta=1000, lados=("Long", "Short"))
    assert bt is not None, "con 11 cierres y mas de 30 dias deberia puntuar"
    assert bt["pnl_total"] == 70, bt  # 50+10 del episodio de prueba + 10 de relleno (1 cada uno)
    assert bt["win_rate"] == 1.0, bt

    # una posicion todavia abierta no debe contar como trade cerrado
    ops_abierta = [fill("ETH", "Short", "Abre", 1, 0, 100)]
    assert backtest_trader(ops_abierta) is None

    # spot con closedPnl no debe colarse en el backtest de trading
    relleno_spot = relleno(10, "Spot", 10 * DIA, 4 * DIA, pnl_cada_uno=5)
    ops_mixto = ops + [fill("SOL", "Spot", "Cierra", 50, 999, 5 * DIA), fill("SOL", "Spot", "Abre", 50, 0, 4 * DIA)] + relleno_spot
    bt_mixto = backtest_trader(ops_mixto, cuenta=1000, lados=("Long", "Short"))
    assert bt_mixto["pnl_total"] == 70, bt_mixto
    bt_spot = backtest_trader(ops_mixto, cuenta=1000, lados=("Spot",))
    assert bt_spot["pnl_total"] == 999 + 10 * 5, bt_spot

    # spot con dust (nunca vuelve a 0 del todo) debe seguir contando la venta
    # realizada -- si esto exigiera episodio cerrado del todo, daria None
    ops_spot_dust = [
        fill("ETH", "Spot", "Cierra", 30, 200, DIA),  # vende una parte (queda resto)
        fill("ETH", "Spot", "Abre", 100, 0, 0),
    ] + relleno_spot
    ep_eth = next(e for e in construir_episodios(ops_spot_dust) if e["coin"] == "ETH")
    assert ep_eth["abierta"]  # nunca cierra del todo
    bt_dust = backtest_trader(ops_spot_dust, cuenta=1000, lados=("Spot",))
    assert bt_dust["pnl_total"] == 200 + 10 * 5, bt_dust

    # ventas de shitcoins en centimos (notional por debajo del minimo) no
    # deben contar como trade -- si no, un monton de "polvo" vendido con pnl
    # positivo de centimos infla el win rate/profit factor sin representar
    # capital real asignado
    relleno_spot_grande = relleno(10, "Spot", 10 * DIA, 4 * DIA, pnl_cada_uno=5)
    ops_con_dust = relleno_spot_grande + [fill("DUST", "Spot", "Cierra", 1, 0.01, 5 * DIA)]
    bt_sin_dust = backtest_trader(relleno_spot_grande, cuenta=1000, lados=("Spot",))
    bt_con_dust = backtest_trader(ops_con_dust, cuenta=1000, lados=("Spot",))
    assert bt_con_dust["pnl_total"] == bt_sin_dust["pnl_total"], (bt_con_dust, bt_sin_dust)

    # veto: un retorno catastrofico descalifica sin importar la puntuacion
    assert veto_catastrofico(-30) is True
    assert veto_catastrofico(-10) is False
    assert veto_catastrofico(None) is False  # sin muestra suficiente no se veta, no es lo mismo que ir mal

    print("hyperliquid._demo: OK")


if __name__ == "__main__":
    _demo()
