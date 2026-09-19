"""
Puerta de regresion, 17-sept-2026: comprueba que
`laboratorio/patrones/trailing_retroceso_alto.py` (movido desde los
scripts sueltos de la sesion en la que se encontro el mecanismo) reproduce,
centimo a centimo, los mismos resultados que dio el script original.

Historia de la seleccion de parametros (ver docstring completo en
`laboratorio/patrones/trailing_retroceso_alto.py`): el primer intento
eligio el mejor punto mirando solo ETH 2024 (5%/75%, 2056.57€) y solo
confirmo despues -- resulto generalizar peor (5/8) que el punto del grid
grueso (10%/85%, 6/8) pese a ser "mejor" en su propio año de ajuste.
Corregido seleccionando por ROBUSTEZ en ETH 2021-2023 (sin tocar ni
ETH-2024 ni BTC): el punto final es activacion=5%/retroceso=92.5%, que
gana en las 8 de 8 combinaciones de confirmacion.

Este archivo NO es una prueba de que el mecanismo sea bueno (eso lo decide
la validacion cruzada) -- es solo la prueba de que el codigo (movido y
luego corregido) reproduce siempre los mismos numeros.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from laboratorio.patrones.trailing_retroceso_alto import (
    _cargar, _simular, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS

# capital final por (moneda, año, activacion, retroceso) -- referencia fijada
# el 17-sept-2026, punto final tras la correccion metodologica.
REFERENCIA = {
    ("ETHUSDT", 2024, 0.10, 999): 1920.90,    # baseline sin trailing (comun a todos los puntos)
    ("ETHUSDT", 2021, 0.05, 0.925): 1640.83,  # confirmado 8/8 -- punto final en produccion
    ("ETHUSDT", 2022, 0.05, 0.925): 1381.36,
    ("ETHUSDT", 2023, 0.05, 0.925): 1242.50,
    ("ETHUSDT", 2024, 0.05, 0.925): 2012.58,
    ("BTCUSDT", 2021, 0.05, 0.925): 1639.41,
    ("BTCUSDT", 2022, 0.05, 0.925): 1695.11,
    ("BTCUSDT", 2023, 0.05, 0.925): 1533.05,
    ("BTCUSDT", 2024, 0.05, 0.925): 1484.34,
    ("ETHUSDT", 2024, 0.05, 0.75): 2056.57,   # punto descartado (solo gana 5/8), referencia historica
    ("ETHUSDT", 2024, 0.10, 0.85): 2006.10,   # punto descartado (solo gana 6/8), referencia historica
}


def verificar():
    fallos = []
    cache = {}
    for (moneda, año, act, retroceso), esperado in REFERENCIA.items():
        if moneda not in cache:
            cache[moneda] = _cargar(moneda)
        df, atr, rt, rs, pendiente = cache[moneda]
        cand = candidatos_por_año(df, año)
        cap, _n, _gan, _dd, _disp = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, act, retroceso)
        if round(cap, 2) != esperado:
            fallos.append(f"{moneda} {año} act={act:.0%} retroceso={retroceso}: esperado {esperado}, obtenido {cap:.2f}")
        else:
            print(f"  OK  {moneda} {año} act={act:.0%} retroceso={retroceso}: {cap:.2f}€")
    if fallos:
        print("\nFALLOS:")
        for f in fallos:
            print(f"  {f}")
        raise SystemExit(1)
    print("\nTodo coincide -- la migracion no ha cambiado ningun numero.")


if __name__ == "__main__":
    verificar()
