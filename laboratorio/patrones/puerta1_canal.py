"""Puerta 1 (causalidad) aplicada a laboratorio/patrones/canal_en_vivo.py
-- 15-sept-2026 (fichero movido desde entradas/canal.py el mismo dia, ver
docstring de canal_en_vivo.py: entradas/ es solo para reglas sobre motores
ya graduados, y canal_flexible.py todavia no lo esta).

No usa el arnes generico de tests/puerta1_causalidad.py (esta pensado para
indicadores columna-a-columna sobre TODO el dataframe, y canal_en_vivo.py
no evalua "todas las filas" sino picos aparentes concretos con una
direccion). Se reimplementa la misma idea: para un puñado de picos
aparentes, calcular su probabilidad_total_si_confirma con el historico
completo y con el historico cortado justo despues de ese pico -- deben
coincidir siempre. Si no coinciden, el detector esta usando datos que en
vivo no tendria disponibles todavia.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.patrones import canal_en_vivo as en_vivo
from laboratorio.datos_lab import cargar_ohlcv_lab

SEMILLA = 42
N_MUESTRAS = 25


def probar(moneda: str, direccion: str) -> tuple[int, int]:
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="puerta1_canal")
    close = df["close"].to_numpy()
    picos = en_vivo.picos_aparentes(close)

    rng = np.random.default_rng(SEMILLA)
    muestra = rng.choice(picos, size=min(N_MUESTRAS, len(picos)), replace=False)

    ok, mal = 0, 0
    for idx in muestra:
        r_completo = en_vivo.calcular_en_vivo(df, int(idx), direccion, dia_transcurrido=0)
        # cortar el historico justo el dia del pico aparente -- como si "hoy" fuera ese dia
        df_cortado = df.iloc[: idx + 1]
        r_cortado = en_vivo.calcular_en_vivo(df_cortado, int(idx), direccion, dia_transcurrido=0)

        p_completo = r_completo.probabilidad_total_si_confirma if r_completo else None
        p_cortado = r_cortado.probabilidad_total_si_confirma if r_cortado else None

        iguales = (p_completo is None and p_cortado is None) or (
            p_completo is not None and p_cortado is not None and np.isclose(p_completo, p_cortado, atol=1e-9)
        )
        if iguales:
            ok += 1
        else:
            mal += 1
            print(f"  MISMATCH idx={idx} completo={p_completo} cortado={p_cortado}")
    return ok, mal


if __name__ == "__main__":
    total_ok, total_mal = 0, 0
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        for direccion in ["subida", "bajada", "lateral"]:
            ok, mal = probar(moneda, direccion)
            print(f"{moneda} {direccion}: OK={ok} MAL={mal}")
            total_ok += ok
            total_mal += mal
    print()
    if total_mal == 0:
        print(f"PUERTA 1 -- PASA ({total_ok} picos aparentes probados, 0 fugas de futuro)")
    else:
        print(f"PUERTA 1 -- NO PASA ({total_mal} de {total_ok + total_mal} con fuga de futuro)")
