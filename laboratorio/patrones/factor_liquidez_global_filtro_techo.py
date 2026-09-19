"""
Idea del usuario (17-sept-2026), tras cerrar la investigacion del "Global
Liquidity Index" como señal de precio directa: aunque la liquidez global no
sirva para predecir el precio de BTC por si sola (5 pruebas distintas, todas
negativas -- ver `liquidez_global_m2_bgeometrics.py` y
`liquidez_global_completa_montecarlo.py`), ¿podria seguir siendo util como
FILTRO DE CONTEXTO para confirmar candidatos de doble techo/doble suelo YA
detectados? Esta pregunta es legitima -- una señal debil o inestable como
predictor directo puede seguir siendo un buen filtro condicional (es
exactamente la logica de los filtros de contexto que ya funcionan en el
proyecto, ej. canal por calidad absoluta).

Distinto del intento anterior con el mismo espiritu (12-sept-2026,
`factor_macro_tipos_liquidez_techo.py`, descartado): aquel probaba DGS10,
DGS30, WALCL, M2SL, CPIAUCSL, PPIACO, PAYEMS, DTWEXBGS, VIXCLS, USDT_SUPPLY
por separado -- entre ellas WALCL y M2SL, pero NUNCA el M2 GLOBAL real (21
bancos centrales) ni el proxy combinado Fed+BCE+BOJ que se construyeron
despues, el 17-sept. Este fichero repite EXACTAMENTE el mismo metodo
(`_analizar`/`_candidatos_completos` de `factor_macro_tipos_liquidez_techo.py`,
reutilizados tal cual, sin modificar) sobre esas dos series nuevas.

Metodo (identico al de 12-sept, solo cambian las series de entrada):
ROC (% cambio) de la serie macro en K dias antes del techo2 de cada
candidato de doble techo, correlacionado (Spearman) con el retorno real a
`DIAS_EXITO` dias -- ajuste en ETH (dos tramos: 2017-2021 y 2021-2023),
confirmacion sin tocar nada en BTC (2021-2025) y en ETH-tiempo (2023-2025,
nunca visto durante el ajuste). K en [20, 40, 60] dias. Se prueba tanto
sobre TODOS los candidatos como solo sobre el subgrupo ya validado
(regimen bajista + nivel repetido).

Series probadas:
- GLI-3 propio (Fed+BCE+BOJ, historia completa 2017-2026, mismo proxy que
  `liquidez_global_completa_montecarlo.py`).
- M2 global real (bgeometrics.com, 21 bancos centrales, solo desde
  sept-2022 -- limita la muestra en los tramos de ETH mas antiguos, ver
  "muestra insuficiente" en la salida para esos tramos).

Resultado (17-sept-2026): NINGUN p-valor por debajo de 0.05 en ninguna de
las ventanas de ETH (2017-2021, 2021-2023, ni 2023-2025) -- es decir, en la
fase donde hay que ENCONTRAR la señal antes de mirar BTC, no hay nada que
encontrar (p entre 0.10 y 0.996 en las 24 combinaciones de ETH). Aparecen 2
resultados con p<0.05 en BTC "todos" (GLI-3 propio, K=40d p=0.020 y K=60d
p=0.016) -- pero esto va al reves de la disciplina de validacion cruzada
del proyecto (la señal debe aparecer primero en ETH y CONFIRMARSE en BTC,
no aparecer solo en el conjunto reservado para confirmar), y con 48
comparaciones totales (2 series x 3 ventanas x 4 tramos x 2 agrupaciones)
se esperan ~2.4 falsos positivos por puro azar a p<0.05 -- exactamente lo
que aparecio. Ademas el signo de esos 2 resultados es CONTRARIO a la
hipotesis (los techos se confirman mejor cuando la liquidez SUBIA antes, no
cuando caia) -- un "hallazgo significativo" que además contradice la
hipotesis que se estaba probando es la firma tipica de ruido, no de señal.

Veredicto: descartado como filtro de contexto, igual que como señal
directa de precio. El razonamiento del usuario (una señal debil como
predictor directo puede seguir siendo util como filtro condicional) es
valido en general y coherente con como funcionan otros filtros del
proyecto -- simplemente esta serie concreta no lo es, probado con el mismo
rigor que ya exige el proyecto para cualquier filtro de contexto. Ver
`registro/intentos.jsonl`.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import json
import urllib.request

import pandas as pd

import laboratorio.patrones.factor_macro_tipos_liquidez_techo as fmt
import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab


def _cargar_json_bgeometrics(nombre: str) -> pd.Series:
    data = json.loads(urllib.request.urlopen(f"https://charts.bgeometrics.com/files/{nombre}").read())
    idx = pd.to_datetime([d[0] for d in data], unit="ms", utc=True)
    val = [d[1] for d in data]
    return pd.Series(val, index=idx).sort_index().resample("1D").last().ffill()


def _construir_gli3_propio() -> pd.Series:
    """Fed+BCE+BOJ convertido a USD, mismo metodo que
    `liquidez_global_completa_montecarlo.py` -- historia completa 2017-2026."""
    fed = fmt._cargar_fred("WALCL")
    ecb_eur = fmt._cargar_fred("ECBASSETSW")
    boj_100m_jpy = fmt._cargar_fred("JPNASSETS")
    eurusd = fmt._cargar_fred("DEXUSEU")
    jpyusd = fmt._cargar_fred("DEXJPUS")
    idx = pd.date_range("2016-01-01", "2026-09-01", freq="D", tz="UTC")
    r = lambda s: s.reindex(idx, method="ffill")
    fed, ecb_eur, boj_100m_jpy, eurusd, jpyusd = r(fed), r(ecb_eur), r(boj_100m_jpy), r(eurusd), r(jpyusd)
    return fed + ecb_eur * eurusd + (boj_100m_jpy * 1e8 / jpyusd) / 1e6


if __name__ == "__main__":
    series_macro = {
        "GLI-3 propio (Fed+BCE+BOJ)": _construir_gli3_propio(),
        "M2 global real (bgeometrics, 21 bancos, desde sept-2022)": _cargar_json_bgeometrics("glm2_in.json"),
    }

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="factor_liquidez_global_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="factor_liquidez_global_btc")

    for solo_validados in (True, False):
        fmt._analizar("ETH 2017-2021", df_eth, series_macro, df_eth["open_time"].min(), vcp.CORTE, solo_validados)
        fmt._analizar("ETH ajuste (2021-2023)", df_eth, series_macro, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, solo_validados)
        fmt._analizar("ETH tiempo (2023-2025, nunca visto)", df_eth, series_macro, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, solo_validados)
        fmt._analizar("BTC (nunca visto)", df_btc, series_macro, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, solo_validados)
