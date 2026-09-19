"""
19-sept-2026: barrido de RIESGO_BASE_PCT (3%, 3.5%, 4%) pedido por el
usuario tras ver que el 2% actual deja posiciones "muy pequeñas" en euros.
No reimplementa nada: recorre año a año llamando a
`ejecucion.quantfury.bot_paper.procesar_dia` (la MISMA funcion del bot en
vivo, ya verificada contra `salidas/stop_objetivo.py` en
`tests/verificar_bot_paper_salidas_vs_graduado.py`), solo que sobreescribe
temporalmente `bot_paper.RIESGO_BASE_PCT` en memoria para cada nivel --
nunca toca el fichero, el valor de produccion sigue siendo 0.02 hasta que
el usuario elija uno de estos tres y se cambie a mano.

Incluye 2021-2024 (Desarrollo, sin restriccion de acceso) A LA VEZ que
2025 (Validacion) porque el usuario preguntaba especificamente por el
drawdown en los años con las rachas de perdidas peores -- 2025 por si
solo nunca tuvo una racha larga (ver conversacion), así que decidir el
riesgo solo con 2025 seria optimista.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

import ejecucion.quantfury.bot_paper as bp
from laboratorio.datos_lab import cargar_ohlcv_lab

MOTIVO = ("Barrido de RIESGO_BASE_PCT (3%/3.5%/4%) sobre 2025 para elegir nivel de riesgo, "
          "pedido explicito del usuario 19-sept-2026")

NIVELES = [0.03, 0.035, 0.04]
AÑOS_DESARROLLO = [2021, 2022, 2023, 2024]


def _correr_año(par: str, df, series, año: int) -> tuple[float, list[dict]]:
    estado = {
        "capital_interno": bp.CAPITAL_INICIAL, "capital_real_usuario": bp.CAPITAL_INICIAL,
        "posiciones": {p: None for p in bp.PARES},
    }
    idxs = [i for i, f in enumerate(df["open_time"]) if f.year == año]
    eventos = []
    for idx in idxs:
        estado["capital_real_usuario"] = estado["capital_interno"]
        eventos.extend(bp.procesar_dia(par, df, idx, estado, enviar=False, series=series))
    return estado["capital_interno"], eventos


def _drawdown_max(eventos: list[dict], capital_inicial: float) -> float:
    valores = [capital_inicial] + [e["capital_interno_tras"] for e in eventos if e["evento"] in ("cierra", "venta_parcial")]
    valores = np.array(valores)
    pico = np.maximum.accumulate(valores)
    return float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0


def main():
    for nivel in NIVELES:
        bp.RIESGO_BASE_PCT = nivel
        print(f"\n=== RIESGO_BASE_PCT = {nivel:.1%} ===")
        for par in ["BTCUSDT", "ETHUSDT"]:
            df_dev = cargar_ohlcv_lab(par, "1d", estrategia="prueba_barrido_riesgo_base")
            series_dev = bp.precalcular_series(df_dev)
            print(f"  {par} -- Desarrollo (2021-2024, ya validado, sin acceso especial):")
            for año in AÑOS_DESARROLLO:
                cap, eventos = _correr_año(par, df_dev, series_dev, año)
                dd = _drawdown_max(eventos, bp.CAPITAL_INICIAL)
                print(f"    {año}: {cap:.2f}€ ({(cap/bp.CAPITAL_INICIAL-1)*100:+.1f}%), drawdown max {dd:.1f}%")

            df_val = cargar_ohlcv_lab(par, "1d", estrategia="prueba_barrido_riesgo_base",
                                       acceso_validacion=True, motivo=MOTIVO)
            series_val = bp.precalcular_series(df_val)
            cap25, eventos25 = _correr_año(par, df_val, series_val, 2025)
            dd25 = _drawdown_max(eventos25, bp.CAPITAL_INICIAL)
            print(f"  {par} -- Validacion 2025: {cap25:.2f}€ ({(cap25/bp.CAPITAL_INICIAL-1)*100:+.1f}%), drawdown max {dd25:.1f}%")


if __name__ == "__main__":
    main()
