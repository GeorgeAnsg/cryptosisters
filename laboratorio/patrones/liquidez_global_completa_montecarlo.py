"""
Continuacion de `liquidez_global_ciclos.py` (17-sept-2026), a peticion
explicita del usuario tras el primer resultado negativo: aquel proxy
era SOLO EEUU (Fed WALCL + M2SL + DXY). Aqui se construye el GLI
"de verdad" -- Fed + BCE + BOJ, cada uno convertido a USD con su tipo
de cambio -- para comprobar si el resultado cambia con los 3 bancos
centrales grandes que sí publican datos limpios y gratuitos.

Fuente de los datos nuevos: FRED, descargado en directo el 17-sept-2026
(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIE>`, sin login,
como ya se hacia con las series previas de `datos/crudo/`):
- ECBASSETSW: balance del BCE, millones de EUR, semanal.
- JPNASSETS: balance del BOJ, unidades de 100 millones de JPY, mensual.
- DEXUSEU, DEXJPUS: tipos de cambio USD/EUR y JPY/USD para convertir.

PBOC (China) se probo pero se descarta de este proxy: las series
candidatas en FRED (MYAGM2CNM189N, MANMM101CNM189S) se discontinuan en
2018-2019, y no se encontro ninguna serie de M2/balance china gratuita
con historia larga Y actualizada a 2026. El proxy se queda en Fed+BCE+BOJ
-- que de todas formas es la base de la mayoria de trackers de "liquidez
global" (China es la pieza mas opaca y discutida de cualquier GLI, publico
o de pago).

Dos pruebas, igual que en el fichero anterior:
1) Emparejamiento de techos/suelos de CICLO (mismo metodo, argrelextrema
   orden=180 dias, no causal a proposito -- exploracion historica).
2) NUEVO -- correlacion cruzada por desfase sobre la tasa de cambio
   interanual (365d) de cada serie (evita la correlacion espuria de dos
   series que simplemente comparten una tendencia de fondo), barriendo
   lags de -365 a +365 dias.

Resultado parte 1 (emparejamiento): SIGUE sin haber desfase estable con
el proxy completo -- diferencias de +32 a +1030 dias, ambas direcciones.

Resultado parte 2 (correlacion por desfase): aqui SI aparece algo vistoso
a primera vista -- mejor correlacion r=0.641 en torno a un desfase de
+200 dias (liquidez adelantada). Antes de aceptarlo, se aplico un test de
Monte Carlo (1000 repeticiones): se desplaza circularmente la serie de
liquidez un numero de dias aleatorio (misma forma/autocorrelacion interna,
pero relacion temporal real destruida) y se repite EXACTAMENTE el mismo
barrido de 147 desfases, guardando la mejor correlacion de cada repeticion
-- asi se mide cuanta "mejor correlacion de 147 intentos" produce el puro
azar entre dos series suaves sin relacion real (la misma logica que la
puerta 4/DSR del proyecto: corregir por el numero de intentos, no mirar
un unico p-valor ingenuo).

Resultado del Monte Carlo: mediana nula=0.355, percentil90=0.715,
percentil99=0.743 -- el r=0.641 observado cae en el percentil ~77 de la
distribucion nula (p~=0.234, nada significativo). Es decir: **incluso sin
ninguna relacion real, buscar el mejor desfase entre dos series
macro-suaves ya produce, la mayoria de las veces, una correlacion tan
buena o mejor que la que se ve en los datos reales.** Esto tiene una
explicacion doble: (a) ambas series son curvas suaves de bajo numero de
puntos independientes (aunque haya miles de dias, el numero de "giros"
reales en 8 años es muy bajo), y (b) solo existe UN episodio grande
compartido en todo el periodo (expansion 2020-2021 + contraccion 2022,
QE->QT), no varias confirmaciones independientes -- una sola coincidencia
grande basta para producir una correlacion vistosa en una grafica.

Veredicto: descartado tambien con el GLI completo (Fed+BCE+BOJ). La
impresion visual de la grafica del youtuber es coherente con el sesgo de
"elegir a posteriori el desfase que mejor encaja" sobre dos series
naturalmente suaves que ademas comparten un unico gran episodio macro --
no con una relacion sistematica y explotable. Ver `registro/intentos.jsonl`
(actualiza/completa `liquidez_global_ciclos_gli`).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

from datos.cargar import cargar_ohlcv

CORTE_RESERVA = pd.Timestamp("2025-01-01", tz="UTC")
ORDEN_DIAS = 180
LAGS = list(range(-365, 366, 5))
N_MONTECARLO = 1000
SEMILLA = 20260917


def cargar_fred(serie: str) -> pd.Series:
    df = pd.read_csv(f"datos/crudo/{serie}.csv")
    df["observation_date"] = pd.to_datetime(df["observation_date"], utc=True)
    df[serie] = pd.to_numeric(df[serie], errors="coerce")
    s = df.set_index("observation_date")[serie].sort_index()
    return s.resample("1D").last().ffill()


def zscore(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / s.std()


def picos_valles(serie: pd.Series, orden: int = ORDEN_DIAS):
    arr = serie.to_numpy()
    idx_max = [i for i in argrelextrema(arr, np.greater_equal, order=orden)[0] if 0 < i < len(arr) - 1]
    idx_min = [i for i in argrelextrema(arr, np.less_equal, order=orden)[0] if 0 < i < len(arr) - 1]
    return sorted(idx_max), sorted(idx_min)


def emparejar(fechas, btc_idxs, liq_idxs, etiqueta):
    print(f"\n-- {etiqueta} --")
    if not liq_idxs:
        print("  (sin puntos de liquidez para comparar)")
        return
    for bi in btc_idxs:
        cercano = min(liq_idxs, key=lambda li: abs(li - bi))
        dias = bi - cercano
        et = "liquidez primero" if dias > 0 else "BTC primero" if dias < 0 else "mismo dia"
        print(f"  BTC {fechas[bi].date()}  <->  liquidez {fechas[cercano].date()}  (diferencia {dias:+d} dias, {et})")


def mejor_correlacion_por_desfase(btc_yoy: np.ndarray, serie_yoy: np.ndarray, lags=LAGS):
    n = len(btc_yoy)
    mejor_lag, mejor_r = None, 0.0
    filas = []
    for lag in lags:
        if lag >= 0:
            a, b = (btc_yoy[lag:], serie_yoy[: n - lag]) if lag > 0 else (btc_yoy, serie_yoy)
        else:
            a, b = btc_yoy[: n + lag], serie_yoy[-lag:]
        if len(a) < 200:
            continue
        c = np.corrcoef(a, b)[0, 1]
        filas.append((lag, c))
        if abs(c) > abs(mejor_r):
            mejor_lag, mejor_r = lag, c
    return mejor_lag, mejor_r, filas


if __name__ == "__main__":
    btc = cargar_ohlcv("BTCUSDT", "1d").set_index("open_time")["close"]
    fed = cargar_fred("WALCL")             # millones USD
    ecb_eur = cargar_fred("ECBASSETSW")    # millones EUR
    boj_100m_jpy = cargar_fred("JPNASSETS")  # unidades de 100 millones de JPY
    eurusd = cargar_fred("DEXUSEU")
    jpyusd = cargar_fred("DEXJPUS")

    desde = max(s.index.min() for s in [btc, fed, ecb_eur, boj_100m_jpy, eurusd, jpyusd])
    hasta = min(min(s.index.max() for s in [btc, fed, ecb_eur, boj_100m_jpy, eurusd, jpyusd]), CORTE_RESERVA)
    print(f"Rango comun (2025+ excluido): {desde.date()} a {hasta.date()}")

    idx = pd.date_range(desde, hasta, freq="D", tz="UTC")
    r = lambda s: s.reindex(idx, method="ffill")
    btc, fed, ecb_eur, boj_100m_jpy, eurusd, jpyusd = r(btc), r(fed), r(ecb_eur), r(boj_100m_jpy), r(eurusd), r(jpyusd)

    fed_musd = fed
    ecb_musd = ecb_eur * eurusd
    boj_musd = (boj_100m_jpy * 1e8 / jpyusd) / 1e6
    gli = fed_musd + ecb_musd + boj_musd
    print(f"GLI-3 (Fed+BCE+BOJ) actual: {gli.iloc[-1] / 1000:.0f} mil M$ "
          f"(Fed {fed_musd.iloc[-1]/1000:.0f} + BCE {ecb_musd.iloc[-1]/1000:.0f} + BOJ {boj_musd.iloc[-1]/1000:.0f})")

    fechas = btc.index
    btc_suave = np.log(btc).rolling(30, min_periods=15).mean()
    btc_max, btc_min = picos_valles(btc_suave)
    gli_suave = zscore(gli).rolling(30, min_periods=15).mean().bfill()
    liq_max, liq_min = picos_valles(gli_suave)

    print(f"\nMaximos de ciclo BTC: {[fechas[i].date() for i in btc_max]}")
    print(f"Minimos de ciclo BTC: {[fechas[i].date() for i in btc_min]}")
    print(f"Maximos de ciclo GLI-3: {[fechas[i].date() for i in liq_max]}")
    print(f"Minimos de ciclo GLI-3: {[fechas[i].date() for i in liq_min]}")
    emparejar(fechas, btc_max, liq_max, "Techos: BTC vs GLI-3")
    emparejar(fechas, btc_min, liq_min, "Suelos: BTC vs GLI-3")

    print("\n" + "=" * 70)
    print("Correlacion cruzada por desfase, tasa interanual (365d)")
    print("=" * 70)
    btc_yoy = (btc.pct_change(365) * 100).to_numpy()
    gli_yoy = (gli.pct_change(365) * 100).to_numpy()
    valido = ~np.isnan(btc_yoy) & ~np.isnan(gli_yoy)
    btc_v, gli_v = btc_yoy[valido], gli_yoy[valido]

    mejor_lag, mejor_r, filas = mejor_correlacion_por_desfase(btc_v, gli_v)
    print(f"\nMejor correlacion real: lag={mejor_lag:+d} dias (positivo=liquidez adelantada), r={mejor_r:.3f}")
    for lag, corr in filas:
        if lag % 30 == 0:
            print(f"  lag {lag:+5d}d: r={corr:+.3f}" + ("  <-- mejor" if lag == mejor_lag else ""))

    print("\n" + "=" * 70)
    print(f"Monte Carlo ({N_MONTECARLO} repeticiones): ¿ese r es distinguible del azar")
    print("entre dos series suaves probando 147 desfases distintos?")
    print("=" * 70)
    rng = np.random.default_rng(SEMILLA)
    n = len(btc_v)
    mejores_mc = np.empty(N_MONTECARLO)
    for i in range(N_MONTECARLO):
        despl = rng.integers(200, n - 200)
        gli_shift = np.roll(gli_v, despl)
        _, r_mc, _ = mejor_correlacion_por_desfase(btc_v, gli_shift)
        mejores_mc[i] = abs(r_mc)

    p_valor = (mejores_mc >= abs(mejor_r)).mean()
    print(f"\nr observado: {mejor_r:.3f}")
    print(f"Nula -- mediana={np.median(mejores_mc):.3f}  p90={np.percentile(mejores_mc,90):.3f}  "
          f"p99={np.percentile(mejores_mc,99):.3f}  max={mejores_mc.max():.3f}")
    print(f"p-valor aproximado: {p_valor:.3f}  "
          f"({'NO significativo' if p_valor > 0.05 else 'significativo'})")
