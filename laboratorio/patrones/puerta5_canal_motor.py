"""Puerta 5 (recursividad/calentamiento) sobre el motor batch de canal --
15-sept-2026.

canal_flexible.py no usa ningun indicador recursivo (EMA/RSI/ADX/Wilder) --
solo `rolling(30).mean()` sobre volumen, una ventana FIJA. Segun
`tests/puerta5_recursividad.py`, una ventana fija no deberia depender de
cuanto pasado haya detras siempre que haya al menos esas 30 velas
disponibles -- pero se comprueba empiricamente en vez de asumirlo (regla
del proyecto: nada de absolutos sin verificar).

Metodo: para una muestra de candidatos reales, re-detectar sobre una
ventana de historia_disponible velas ANTES del candidato (bastante mayor
que rolling(30) y que dias_max_tramo=60) y comparar candidato a candidato
contra el historico completo.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import canal_flexible as cf

SEMILLA = 42
N_MUESTRAS = 25
HISTORIA_DISPONIBLE = 150  # > rolling(30) y > dias_max_tramo(60), con margen


def _candidato_por_pico2(cands, idx_pico2):
    for c in cands:
        if c.idx_pico2 == idx_pico2:
            return c
    return None


def probar(moneda: str, direccion: str) -> tuple[int, int]:
    fn = {"subida": cf.detectar_ascendente, "bajada": cf.detectar_descendente, "lateral": cf.detectar_lateral}[direccion]
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="puerta5_canal_motor")
    cands_completo = fn(df)

    candidatos_validos = [c for c in cands_completo if c.idx_fondo1 >= HISTORIA_DISPONIBLE]
    rng = np.random.default_rng(SEMILLA)
    muestra_idx = rng.choice(len(candidatos_validos), size=min(N_MUESTRAS, len(candidatos_validos)), replace=False)

    ok, mal = 0, 0
    for i in muestra_idx:
        c = candidatos_validos[int(i)]
        inicio = c.idx_fondo1 - HISTORIA_DISPONIBLE
        # fin necesita cubrir tanto la confirmacion de pico2 (+3, ventana
        # centrada) como la ventana de volumen tras la confirmacion
        # (dias_ventana_volumen=6 por defecto) -- si se corta antes de eso,
        # lo que se mide no es "cuanto pasado hace falta" (Puerta 5) sino
        # una fuga de FUTURO distinta (Puerta 1), que no es lo que se
        # quiere aislar aqui.
        fin = min(c.idx_pico2 + 3 + 6, len(df) - 1)
        df_limitado = df.iloc[inicio: fin + 1].reset_index(drop=True)

        cands_limitado = fn(df_limitado)
        idx_pico2_relativo = c.idx_pico2 - inicio
        c_limitado = _candidato_por_pico2(cands_limitado, idx_pico2_relativo)

        campos_iguales = (
            c_limitado is not None
            and np.isclose(c_limitado.probabilidad_forma, c.probabilidad_forma, atol=1e-9)
            and np.isclose(c_limitado.volumen_ratio, c.volumen_ratio, atol=1e-6)
        )
        if campos_iguales:
            ok += 1
        else:
            mal += 1
            print(f"  MISMATCH {moneda} {direccion} idx_pico2={c.idx_pico2} "
                  f"completo(prob={c.probabilidad_forma}, vol_ratio={c.volumen_ratio}) "
                  f"limitado={'no encontrado' if c_limitado is None else (c_limitado.probabilidad_forma, c_limitado.volumen_ratio)}")
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
        print(f"PUERTA 5 (motor batch) -- PASA ({total_ok} comprobaciones, sin dependencia del historial disponible)")
    else:
        print(f"PUERTA 5 (motor batch) -- NO PASA ({total_mal} de {total_ok + total_mal})")
