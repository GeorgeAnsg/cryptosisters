"""
19-sept-2026: primera mirada a SOLUSDT con el sistema YA CONFIRMADO en
BTC/ETH (`ejecucion/cuenta_referencia.py`), SIN TOCAR NINGUN PARAMETRO --
ni K_ATR_STOP/R_FIJO, ni los umbrales de racha_rota/pendiente_acelerada/
trailing/venta_parcial. Pedido explicito del usuario: "vamos a hacerlo en
Sol... pasame los resultados en una tablita a ver que tal va en los
años" -- esto es una prueba de TRANSFERENCIA (¿el mismo sistema, tal
cual, funciona en un activo que nunca vio?), no una recalibracion.

Reutiliza `candidatos_por_año`/`simular_cuenta` de `ejecucion/
cuenta_referencia.py` literalmente (mismo codigo que corre en
produccion para BTC/ETH) -- solo cambia la fuente de los datos, via
`cargar_ohlcv_lab` en vez del `cargar_ohlcv` restringido a <2025 que usa
`cuenta_referencia.cargar()`, para poder ver tambien 2025 (con acceso de
Validacion registrado, motivo abajo) -- no hay NADA que calibrar aqui
que se pudiera contaminar por mirarlo, es una transferencia directa de
parametros ya cerrados.

Datos: SOLUSDT diario descargado el 19-sept-2026
(`datos/descarga/descargar_ohlcv_binance.py`), 2020-08-11 a hoy -- se
descarta 2020 (año parcial, solo 4 meses) del resumen por año.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from ejecucion.cuenta_referencia import (
    K_ATR_STOP, R_FIJO, DIAS_MAXIMO, UMBRAL_SWITCH, VENTA_PARCIAL_UMBRAL,
    VENTA_PARCIAL_FRACCION, TRAILING_ACTIVACION_PCT, TRAILING_RETROCESO_PCT,
    RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX, CAPITAL_INICIAL,
    candidatos_por_año, simular_cuenta,
)
from motores.volatilidad import atr_absoluto
from salidas.pendiente_acelerada import calcular_pendiente_atr, señal_para_direccion, UMBRAL_PENDIENTE_ATR
from salidas.racha_rota import calcular_para_direccion as racha_rota_para_direccion

MOTIVO = ("Primera prueba de SOLUSDT con el sistema confirmado de BTC/ETH, sin tocar "
          "ningun parametro -- pedido explicito del usuario 19-sept-2026, "
          "prueba de transferencia a un activo nuevo, no recalibracion")

AÑOS = [2021, 2022, 2023, 2024, 2025]


def cargar(moneda: str):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_solana_transferencia",
                           acceso_validacion=True, motivo=MOTIVO)
    atr = atr_absoluto(df)
    pendiente = calcular_pendiente_atr(df, atr)
    racha_rota_largo = racha_rota_para_direccion(df, "largo")
    racha_rota_corto = racha_rota_para_direccion(df, "corto")
    señal_pendiente_largo = señal_para_direccion(pendiente, "largo", UMBRAL_PENDIENTE_ATR)
    señal_pendiente_corto = señal_para_direccion(pendiente, "corto", UMBRAL_PENDIENTE_ATR)
    return dict(
        df=df, atr=atr, pendiente=pendiente,
        racha_rota_largo=racha_rota_largo, racha_rota_corto=racha_rota_corto,
        señal_pendiente_largo=señal_pendiente_largo, señal_pendiente_corto=señal_pendiente_corto,
    )


def main():
    datos = cargar("SOLUSDT")
    df = datos["df"]
    print(f"=== SOLUSDT -- sistema confirmado BTC/ETH, SIN TOCAR PARAMETROS ===")
    print(f"Historico: {df['open_time'].iloc[0].date()} -> {df['open_time'].iloc[-1].date()} ({len(df)} velas)\n")
    print(f"{'Año':>6} {'Buy&Hold':>10} {'Sistema':>12} {'Trades':>7} {'Ganadoras':>10} {'Drawdown':>9}")
    for año in AÑOS:
        idxs = [i for i, f in enumerate(df["open_time"]) if f.year == año]
        if len(idxs) < 30:
            print(f"{año:>6}  (menos de 30 dias de datos ese año, se omite)")
            continue
        precio_ini, precio_fin = df["close"].iloc[idxs[0]], df["close"].iloc[idxs[-1]]
        retorno_hold = (precio_fin / precio_ini - 1) * 100

        cand = candidatos_por_año(df, año)
        cap, trades, gan, dd = simular_cuenta(datos, cand)
        retorno_sistema = (cap / CAPITAL_INICIAL - 1) * 100
        n = len(trades)
        pct_gan = gan / n * 100 if n else 0.0
        print(f"{año:>6} {retorno_hold:>+9.1f}% {retorno_sistema:>+11.1f}% {n:>7} "
              f"{gan:>5}/{n:<4} {dd:>+8.1f}%")


if __name__ == "__main__":
    main()
