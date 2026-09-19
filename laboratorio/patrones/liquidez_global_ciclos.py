"""
Idea del usuario (17-sept-2026): "Global Liquidity Index" (GLI) -- un
youtuber de cripto superpone la grafica de liquidez global, retrasada
unos dias/semanas, sobre el precio de BTC y hace coincidir maximos y
minimos de ciclo aproximadamente. Hipotesis: la liquidez global "lidera"
los grandes techos/suelos de BTC por un desfase mas o menos estable.

Esto es DISTINTO del intento anterior `factor_macro_tipos_liquidez_techo.py`
(12-sept, descartado como `techo_macro_tipos_liquidez` en
`registro/intentos.jsonl`): aquel probaba las mismas series macro como
FILTRO DE CONTEXTO sobre cada candidato individual de doble techo (¿el
patron es mas fiable si la Fed esta contrayendo balance ESE dia?). Este
prueba la version que describe el youtuber: emparejar los GRANDES techos
y suelos de CICLO de BTC (no cada patron individual) contra los grandes
techos y suelos de un proxy de liquidez, y medir si el desfase es estable.

Dato importante y limitacion honesta: NO tenemos un "Global Liquidity
Index" real descargado (el de trackers como Michael Howell/CrossBorder
Capital es propietario, no gratuito) -- se construye un PROXY con lo que
ya habia descargado de FRED en `datos/crudo/`: balance de la Fed (WALCL,
semanal), M2 de EEUU (M2SL, mensual) y el indice del dolar (DTWEXBGS,
diario, invertido: dolar debil = mas liquidez). Esto es SOLO EEUU -- no
incluye BCE/BOJ/PBOC, que un GLI de verdad si pesa. El resultado de abajo
no descarta que un GLI completo (con los 4 bancos centrales) se comporte
distinto, pero sí descarta que el proxy mas accesible/barato lo haga.

Metodo: suavizado 30 dias de cada serie (quita ruido de publicacion),
deteccion de maximos/minimos LOCALES con ventana de 180 dias (solo
"puntos de ciclo" grandes, no vaivenes cortos) via
`scipy.signal.argrelextrema`, no causal a proposito (esto es exploracion
de correlacion historica, no una señal en vivo) -- se emparaja cada techo
de BTC con el techo de liquidez mas cercano en el tiempo y se mide la
diferencia en dias. 2025-2026 excluido (reserva de validacion ciega del
proyecto).

Resultado (17-sept-2026): NINGUN desfase estable. Los emparejamientos de
techos/suelos dan diferencias de +3 a +1822 dias, en ambas direcciones
(a veces "lidera" la liquidez, a veces BTC), sin ningun patron reconocible
-- ni con el proxy combinado ni probando WALCL, M2SL o DXY cada uno por
separado. Los pocos emparejamientos que caen cerca (ej. techo/suelo de
marzo-abril 2020, ambos causados por el mismo shock de COVID) se explican
mejor por una causa comun (el propio crash) que por que la liquidez
"lidere" al precio.

Limitacion estructural, no solo de este proxy: en el historico disponible
solo hay 4-5 techos/suelos de ciclo de BTC. Ninguna prueba de desfase
puede ser estadisticamente solida con una muestra tan pequeña, sea cual
sea el proxy de liquidez usado -- esto es una limitacion del propio
fenomeno (los ciclos de BTC son eventos raros), no un fallo de la
implementacion.

Coherente con el hallazgo anterior (`techo_macro_tipos_liquidez`,
12-sept): dos formulaciones distintas de la misma familia de datos
macro (Fed/M2/tipos/dolar) fallan en dar una señal sistematica util.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

from datos.cargar import cargar_ohlcv

CORTE_RESERVA = pd.Timestamp("2025-01-01", tz="UTC")
ORDEN_DIAS = 180  # ventana para considerar un maximo/minimo "de ciclo", no un vaiven corto


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
        dias = bi - cercano  # positivo = liquidez llega antes que BTC (como afirma la hipotesis)
        etiqueta_dias = "liquidez primero" if dias > 0 else "BTC primero" if dias < 0 else "mismo dia"
        print(f"  BTC {fechas[bi].date()}  <->  liquidez {fechas[cercano].date()}  "
              f"(diferencia {dias:+d} dias, {etiqueta_dias})")


if __name__ == "__main__":
    btc = cargar_ohlcv("BTCUSDT", "1d").set_index("open_time")["close"]
    walcl = cargar_fred("WALCL")
    m2sl = cargar_fred("M2SL")
    dxy = cargar_fred("DTWEXBGS")

    desde = max(btc.index.min(), walcl.index.min(), m2sl.index.min(), dxy.index.min())
    hasta = min(btc.index.max(), walcl.index.max(), m2sl.index.max(), dxy.index.max(), CORTE_RESERVA)
    print(f"Rango usado (2025+ excluido, reserva de validacion ciega): {desde.date()} a {hasta.date()}")

    btc = btc[(btc.index >= desde) & (btc.index <= hasta)]
    walcl = walcl.reindex(btc.index, method="ffill")
    m2sl = m2sl.reindex(btc.index, method="ffill")
    dxy = dxy.reindex(btc.index, method="ffill")
    fechas = btc.index

    proxy = zscore(walcl) + zscore(m2sl) - zscore(dxy)
    proxy_suave = proxy.rolling(30, min_periods=15).mean().bfill()
    btc_suave = np.log(btc).rolling(30, min_periods=15).mean()

    btc_max, btc_min = picos_valles(btc_suave)
    liq_max, liq_min = picos_valles(proxy_suave)

    print(f"\nMaximos de ciclo BTC: {[fechas[i].date() for i in btc_max]}")
    print(f"Minimos de ciclo BTC: {[fechas[i].date() for i in btc_min]}")
    print(f"\nMaximos de ciclo en proxy de liquidez (Fed+M2-dolar): {[fechas[i].date() for i in liq_max]}")
    print(f"Minimos de ciclo en proxy de liquidez: {[fechas[i].date() for i in liq_min]}")

    emparejar(fechas, btc_max, liq_max, "Techos: BTC vs techos de liquidez (proxy combinado)")
    emparejar(fechas, btc_min, liq_min, "Suelos: BTC vs suelos de liquidez (proxy combinado)")

    print("\n" + "=" * 70)
    print("Comprobacion por separado -- ¿alguna serie sola es mas consistente que la mezcla?")
    print("=" * 70)
    componentes = {
        "WALCL solo (balance Fed)": walcl,
        "M2SL solo (M2 EEUU)": m2sl,
        "DXY invertido solo (dolar debil = liquidez)": -dxy,
    }
    for nombre, serie in componentes.items():
        suave = zscore(serie).rolling(30, min_periods=15).mean().bfill()
        c_max, c_min = picos_valles(suave)
        print(f"\n-- {nombre} --")
        emparejar(fechas, btc_max, c_max, "Techos")
        emparejar(fechas, btc_min, c_min, "Suelos")
