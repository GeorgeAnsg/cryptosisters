"""
Corrección del usuario (15-sept-2026) a la prueba anterior de `cartera/`:
NO se pueden tener 5 posiciones simultáneas en el MISMO activo -- lo
realista es 1 posición por activo, como ya funciona (BTC y ETH cada uno
con su propio hueco). El problema real que señaló es otro: dentro de UN
solo activo, con 1 solo hueco, un short mediocre ya abierto bloquea un
long mucho mejor que aparece después (caso real: rally ETH 04-feb a
11-mar-2024, 4 longs con probabilidad 0.79-0.96 descartados por tener un
corto abierto -- ver cartera/README.md, prueba anterior).

Idea a probar: en vez de descartar el candidato nuevo sin más, permitir
CAMBIAR de posición -- cerrar la abierta HOY (a precio de cierre de hoy,
sin mirar al futuro) y abrir la nueva -- pero SOLO si el candidato nuevo
es dirección contraria Y su probabilidad supera a la de la posición
abierta por un margen suficiente (`UMBRAL_SWITCH`, barrido, no un número
fijo a ojo -- regla de "no absolutos"). Sin esto, cualquier vaivén normal
de probabilidad estaría cambiando de posición constantemente.

100% causal: la decisión de cambiar se toma con la probabilidad YA
conocida de ambos candidatos en el momento de la comparación (la de la
posición abierta, fijada en su entrada; la del nuevo, calculada con
`calcular_en_vivo` ese mismo día) -- nunca se usa el resultado futuro real
de ninguna de las dos operaciones para decidir.

Métrica: cuenta secuencial completa de 2024 (no el exceso aislado por
candidato -- el valor de esta idea es de secuenciación, no se puede medir
candidato a candidato). Config de salidas/ + tamano/ + racha rota ya
aceptadas. Validación cruzada de siempre: barrido en ETH, confirmación en
BTC sin retocar el umbral ganador.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, R_FIJO, RIESGO_BASE_PCT, candidatos_2024, señales_racha,
)
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH_GRID = [0.0, 0.005, 0.01, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]


def _simular_con_switch(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, umbral_switch):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None  # dict: idx_entrada, direccion, prob, t (TradeSalida natural), unidades
    cambios = 0

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
        if t is None:
            return None
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob, "t": t, "unidades": pos.unidades}

    def _cerrar(pos, idx_cierre, precio_cierre, motivo):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_cierre - pos["t"].precio_entrada) * signo
        capital += pnl
        curva.append((fechas.iloc[idx_cierre], capital))
        trades.append({
            "entrada": str(fechas.iloc[pos["idx_entrada"]].date()), "salida": str(fechas.iloc[idx_cierre].date()),
            "direccion": pos["direccion"], "probabilidad": round(pos["probabilidad"], 3),
            "motivo": motivo, "pnl_eur": round(pnl, 2), "capital_tras": round(capital, 2),
        })

    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue

        if abierta is not None and idx > abierta["t"].idx_salida:
            _cerrar(abierta, abierta["t"].idx_salida, abierta["t"].precio_salida, abierta["t"].motivo)
            abierta = None

        if abierta is None:
            nueva = _abrir(idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
            continue

        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= umbral_switch:
            _cerrar(abierta, idx, close[idx], "cambio_candidato_fuerte")
            cambios += 1
            nueva = _abrir(idx, direccion, prob)
            abierta = nueva
        # si no hay switch, se descarta el candidato -- sin hueco (comportamiento actual)

    if abierta is not None:
        _cerrar(abierta, abierta["t"].idx_salida, abierta["t"].precio_salida, abierta["t"].motivo)

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    return capital, trades, drawdown_max_pct, cambios


def _resumen(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, umbral_switch):
    capital, trades, dd, cambios = _simular_con_switch(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, umbral_switch)
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return {"umbral_switch": umbral_switch, "capital_final": round(capital, 2),
            "retorno_pct": round((capital / CAPITAL_INICIAL - 1) * 100, 1),
            "n_trades": len(trades), "ganadoras": ganadoras, "cambios": cambios,
            "drawdown_max_pct": round(dd, 2)}


def main():
    resultados_por_moneda = {}
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_cambio_candidato_fuerte")
        atr = atr_absoluto(df)
        cand = candidatos_2024(df)
        racha_rota_techo, racha_rota_suelo = señales_racha(df)
        resultados_por_moneda[moneda] = (df, cand, atr, racha_rota_techo, racha_rota_suelo)

    df_eth, cand_eth, atr_eth, rt_eth, rs_eth = resultados_por_moneda["ETHUSDT"]
    print("=== ETH (ajuste) ===")
    base = _resumen(df_eth, cand_eth, atr_eth, rt_eth, rs_eth, umbral_switch=999)  # inalcanzable = nunca cambia (baseline)
    print(f"SIN switch (base, umbral=1.0 inalcanzable): {base}")

    resultados = [_resumen(df_eth, cand_eth, atr_eth, rt_eth, rs_eth, u) for u in UMBRAL_SWITCH_GRID]
    for r in resultados:
        print(" ", r)

    mejor = max(resultados, key=lambda r: r["capital_final"])
    en_borde = mejor["umbral_switch"] in (min(UMBRAL_SWITCH_GRID), max(UMBRAL_SWITCH_GRID))
    print(f"mejor umbral en ETH: {mejor} -- {'EN EL BORDE' if en_borde else 'dentro del rango'}")

    df_btc, cand_btc, atr_btc, rt_btc, rs_btc = resultados_por_moneda["BTCUSDT"]
    print("\n=== BTC (confirmación, sin tocar el umbral ganador) ===")
    base_btc = _resumen(df_btc, cand_btc, atr_btc, rt_btc, rs_btc, umbral_switch=999)
    ganador_btc = _resumen(df_btc, cand_btc, atr_btc, rt_btc, rs_btc, mejor["umbral_switch"])
    print(f"SIN switch (base) en BTC: {base_btc}")
    print(f"umbral={mejor['umbral_switch']} (ganador de ETH) en BTC: {ganador_btc}")


if __name__ == "__main__":
    main()
