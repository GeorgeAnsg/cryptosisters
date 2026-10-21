"""Pool de descubrimiento (global, no por usuario -- el seguimiento personal
vive en usuario_sigue, ver usuarios.py). Expone en un solo payload todo lo
que el frontend necesita para derivar Traders/Posiciones/Consenso/
Notificaciones sin mocks, con la misma forma que ya usaban los mocks."""
import json
import time

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import usuario_actual
from app.db import database as db
from app.services import hyperliquid, nombres

router = APIRouter(prefix="/candidatos", tags=["candidatos"])

VENTANA_MOVIMIENTOS_MS = 72 * 60 * 60 * 1000  # mismo alcance que la ventana de consenso

# @107/@142/... -> HYPE/UBTC/... (indices internos de spot en Hyperliquid,
# ver hyperliquid.cargar_spot_meta) -- cambia pratimente nunca, asi que se
# carga una vez por proceso en vez de pedirselo a Hyperliquid en cada
# peticion de /candidatos
_SPOT_NOMBRES: dict[str, str] | None = None


def _spot_nombres() -> dict[str, str]:
    global _SPOT_NOMBRES
    if _SPOT_NOMBRES is None:
        try:
            _SPOT_NOMBRES = hyperliquid.cargar_spot_meta()
        except Exception:
            return {}
    return _SPOT_NOMBRES


def _nombre_moneda(coin: str) -> str:
    return _spot_nombres().get(coin, coin)


def _categoria_de(coin: str) -> str:
    # el pool de descubrimiento de Hyperliquid es todo cripto; sin una fuente
    # real de categoria por moneda, todo cae en "Cripto" -- correcto para el
    # 100% de los casos reales hoy, se ajusta si algun dia hay otra cosa
    return "Cripto"


def _movimientos_de(conn, addr: str, tipo: str) -> list[dict]:
    """tipo: 'trading' o 'spot' -- traduce las filas de 'alertas' (que guarda
    tamaño/tamaño_antes/precio/detectado) al mismo vocabulario de verbos que
    ya usaba el frontend con los mocks (Abre/Añade/Reduce/Cierra, o
    Compra/Vende para spot)."""
    desde = int(time.time() * 1000) - VENTANA_MOVIMIENTOS_MS
    filas = conn.execute(
        "SELECT coin, lado, tamaño, tamaño_antes, precio, detectado FROM alertas "
        "WHERE addr=? AND tipo=? AND detectado>=? ORDER BY detectado DESC",
        (addr, tipo, desde),
    ).fetchall()
    movimientos = []
    for f in filas:
        if f["tamaño_antes"] is None:
            verbo = "Abre (inicio)" if tipo == "trading" else "Compra (inicio)"
        elif f["tamaño"] == 0:
            verbo = "Cierra" if tipo == "trading" else "Vende"
        elif f["tamaño"] > f["tamaño_antes"]:
            verbo = "Añade" if tipo == "trading" else "Compra"
        else:
            verbo = "Reduce" if tipo == "trading" else "Vende"
        movimientos.append({
            "coin": f["coin"],
            "lado": f["lado"],
            "fecha": _ms_a_iso(f["detectado"]),
            "verbo": verbo,
            "notionalUsd": (f["tamaño"] or 0) * (f["precio"] or 0),
            "precio": f["precio"],
        })
    return movimientos


def _ms_a_iso(ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ms / 1000))


def _candidato_dict(conn, f, todas: list[str], *, con_operaciones: bool, posicion_actual_vivo=None, holdings_spot_vivo=None) -> dict:
    """con_operaciones=False (listado masivo): sin operacionesRecientes --
    hasta 2000 fills x cada candidato hacia que /candidatos pesara
    20+ MB con 80 candidatos y se atascara en el navegador. Solo el detalle
    de UN trader (ver /candidatos/{address}) la necesita.

    posicion_actual_vivo/holdings_spot_vivo: cuando se pasan (detalle de UN
    trader), sustituyen a la version cacheada en BD (refrescada cada 5 min)
    por una instantanea pedida a Hyperliquid en este mismo instante -- igual
    que hacia la app vieja al abrir el modal, para que nunca se vea "sin
    confirmar" en una posicion que sigue abierta de verdad ahora mismo."""
    posicion_actual = posicion_actual_vivo if posicion_actual_vivo is not None else json.loads(f["posicion_actual"] or "[]")
    holdings_spot = holdings_spot_vivo if holdings_spot_vivo is not None else json.loads(f["holdings_spot"] or "[]")
    operaciones_recientes = json.loads(f["operaciones_recientes"] or "[]") if con_operaciones else []
    # los fills de spot traen el coin como "@idx" (indice interno de
    # Hyperliquid), no el ticker -- las posiciones/holdings en vivo ya vienen
    # traducidos (ver hyperliquid.py), solo los fills crudos necesitan esto
    for op in operaciones_recientes:
        op["coin"] = _nombre_moneda(op["coin"])
    # las tags de la tarjeta son las monedas que MAS opera en general (ver
    # hyperliquid.monedas_mas_usadas, calculado sobre el año completo del
    # backtest en descubrimiento/refresher), con las que tiene abiertas
    # ahora mismo primero -- no solo lo que tiene abierto en este instante,
    # que es como estaba antes y dejaba traders activos sin ninguna tag
    monedas_top = json.loads(f["monedas_top"] or "[]")
    if not monedas_top:
        # fallback para candidatos descubiertos antes de monedas_top (o aun
        # sin su primer ciclo de backtest): mejor esto que no mostrar nada
        monedas_top = sorted({p["coin"] for p in posicion_actual} | {h["coin"] for h in holdings_spot})
    return {
        "address": f["address"],
        "nombre": nombres.nombre_de(f["address"], todas),
        # 'especulativo' = apuesta curada a mano, nunca se juzga por
        # backtest (ver descubrimiento.py) -- por eso puede no tener
        # puntuacion y aun asi deber aparecer en Trading (y nunca borrarse
        # por no llegar al minimo)
        "esEspeculativo": f["categoria"] == "especulativo",
        "puntuacion": f["puntuacion"],
        "puntuacionSpot": f["puntuacion_spot"],
        "estilo": f["estilo"] or "activo",
        "riesgo": f["riesgo"] or "moderado",
        "antiguedadDias": f["antiguedad"],
        "drawdown": f["drawdown"],
        "cuenta": f["cuenta"],
        "winRate": f["win_rate"],
        "retornoPct": f["retorno_pct"],
        "profitFactor": f["profit_factor"],
        "drawdownSpot": f["drawdown_spot"],
        "winRateSpot": f["win_rate_spot"],
        "retornoPctSpot": f["retorno_pct_spot"],
        "profitFactorSpot": f["profit_factor_spot"],
        "monedas": [{"nombre": m, "categoria": _categoria_de(m)} for m in monedas_top],
        "desestimado": (
            {"motivo": f["desestimado_motivo"], "fecha": _ms_a_iso(f["desestimado_fecha"])}
            if f["desestimado_motivo"] else None
        ),
        "posicionActual": posicion_actual,
        "holdingsSpot": holdings_spot,
        "operacionesRecientes": operaciones_recientes,
        "movimientosTrading": _movimientos_de(conn, f["address"], "trading"),
        "movimientosSpot": _movimientos_de(conn, f["address"], "spot"),
    }


@router.get("")
def listar_candidatos(_uid: str = Depends(usuario_actual)):
    with db.conectar() as conn:
        filas = conn.execute("SELECT * FROM candidatos ORDER BY descubierto_ts DESC").fetchall()
        todas = [r["address"] for r in filas]
        return [_candidato_dict(conn, f, todas, con_operaciones=False) for f in filas]


@router.get("/consenso")
def consenso_actual(_uid: str = Depends(usuario_actual)):
    """Estado EN VIVO de consenso (no el 'ya avisado' de consenso_visto, que
    es solo para no repetir el aviso de Telegram por el mismo tamaño de
    grupo) -- 2+ traders con la misma coin+lado entrando o cerrando en las
    ultimas 72h. Solo dos verbos ('han entrado'/'han cerrado'), igual que la
    app vieja (calcularSeguimiento/gruposEntrando/gruposCerrando) -- un grupo
    reduciendo posiciones nunca se mostro como consenso en el frontend, solo
    alimentaba el aviso de Telegram (ver refresher.detectar_consenso)."""
    desde = int(time.time() * 1000) - VENTANA_MOVIMIENTOS_MS
    with db.conectar() as conn:
        todas = [r["address"] for r in conn.execute("SELECT address FROM candidatos")]
        # posicion_actual por trader (cacheada cada 5 min) para calcular el %
        # en vivo de los que siguen abiertos -- los que ya cerraron ("han
        # cerrado") no tienen dato en vivo que mostrar, se dejan sin %
        posicion_por_addr: dict[str, list[dict]] = {
            r["address"]: json.loads(r["posicion_actual"] or "[]")
            for r in conn.execute("SELECT address, posicion_actual FROM candidatos")
        }

        def pnl_pct_en_vivo(addr: str, coin: str, lado: str) -> float | None:
            for p in posicion_por_addr.get(addr, []):
                if p["coin"] == coin and p["lado"] == lado:
                    coste = p["valorPosicion"] - p["pnlNoRealizado"]
                    return round(p["pnlNoRealizado"] / coste * 100, 1) if coste else None
            return None

        grupos: dict[tuple, dict[str, dict]] = {}

        def agrupar(sql, verbo):
            for fila in conn.execute(sql, (desde,)):
                clave = (fila["coin"], fila["lado"], verbo)
                grupos.setdefault(clave, {})[fila["addr"]] = fila

        agrupar(
            "SELECT coin, lado, addr, tamaño, precio, detectado FROM alertas WHERE tipo='trading' AND tamaño>0 "
            "AND detectado>=? AND (tamaño_antes IS NULL OR tamaño>tamaño_antes)",
            "han entrado",
        )
        agrupar(
            "SELECT coin, lado, addr, tamaño_antes AS tamaño, precio, detectado FROM alertas WHERE tipo='trading' "
            "AND tamaño=0 AND detectado>=?",
            "han cerrado",
        )

        resultado = []
        for (coin, lado, verbo), por_addr in grupos.items():
            if len(por_addr) < 2:
                continue
            resultado.append({
                "coin": coin,
                "lado": lado,
                "verbo": verbo,
                "traders": [
                    {
                        "address": addr,
                        "nombre": nombres.nombre_de(addr, todas),
                        "fecha": _ms_a_iso(fila["detectado"]),
                        "invertidoUsd": (fila["tamaño"] or 0) * (fila["precio"] or 0),
                        "precio": fila["precio"],
                        "pnlPct": pnl_pct_en_vivo(addr, coin, lado) if verbo == "han entrado" else None,
                    }
                    for addr, fila in por_addr.items()
                ],
            })
        return resultado


@router.get("/{address}")
def detalle_candidato(address: str, _uid: str = Depends(usuario_actual)):
    """Detalle de UN trader con su historial completo de fills --
    agruparEpisodios/construirBloques en el frontend (ver
    shared/utils/episodios.ts) construye los bloques trading/spot del modal
    a partir de operacionesRecientes, que aqui SI se incluye. Registrada al
    final: "/{address}" capturaria "/consenso" como si fuera una direccion
    si se registrara antes."""
    with db.conectar() as conn:
        f = conn.execute("SELECT * FROM candidatos WHERE address=?", (address,)).fetchone()
        if f is None:
            raise HTTPException(status_code=404, detail="candidato no encontrado")
        todas = [r["address"] for r in conn.execute("SELECT address FROM candidatos")]
        try:
            idx_por_nombre = hyperliquid.cargar_idx_por_nombre()
            precios = hyperliquid.fetch_json({"type": "allMids"})
            posiciones, holdings = hyperliquid.posicion_y_holdings_de(address, idx_por_nombre, precios)
        except Exception:
            posiciones = holdings = None  # Hyperliquid no responde: cae al dato cacheado, mejor que romper el modal
        return _candidato_dict(conn, f, todas, con_operaciones=True, posicion_actual_vivo=posiciones, holdings_spot_vivo=holdings)
