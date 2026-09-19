"""Puerta 1 (causalidad) sobre el MOTOR BATCH de canal
(`canal_flexible.detectar_ascendente/descendente/lateral`) -- 15-sept-2026.

Distinto de `puerta1_canal.py` (que prueba la capa EN VIVO, tratando un
"pico aparente" como si fuera el pico2 definitivo). Aqui la pregunta es
otra: el propio detector batch, usado para explorar el historico
completo, ?usa alguna vez datos mas alla de lo estrictamente necesario
para confirmar un candidato ya encontrado? Si un candidato termina en
idx_pico2, lo minimo necesario para saber que ese candidato existe es que
pico2 este confirmado como maximo local (necesita pico2+3 dias, por la
ventana centrada de `_detectar_picos_simple`) -- nada mas alla de eso
deberia cambiar su score.

Metodo: para una muestra de candidatos reales, re-detectar sobre el
historico cortado justo en pico2+3 (el minimo exacto) y comparar el score
con el mismo candidato detectado sobre el historico completo. Tambien se
prueba un corte intermedio (pico2+15) para descartar que el minimo exacto
sea información pese a todo (un lugar plausible para un bug distinto:
dependencia de cuantos "picos futuros" hay disponibles en la lista global,
no solo del pico2 concreto).
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import canal_flexible as cf

SEMILLA = 42
N_MUESTRAS = 25
VENTANA_CONFIRMACION = 3  # la misma que _detectar_picos_simple


def _candidato_por_pico2(cands, idx_pico2):
    for c in cands:
        if c.idx_pico2 == idx_pico2:
            return c
    return None


def probar(moneda: str, direccion: str) -> tuple[int, int]:
    fn = {"subida": cf.detectar_ascendente, "bajada": cf.detectar_descendente, "lateral": cf.detectar_lateral}[direccion]
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="puerta1_canal_motor")
    cands_completo = fn(df)

    rng = np.random.default_rng(SEMILLA)
    muestra_idx = rng.choice(len(cands_completo), size=min(N_MUESTRAS, len(cands_completo)), replace=False)

    ok, mal = 0, 0
    for i in muestra_idx:
        c = cands_completo[int(i)]
        for buffer_extra in (0, 15):
            corte = c.idx_pico2 + VENTANA_CONFIRMACION + buffer_extra
            if corte >= len(df):
                continue
            df_cortado = df.iloc[: corte + 1]
            cands_cortado = fn(df_cortado)
            c_cortado = _candidato_por_pico2(cands_cortado, c.idx_pico2)

            if c_cortado is not None and np.isclose(c_cortado.probabilidad_forma, c.probabilidad_forma, atol=1e-9):
                ok += 1
            else:
                mal += 1
                encontrado = c_cortado.probabilidad_forma if c_cortado else None
                print(f"  MISMATCH {moneda} {direccion} idx_pico2={c.idx_pico2} buffer={buffer_extra} "
                      f"completo={c.probabilidad_forma} cortado={encontrado}")
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
        print(f"PUERTA 1 (motor batch) -- PASA ({total_ok} comprobaciones, 0 fugas de futuro)")
    else:
        print(f"PUERTA 1 (motor batch) -- NO PASA ({total_mal} de {total_ok + total_mal} con fuga de futuro)")
