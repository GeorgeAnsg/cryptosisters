"""
Busqueda de pesos SOLO en ETH (tramo de ajuste), congelar, y confirmar SIN
TOCAR NADA en dos sitios nunca vistos durante la busqueda: (a) el tramo de
tiempo posterior de ETH, (b) BTC completo. Metodologia exigida por la
skill `deteccion-flexible-patrones`, paso 7 ("dos cortes": moneda y
tiempo) -- nunca ejecutada correctamente hasta ahora porque BTC se venia
mirando en paralelo durante todo el ajuste (ver
feedback_validacion_cruzada_solo_eth en la memoria persistente).

Tambien corrige un defecto de `validacion_confirmacion.py`: ahi el retorno
se media desde el dia del PATRON (idx_fondo2/idx_techo2), no desde el dia
real en que se confirma la ruptura -- un trader que espera la confirmacion
entra mas tarde y captura menos retorno del que se estaba reportando. Aqui
se mide desde el dia de confirmacion real.

Solo se busca sobre los PESOS ya conocidos (los 5 de
doble_suelo_consenso.py / doble_techo_consenso.py) -- no se amplia el
grid de tolerancias, para no gastar presupuesto de intentos de mas.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import caida_recuperacion, canal_flexible, doble_suelo_flexible, doble_techo_flexible
from laboratorio.patrones.doble_suelo_consenso import PESOS_FORMA as PESOS_SUELO
from laboratorio.patrones.doble_techo_consenso import PESOS_FORMA as PESOS_TECHO
from laboratorio.patrones.caida_recuperacion import PESOS_FORMA as PESOS_CAIDA
from laboratorio.patrones.canal_flexible import PESOS_FORMA as PESOS_CANAL

CORTE = pd.Timestamp("2021-01-01", tz="UTC")
CORTE_AJUSTE_FIN = pd.Timestamp("2023-01-01", tz="UTC")   # ajuste: [CORTE, CORTE_AJUSTE_FIN)
CORTE_DESARROLLO_FIN = pd.Timestamp("2025-01-01", tz="UTC")  # confirmacion de tiempo: [CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN)
DIAS_CONFIRMACION = 10
DIAS_EXITO = 15
# Variante para canal (11-sept-2026): un canal dura 10-60 dias (vs 8-20 en
# doble suelo), copiar DIAS_CONFIRMACION=10 tal cual de doble suelo/techo
# penaliza a los canales largos con una ventana de confirmacion demasiado
# corta relativa a su propia duracion. Rango, no un solo valor fijo -- se
# prueban varias fracciones de dias_total como ventana de confirmacion.
FRACCIONES_CONFIRMACION_CANAL = [0.15, 0.25, 0.35, 0.5]
UMBRALES_EXITO_PCT = [2.0, 3.0, 5.0, 7.0, 10.0]  # rango, no un numero fijo elegido a mano


def _entradas_confirmadas_suelo(df: pd.DataFrame, pesos: tuple) -> list[tuple[int, int | None]]:
    peso_nivel, peso_rebote, peso_tiempo, peso_altura = pesos
    candidatos = doble_suelo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_rebote=peso_rebote, peso_tiempo=peso_tiempo,
        peso_altura=peso_altura,
    )
    n = len(df)
    filas = []
    for c in candidatos:
        maximo_intermedio = df["close"].iloc[c.idx_fondo1: c.idx_fondo2 + 1].max()
        fin_conf = min(c.idx_fondo2 + 1 + DIAS_CONFIRMACION, n)
        tramo_conf = df["close"].iloc[c.idx_fondo2 + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf > maximo_intermedio]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None
        filas.append((c.idx_fondo2, idx_confirmacion))
    return filas


def _entradas_confirmadas_techo(df: pd.DataFrame, pesos: tuple) -> list[tuple[int, int | None]]:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo,
        peso_altura=peso_altura,
    )
    n = len(df)
    filas = []
    for c in candidatos:
        minimo_intermedio = df["close"].iloc[c.idx_techo1: c.idx_techo2 + 1].min()
        fin_conf = min(c.idx_techo2 + 1 + DIAS_CONFIRMACION, n)
        tramo_conf = df["close"].iloc[c.idx_techo2 + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf < minimo_intermedio]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None
        filas.append((c.idx_techo2, idx_confirmacion))
    return filas


def _entradas_confirmadas_caida(df: pd.DataFrame, pesos: tuple) -> list[tuple[int, int | None]]:
    """Etapa 2 para caida_recuperacion.py: confirmacion = el precio vuelve
    a superar el precio_pico (el nivel de ANTES de la caida, equivalente
    al 'neckline' de doble suelo) dentro de DIAS_CONFIRMACION dias tras el
    fondo -- una recuperacion COMPLETA confirmada.

    15-sept-2026: `peso_recuperacion`/`peso_redondeo` se retiraron de
    `caida_recuperacion.detectar()` (Capa 1 no era causal -- ver
    observacion 0021 del log de task-observer y el docstring del modulo).
    Esta funcion ahora pasa solo los 5 pesos causales."""
    (peso_caida, peso_velocidad, peso_mecha, peso_desaceleracion, peso_arranque) = pesos
    candidatos = caida_recuperacion.detectar(
        df, peso_caida=peso_caida, peso_velocidad=peso_velocidad,
        peso_mecha=peso_mecha, peso_desaceleracion=peso_desaceleracion,
        peso_arranque=peso_arranque,
    )
    n = len(df)
    filas = []
    for c in candidatos:
        fin_conf = min(c.idx_fondo + 1 + DIAS_CONFIRMACION, n)
        tramo_conf = df["close"].iloc[c.idx_fondo + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf > c.precio_pico]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None
        filas.append((c.idx_fondo, idx_confirmacion))
    return filas


def _entradas_confirmadas_canal(
    df: pd.DataFrame, pesos: tuple, direccion: str, fraccion_confirmacion: float | None = None,
) -> list[tuple[int, int | None]]:
    """Etapa 2 para canal_flexible.py: un canal no es un patron de reversion
    con neckline horizontal, es una estructura diagonal -- la 'ruptura' es
    que el precio cruce la PROYECCION hacia adelante de la linea (misma
    pendiente que ya tenia), no un nivel fijo. Ascendente: confirma si el
    precio supera la proyeccion de la resistencia (continuacion alcista).
    Descendente: confirma si el precio cae por debajo de la proyeccion del
    soporte (continuacion bajista)."""
    (peso_pendiente, peso_paralelismo, peso_ancho, peso_consistencia, peso_contencion) = pesos
    fn = canal_flexible.detectar_ascendente if direccion == "subida" else canal_flexible.detectar_descendente
    candidatos = fn(
        df, peso_pendiente=peso_pendiente, peso_paralelismo=peso_paralelismo, peso_ancho=peso_ancho,
        peso_consistencia=peso_consistencia, peso_contencion=peso_contencion,
    )
    close = df["close"].to_numpy()
    n = len(df)
    filas = []
    for c in candidatos:
        dias_confirmacion = (
            max(DIAS_CONFIRMACION, round(fraccion_confirmacion * c.dias_total))
            if fraccion_confirmacion is not None else DIAS_CONFIRMACION
        )
        fin_conf = min(c.idx_pico2 + 1 + int(dias_confirmacion), n)
        idx_confirmacion = None
        if direccion == "subida":
            slope_abs = (c.precio_pico2 - c.precio_pico1) / (c.idx_pico2 - c.idx_pico1)
            for x in range(c.idx_pico2 + 1, fin_conf):
                proyeccion = c.precio_pico2 + slope_abs * (x - c.idx_pico2)
                if close[x] > proyeccion:
                    idx_confirmacion = x
                    break
        else:
            slope_abs = (c.precio_fondo2 - c.precio_fondo1) / (c.idx_fondo2 - c.idx_fondo1)
            for x in range(c.idx_pico2 + 1, fin_conf):
                proyeccion = c.precio_fondo2 + slope_abs * (x - c.idx_fondo2)
                if close[x] < proyeccion:
                    idx_confirmacion = x
                    break
        filas.append((c.idx_pico2, idx_confirmacion))
    return filas


def _resumen(df: pd.DataFrame, filas: list, desde: pd.Timestamp, hasta: pd.Timestamp, exito_es_subida: bool) -> dict:
    n = len(df)
    fechas = df["open_time"]
    con, sin = [], []
    for idx2, idx_conf in filas:
        fecha2 = fechas.iloc[idx2]
        if fecha2 < desde or fecha2 >= hasta:
            continue
        if idx_conf is not None:
            fin_exito = idx_conf + DIAS_EXITO
            if fin_exito >= n:
                continue
            precio0 = df["close"].iloc[idx_conf]
            retorno = (df["close"].iloc[fin_exito] - precio0) / precio0 * 100
            con.append(retorno)
        else:
            fin_exito = idx2 + DIAS_EXITO
            if fin_exito >= n:
                continue
            precio0 = df["close"].iloc[idx2]
            retorno = (df["close"].iloc[fin_exito] - precio0) / precio0 * 100
            sin.append(retorno)

    def stats(retornos):
        if not retornos:
            return {"n": 0, "acierto_pct_medio": None, "acierto_pct_rango": None, "retorno_medio_pct": None}
        arr = np.array(retornos)
        aciertos_por_umbral = []
        for umbral in UMBRALES_EXITO_PCT:
            acierto = (arr >= umbral) if exito_es_subida else (arr <= -umbral)
            aciertos_por_umbral.append(float(acierto.mean() * 100))
        return {
            "n": len(arr),
            "acierto_pct_medio": round(float(np.mean(aciertos_por_umbral)), 1),
            "acierto_pct_rango": [round(min(aciertos_por_umbral), 1), round(max(aciertos_por_umbral), 1)],
            "retorno_medio_pct": round(float(arr.mean()), 2),
        }

    return {"con_confirmacion": stats(con), "sin_confirmacion": stats(sin)}


def _mejor(resultados: list[dict]) -> dict:
    con_datos = [r for r in resultados if r["ajuste"]["con_confirmacion"]["n"] >= 5]
    universo = con_datos if con_datos else resultados
    return max(universo, key=lambda r: (
        r["ajuste"]["con_confirmacion"]["acierto_pct_medio"] or -1,
        r["ajuste"]["con_confirmacion"]["retorno_medio_pct"] or -999,
    ))


if __name__ == "__main__":
    import json

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="busqueda_pesos_solo_eth")

    print(f"ETH -- ajuste: {CORTE.date()} -> {CORTE_AJUSTE_FIN.date()} (unico tramo usado para elegir pesos)\n")

    print("=== Busqueda de pesos, DOBLE SUELO (solo ajuste, solo ETH) ===")
    resultados_suelo = []
    for pesos in PESOS_SUELO:
        filas = _entradas_confirmadas_suelo(df_eth, pesos)
        r_ajuste = _resumen(df_eth, filas, CORTE, CORTE_AJUSTE_FIN, exito_es_subida=True)
        resultados_suelo.append({"pesos": pesos, "ajuste": r_ajuste})
        print(json.dumps({"pesos": pesos, "ajuste": r_ajuste}, default=str))
    mejor_suelo = _mejor(resultados_suelo)
    print("-> MEJOR combo suelo (congelado):", mejor_suelo["pesos"], mejor_suelo["ajuste"])

    print("\n=== Busqueda de pesos, DOBLE TECHO (solo ajuste, solo ETH) ===")
    resultados_techo = []
    for pesos in PESOS_TECHO:
        filas = _entradas_confirmadas_techo(df_eth, pesos)
        r_ajuste = _resumen(df_eth, filas, CORTE, CORTE_AJUSTE_FIN, exito_es_subida=False)
        resultados_techo.append({"pesos": pesos, "ajuste": r_ajuste})
        print(json.dumps({"pesos": pesos, "ajuste": r_ajuste}, default=str))
    mejor_techo = _mejor(resultados_techo)
    print("-> MEJOR combo techo (congelado):", mejor_techo["pesos"], mejor_techo["ajuste"])

    # --- Confirmacion 1: tramo de tiempo NUNCA visto durante la busqueda, mismo ETH ---
    filas_suelo_frozen = _entradas_confirmadas_suelo(df_eth, mejor_suelo["pesos"])
    conf_tiempo_suelo = _resumen(df_eth, filas_suelo_frozen, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, True)
    filas_techo_frozen = _entradas_confirmadas_techo(df_eth, mejor_techo["pesos"])
    conf_tiempo_techo = _resumen(df_eth, filas_techo_frozen, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, False)

    print(f"\n=== CONFIRMACION 1: ETH, tramo {CORTE_AJUSTE_FIN.date()}->{CORTE_DESARROLLO_FIN.date()} (nunca visto en la busqueda) ===")
    print("Suelo:", json.dumps(conf_tiempo_suelo, default=str))
    print("Techo:", json.dumps(conf_tiempo_techo, default=str))

    # --- Confirmacion 2: BTC completo, pesos ya congelados (moneda nunca vista en la busqueda) ---
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="confirmacion_btc_pesos_congelados")
    filas_suelo_btc = _entradas_confirmadas_suelo(df_btc, mejor_suelo["pesos"])
    conf_btc_suelo = _resumen(df_btc, filas_suelo_btc, CORTE, CORTE_DESARROLLO_FIN, True)
    filas_techo_btc = _entradas_confirmadas_techo(df_btc, mejor_techo["pesos"])
    conf_btc_techo = _resumen(df_btc, filas_techo_btc, CORTE, CORTE_DESARROLLO_FIN, False)

    print("\n=== CONFIRMACION 2: BTC completo, pesos congelados (moneda nunca vista en la busqueda) ===")
    print("Suelo:", json.dumps(conf_btc_suelo, default=str))
    print("Techo:", json.dumps(conf_btc_techo, default=str))

    # --- Patron nuevo: CAIDA BRUSCA Y RECUPERACION (11-sept-2026) ---
    print("\n=== Busqueda de pesos, CAIDA BRUSCA Y RECUPERACION (solo ajuste, solo ETH) ===")
    resultados_caida = []
    for pesos in PESOS_CAIDA:
        filas = _entradas_confirmadas_caida(df_eth, pesos)
        r_ajuste = _resumen(df_eth, filas, CORTE, CORTE_AJUSTE_FIN, exito_es_subida=True)
        resultados_caida.append({"pesos": pesos, "ajuste": r_ajuste})
        print(json.dumps({"pesos": pesos, "ajuste": r_ajuste}, default=str))
    mejor_caida = _mejor(resultados_caida)
    print("-> MEJOR combo caida (congelado):", mejor_caida["pesos"], mejor_caida["ajuste"])

    filas_caida_frozen = _entradas_confirmadas_caida(df_eth, mejor_caida["pesos"])
    conf_tiempo_caida = _resumen(df_eth, filas_caida_frozen, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, True)
    print(f"\n=== CONFIRMACION 1 (caida): ETH, tramo {CORTE_AJUSTE_FIN.date()}->{CORTE_DESARROLLO_FIN.date()} (nunca visto) ===")
    print(json.dumps(conf_tiempo_caida, default=str))

    filas_caida_btc = _entradas_confirmadas_caida(df_btc, mejor_caida["pesos"])
    conf_btc_caida = _resumen(df_btc, filas_caida_btc, CORTE, CORTE_DESARROLLO_FIN, True)
    print("\n=== CONFIRMACION 2 (caida): BTC completo, pesos congelados (moneda nunca vista) ===")
    print(json.dumps(conf_btc_caida, default=str))

    # --- Patron nuevo: CANAL (Fase B, 11-sept-2026) ---
    # Grid combinado: pesos Y fraccion de ventana de confirmacion (relativa a
    # la duracion propia del canal) -- las dos dimensiones se buscan SOLO en
    # ETH-ajuste, nunca por separado, para no dejar una fija a mano.
    print("\n=== Busqueda de pesos + ventana de confirmacion, CANAL ASCENDENTE (solo ajuste, solo ETH) ===")
    resultados_canal_asc = []
    for pesos in PESOS_CANAL:
        for fraccion in FRACCIONES_CONFIRMACION_CANAL:
            filas = _entradas_confirmadas_canal(df_eth, pesos, "subida", fraccion_confirmacion=fraccion)
            r_ajuste = _resumen(df_eth, filas, CORTE, CORTE_AJUSTE_FIN, exito_es_subida=True)
            resultados_canal_asc.append({"pesos": pesos, "fraccion": fraccion, "ajuste": r_ajuste})
    for r in sorted(resultados_canal_asc, key=lambda r: -(r["ajuste"]["con_confirmacion"]["retorno_medio_pct"] or -999))[:5]:
        print(json.dumps(r, default=str))
    mejor_canal_asc = _mejor(resultados_canal_asc)
    print("-> MEJOR combo canal ascendente (congelado):", mejor_canal_asc["pesos"], mejor_canal_asc["fraccion"], mejor_canal_asc["ajuste"])

    print("\n=== Busqueda de pesos + ventana de confirmacion, CANAL DESCENDENTE (solo ajuste, solo ETH) ===")
    resultados_canal_desc = []
    for pesos in PESOS_CANAL:
        for fraccion in FRACCIONES_CONFIRMACION_CANAL:
            filas = _entradas_confirmadas_canal(df_eth, pesos, "bajada", fraccion_confirmacion=fraccion)
            r_ajuste = _resumen(df_eth, filas, CORTE, CORTE_AJUSTE_FIN, exito_es_subida=False)
            resultados_canal_desc.append({"pesos": pesos, "fraccion": fraccion, "ajuste": r_ajuste})
    for r in sorted(resultados_canal_desc, key=lambda r: -(r["ajuste"]["con_confirmacion"]["retorno_medio_pct"] or -999))[:5]:
        print(json.dumps(r, default=str))
    mejor_canal_desc = _mejor(resultados_canal_desc)
    print("-> MEJOR combo canal descendente (congelado):", mejor_canal_desc["pesos"], mejor_canal_desc["fraccion"], mejor_canal_desc["ajuste"])

    filas_canal_asc_frozen = _entradas_confirmadas_canal(df_eth, mejor_canal_asc["pesos"], "subida", mejor_canal_asc["fraccion"])
    conf_tiempo_canal_asc = _resumen(df_eth, filas_canal_asc_frozen, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, True)
    filas_canal_desc_frozen = _entradas_confirmadas_canal(df_eth, mejor_canal_desc["pesos"], "bajada", mejor_canal_desc["fraccion"])
    conf_tiempo_canal_desc = _resumen(df_eth, filas_canal_desc_frozen, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, False)
    print(f"\n=== CONFIRMACION 1 (canal): ETH, tramo {CORTE_AJUSTE_FIN.date()}->{CORTE_DESARROLLO_FIN.date()} (nunca visto) ===")
    print("Ascendente:", json.dumps(conf_tiempo_canal_asc, default=str))
    print("Descendente:", json.dumps(conf_tiempo_canal_desc, default=str))

    filas_canal_asc_btc = _entradas_confirmadas_canal(df_btc, mejor_canal_asc["pesos"], "subida", mejor_canal_asc["fraccion"])
    conf_btc_canal_asc = _resumen(df_btc, filas_canal_asc_btc, CORTE, CORTE_DESARROLLO_FIN, True)
    filas_canal_desc_btc = _entradas_confirmadas_canal(df_btc, mejor_canal_desc["pesos"], "bajada", mejor_canal_desc["fraccion"])
    conf_btc_canal_desc = _resumen(df_btc, filas_canal_desc_btc, CORTE, CORTE_DESARROLLO_FIN, False)
    print("\n=== CONFIRMACION 2 (canal): BTC completo, pesos congelados (moneda nunca vista) ===")
    print("Ascendente:", json.dumps(conf_btc_canal_asc, default=str))
    print("Descendente:", json.dumps(conf_btc_canal_desc, default=str))
