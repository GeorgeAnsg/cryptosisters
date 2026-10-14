"""
Logica de Hyperliquid portada de copytrading/actualizar_posiciones.py y
copytrading/backtest_traders.py -- mismo comportamiento, solo movido aqui
para que el backend pueda refrescarse solo en bucle en vez de a mano.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

INFO_URL = "https://api.hyperliquid.xyz/info"
SLEEP_ENTRE_LLAMADAS = 0.3
MAX_FILLS_GUARDADOS = 500
MESES_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
STABLES = {"USDC", "USDT0", "USDH", "USDE"}


def fetch_json(payload, intentos=3):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(INFO_URL, data=body, headers={"Content-Type": "application/json"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError):
            if i == intentos - 1:
                raise
            time.sleep(1.5 * (i + 1))


def cargar_spot_meta():
    data = fetch_json({"type": "spotMeta"})
    tokens = {t["index"]: t["name"] for t in data["tokens"]}
    nombres = {}
    for u in data["universe"]:
        base, _quote = u["tokens"]
        nombres[f"@{u['index']}"] = tokens.get(base, u["name"])
    return nombres


def formatear_time(ms):
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
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


def posicion_actual_de(address):
    data = fetch_json({"type": "clearinghouseState", "user": address})
    posiciones = []
    for ap in data.get("assetPositions", []):
        p = ap.get("position", {})
        szi = float(p.get("szi", 0) or 0)
        if abs(szi) < 1e-9:
            continue
        posiciones.append({
            "coin": p.get("coin"), "lado": "Long" if szi > 0 else "Short",
            "tamaño": round(abs(szi), 8), "entryPx": round(float(p.get("entryPx", 0) or 0), 6),
            "pnlNoRealizado": round(float(p.get("unrealizedPnl", 0) or 0), 2),
            "valorPosicion": round(abs(float(p.get("positionValue", 0) or 0)), 2),
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
        holdings.append({
            "coin": b["coin"], "tamaño": round(total, 8),
            "costeBase": round(coste, 2) if coste > 1e-9 else None,
            "valorActual": round(valor_actual, 2) if valor_actual is not None else None,
            "pnlNoRealizado": round(valor_actual - coste, 2) if (valor_actual is not None and coste > 1e-9) else None,
        })
    return holdings


def datos_de_trader(address, spot_nombres, idx_por_nombre, precios):
    """Todo lo que necesitamos de un trader en una pasada: fills, posicion
    actual y holdings spot -- lo que antes escribia actualizar_posiciones.py
    a un fichero, aqui se devuelve directamente."""
    fills = fetch_json({"type": "userFills", "user": address})
    time.sleep(SLEEP_ENTRE_LLAMADAS)
    posiciones = posicion_actual_de(address)
    time.sleep(SLEEP_ENTRE_LLAMADAS)
    holdings = holdings_spot_de(address, idx_por_nombre, precios)
    time.sleep(SLEEP_ENTRE_LLAMADAS)

    fills_utiles = [f for f in fills if f.get("dir") != "Spot Dust Conversion"]
    fills_ordenados = sorted(fills_utiles, key=lambda f: -f["time"])[:MAX_FILLS_GUARDADOS]
    operaciones = [convertir_fill(f) for f in fills_ordenados]
    return {"operaciones_recientes": operaciones, "posicion_actual": posiciones, "holdings_spot": holdings}


def backtest_trader(operaciones, cuenta=None):
    """Portado de copytrading/backtest_traders.py sin cambios de logica."""
    cierres = [f["closedPnl"] for f in operaciones if f["accion"] == "Cierra" and f["closedPnl"] != 0]
    if not cierres:
        return None
    pnl_total = sum(cierres)
    ganadores = [c for c in cierres if c > 0]
    perdedores = [c for c in cierres if c < 0]
    win_rate = len(ganadores) / len(cierres)
    ganancia_bruta = sum(ganadores)
    perdida_bruta = abs(sum(perdedores))
    profit_factor = (ganancia_bruta / perdida_bruta) if perdida_bruta > 0 else None

    acumulado = pico = max_dd = 0.0
    for c in reversed(cierres):
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
