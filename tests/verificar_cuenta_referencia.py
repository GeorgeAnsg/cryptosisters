"""
Puerta de regresion, 17-sept-2026 (actualizada 18-sept-2026 al añadir el
trailing diario): comprueba que `ejecucion/cuenta_referencia.py`
(la migracion de laboratorio a produccion de entradas+tamaño+salidas+switch)
reproduce, centimo a centimo, los mismos resultados que ya daban los
scripts de laboratorio de los que viene cada pieza:

- Racha rota + venta parcial + switch + stop/objetivo 1.2xATR/4R: de
  `laboratorio/patrones/sistema_confirmado_switch_14sept2026.py`.
- Pendiente acelerada (sin ningun filtro de canal, la version que se
  lleva a produccion): de `laboratorio/patrones/pendiente_veto_canal.py`,
  llamado con `en_tendencia` a False en todos los dias -- exactamente lo
  que reproduce este pipeline.
- Trailing diario por retroceso relativo (activacion=5%/retroceso=67.5%,
  revalidado 18-sept-2026 bajo el stop/objetivo real de arriba -- ver
  `salidas/stop_objetivo.py` y `tests/verificar_trailing_diario_confirmado.py`).

Este archivo NO es una prueba de que la estrategia sea buena (eso ya lo
comprobaron las puertas 1/3/4/5 de cada pieza por separado, ver
`registro/intentos.jsonl`) -- es solo la prueba de que MOVER el codigo del
laboratorio a `ejecucion/` no ha cambiado ni un solo numero.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from ejecucion.cuenta_referencia import cargar, candidatos_por_año, simular_cuenta

# Valores de referencia (18-sept-2026, con trailing diario ya incluido).
# El bloque anterior (17-sept, sin trailing) era:
#   ETHUSDT: {2021: 2473.58, 2022: 2271.03, 2023: 2074.06, 2024: 3843.86}
#   BTCUSDT: {2021: 2001.04, 2022: 3102.57, 2023: 1612.98, 2024: 2165.81}
REFERENCIA = {
    "ETHUSDT": {2021: 2453.30, 2022: 2505.95, 2023: 1960.61, 2024: 3648.18},
    "BTCUSDT": {2021: 2420.06, 2022: 3098.40, 2023: 1726.95, 2024: 2424.16},
}


def verificar():
    fallos = []
    for moneda, por_año in REFERENCIA.items():
        datos = cargar(moneda)
        for año, esperado in por_año.items():
            cand = candidatos_por_año(datos["df"], año)
            cap, _trades, _gan, _dd = simular_cuenta(datos, cand)
            if round(cap, 2) != esperado:
                fallos.append(f"{moneda} {año}: esperado {esperado}, obtenido {cap:.2f}")
            else:
                print(f"  OK  {moneda} {año}: {cap:.2f}€")
    if fallos:
        print("\nFALLOS:")
        for f in fallos:
            print(f"  {f}")
        raise SystemExit(1)
    print("\nTodo coincide -- la migracion no ha cambiado ningun numero.")


if __name__ == "__main__":
    verificar()
