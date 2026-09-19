"""
Puerta de regresion, 18-sept-2026: comprueba que la rama `usa_trailing_diario`
de `salidas/stop_objetivo.simular_trade` (graduada de
`laboratorio/patrones/trailing_retroceso_alto._simular_trade_manual`)
reproduce, para cada candidato real de ETH/BTC 2021-2024, EXACTAMENTE el
mismo dia/precio/motivo de salida que la funcion de laboratorio -- usando
los niveles calculados con K_ATR_STOP=1.2/R_FIJO=4.0 (los REALES de
`ejecucion/cuenta_referencia.py`, no los 2.5/3.0 con los que se habia
validado por error el 8/8 original).

Historia (ver `registro/intentos.jsonl` y `salidas/stop_objetivo.py`): el
trailing diario se confirmo primero (17-sept) con activacion=5%/retroceso=
92.5%, pero esa validacion uso K_ATR_STOP=2.5/R_FIJO=3.0 -- un perfil de
riesgo que ya no es el de produccion. Revalidado con los parametros reales,
el punto que se sostiene 8/8 es activacion=5%/retroceso=67.5%. Este archivo
NO es una prueba de que el mecanismo sea bueno (eso ya lo decidio esa
revalidacion) -- es solo la prueba de que la migracion a `salidas/` no
cambio ningun numero.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.patrones.prueba_multi_anio import candidatos_por_año
from laboratorio.patrones.trailing_retroceso_alto import _cargar, _simular_trade_manual
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

K_ATR_STOP_REAL = 1.2
R_FIJO_REAL = 4.0
DIAS_MAXIMO = 45
ACTIVACION = 0.05
RETROCESO = 0.675
AÑOS = [2021, 2022, 2023, 2024]


def verificar():
    fallos = []
    total = 0
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = _cargar(moneda)
        close = df["close"].to_numpy()
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            for idx, direccion, prob in cand:
                if np.isnan(atr[idx]):
                    continue
                total += 1
                niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP_REAL, R_FIJO_REAL)
                senal = rt if direccion == "largo" else rs

                r_lab = _simular_trade_manual(
                    df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                    senal, pendiente, 0.3, ACTIVACION, RETROCESO,
                )
                r_prod = simular_trade(
                    df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                    senal_externa=None,
                    senal_con_confirmacion=senal, serie_confirmacion=pendiente, caida_relativa_confirmacion=0.3,
                    trailing_activacion_pct=ACTIVACION, trailing_retroceso_pct=RETROCESO,
                )
                if r_lab is None or r_prod is None:
                    if r_lab is None and r_prod is None:
                        continue
                    fallos.append(f"{moneda} {año} idx={idx}: uno de los dos devuelve None y el otro no")
                    continue
                idx_salida_lab, precio_salida_lab, motivo_lab = r_lab
                motivo_lab_equiv = motivo_lab if motivo_lab != "senal_externa" else "senal_confirmada"
                if (r_prod.idx_salida, round(r_prod.precio_salida, 6), r_prod.motivo) != \
                   (idx_salida_lab, round(precio_salida_lab, 6), motivo_lab_equiv):
                    fallos.append(
                        f"{moneda} {año} idx={idx} {direccion}: lab=({idx_salida_lab},{precio_salida_lab:.4f},{motivo_lab}) "
                        f"prod=({r_prod.idx_salida},{r_prod.precio_salida:.4f},{r_prod.motivo})"
                    )

    print(f"Total candidatos comparados: {total}")
    if fallos:
        print(f"\nFALLOS ({len(fallos)}):")
        for f in fallos[:40]:
            print(f"  {f}")
        if len(fallos) > 40:
            print(f"  ... y {len(fallos) - 40} mas")
        raise SystemExit(1)
    print("Coincide exactamente en todos los candidatos -- la graduacion del trailing diario no cambio nada.")


if __name__ == "__main__":
    verificar()
