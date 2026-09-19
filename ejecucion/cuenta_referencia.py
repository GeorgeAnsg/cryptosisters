"""
ejecucion/ -- pipeline de referencia, 17-sept-2026.

Esta es la PRIMERA vez que las piezas ya validadas (entradas, tamaño,
salidas) se juntan en un único programa fuera de `laboratorio/`, en vez
de vivir repartidas en 9+ scripts de backtest ad-hoc. No es todavía la
estrategia de Freqtrade ni el puente de Telegram que describe
`ejecucion/README.md` (eso sigue pendiente) -- es el equivalente
"de fontanería": mismo código, mismos parámetros ya confirmados, en un
único sitio, para dejar de depender de copias sueltas del laboratorio.

Ni un solo parámetro se ha vuelto a ajustar aquí. Todos vienen de
`laboratorio/patrones/sistema_confirmado_switch_14sept2026.py` (14-sept,
fuente de la verdad de los números) y de `salidas/pendiente_acelerada.py`
(15-sept, puertas 1/3/4/5 ya pasadas). Comprobación de que la migración
no ha cambiado nada: `tests/verificar_cuenta_referencia.py` reproduce,
cifra a cifra, los resultados que ya daba el script del laboratorio.

Piezas que entran, y de dónde sale cada una:
- Entradas: `motores/doble_techo.detectar()` + `motores/doble_suelo.detectar()`
  para encontrar los candidatos, `entradas/doble_techo.calcular_en_vivo()` +
  `entradas/doble_suelo.calcular_en_vivo()` para puntuarlos (día 0, sin
  esperar confirmación -- ya validado).
- Tamaño: `tamano.calcular_tamano()`.
- Salidas, las SEIS a la vez, vía `salidas/stop_objetivo.simular_trade`:
  stop 1.2×ATR / objetivo 4R (`K_ATR_STOP`, `R_FIJO`), venta parcial
  20%→50% (`venta_parcial_umbral`/`venta_parcial_fraccion`), racha rota
  con confirmación retardada del 30% (`senal_con_confirmacion` +
  `serie_confirmacion` + `caida_relativa_confirmacion`, ver
  `salidas/racha_rota.py`), pendiente acelerada como señal
  independiente (`senal_externa`, umbral 1.5×ATR/5 días, ver
  `salidas/pendiente_acelerada.py`) -- cubre el hueco de racha rota
  cuando no hay ningún pico/valle confirmado cerca -- y trailing DIARIO
  por retroceso relativo (`TRAILING_ACTIVACION_PCT`/
  `TRAILING_RETROCESO_PCT`, ver `salidas/stop_objetivo.simular_trade`
  parámetros `trailing_activacion_pct`/`trailing_retroceso_pct` sin
  `df4h`) -- protege ganancias flotantes grandes que ninguna de las otras
  cinco cubre, ver `tests/verificar_trailing_diario_confirmado.py` para
  la comprobación de que la migración desde el laboratorio no cambió
  nada.
- Switch: si aparece un candidato de dirección contraria con probabilidad
  al menos `UMBRAL_SWITCH` mayor que la posición abierta, se cierra y se
  abre la nueva -- vive aquí (no en `salidas/`) porque mezcla información
  de salida y de entrada a la vez, tal como explica
  `docs/inventario/inventario_laboratorio_a_bot.html`.

18-sept-2026: se intentó primero un SEXTO mecanismo mas ambicioso, trailing
por retroceso relativo a 4h condicional (`salidas/stop_objetivo.simular_trade`,
parámetros `trailing_umbral_intradia_pct`/`trailing_velas_persistencia`,
implementados y disponibles pero SIN USAR desde aquí). Se retiró tras
descubrir que su confirmación 8/8 en
`laboratorio/patrones/trailing_4h_persistencia.py` se hizo con
K_ATR_STOP=2.5/R_FIJO=3.0 (constantes de la "config moderada" de
`prueba_cuenta_1000e_v3_racha.py`), no con el K_ATR_STOP=1.2/R_FIJO=4.0
real de este fichero. Revalidado con los parámetros reales, el mecanismo
cae a 3/8 -- ver `registro/intentos.jsonl`, intento
`trailing_4h_persistencia_condicional_stop_real`. Ese mismo hallazgo obligó
a revisar el trailing DIARIO base (`trailing_retroceso_alto.py`, el 8/8
original con activacion=5%/retroceso=92.5%): tambien se habia validado con
K_ATR_STOP=2.5/R_FIJO=3.0. Revalidado con los parametros reales, SI se
sostiene (8/8) pero con retroceso=67.5%, no 92.5% -- es este ultimo el que
usa esta cuenta.

Lo que NO incluye todavía (fuera del alcance de esta migración):
- `filtros/`: sigue vacía a propósito -- ningún filtro de contexto probado
  sobrevivió la validación (canal, régimen, volumen, aceleración, vela,
  dominancia -- ver `registro/intentos.jsonl`).
- `cartera/`: el árbitro y el riesgo global existen pero nunca se han
  ejercitado -- esta cuenta sigue operando UN SOLO activo con UNA sola
  posición abierta a la vez, igual que todos los backtests anteriores.
- Freqtrade / Telegram / registro señal-emitida-vs-ejecutada.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

from datos.cargar import cargar_ohlcv
from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from motores import doble_suelo as motor_suelo
from motores import doble_techo as motor_techo
from motores.volatilidad import atr_absoluto
from salidas.pendiente_acelerada import calcular_pendiente_atr, señal_para_direccion, UMBRAL_PENDIENTE_ATR
from salidas.racha_rota import calcular_para_direccion as racha_rota_para_direccion, CAIDA_RELATIVA_CONFIRMACION
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

# ---- parametros confirmados (no tocar sin re-validar) ----
# Fuente: laboratorio/patrones/sistema_confirmado_switch_14sept2026.py (14-sept-2026)
K_ATR_STOP = 1.2
R_FIJO = 4.0
DIAS_MAXIMO = 45
UMBRAL_SWITCH = 0.0
VENTA_PARCIAL_UMBRAL = 0.20
VENTA_PARCIAL_FRACCION = 0.50
CAPITAL_INICIAL = 1000.0
RIESGO_BASE_PCT = 0.02
MULTIPLICADOR_MIN, MULTIPLICADOR_MAX = 0.9, 1.1

# Trailing diario por retroceso relativo, revalidado 18-sept-2026 bajo el
# stop/objetivo real de arriba (ver docstring del modulo).
# Fuente: laboratorio/patrones/trailing_retroceso_alto.py.
TRAILING_ACTIVACION_PCT = 0.05
TRAILING_RETROCESO_PCT = 0.675


CORTE_RESERVA = pd.Timestamp("2025-01-01", tz="UTC")  # 2025-2026 son datos reservados para validacion ciega


def cargar(moneda: str):
    """Datos + indicadores compartidos por todas las operaciones del año.

    Recorta a `< CORTE_RESERVA` a proposito: todos los parametros de esta
    cuenta (stop, objetivo, venta parcial, racha rota, pendiente acelerada,
    switch) se validaron solo contra 2017-2024 -- 2025/2026 son la reserva
    de validacion ciega del proyecto (ver `laboratorio/datos_lab.py`) y no
    deben colarse aqui ni aunque sea solo para que una operacion abierta a
    finales de 2024 tenga mas velas futuras con las que resolverse."""
    df = cargar_ohlcv(moneda, "1d")
    df = df[df["open_time"] < CORTE_RESERVA].reset_index(drop=True)
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


def candidatos_por_año(df: pd.DataFrame, año: int) -> list[tuple[int, str, float]]:
    """Un candidato por cada doble techo/suelo confirmado ese año,
    puntuado el mismo día en que se confirma (día 0, sin esperar más)."""
    fechas = df["open_time"]
    out = []
    for c in motor_techo.detectar(df):
        if fechas.iloc[c.idx_techo2].year != año:
            continue
        r = en_vivo_techo(df, c.idx_techo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_techo2, "corto", r.probabilidad_total_si_confirma))
    for c in motor_suelo.detectar(df):
        if fechas.iloc[c.idx_fondo2].year != año:
            continue
        r = en_vivo_suelo(df, c.idx_fondo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_fondo2, "largo", r.probabilidad_total_si_confirma))
    return sorted(out, key=lambda c: c[0])


def _abrir(datos, capital, idx, direccion, prob):
    close = datos["df"]["close"].to_numpy()
    niveles = calcular_niveles_fijos(close[idx], datos["atr"][idx], direccion, K_ATR_STOP, R_FIJO)
    racha = datos["racha_rota_largo"] if direccion == "largo" else datos["racha_rota_corto"]
    señal_pendiente = datos["señal_pendiente_largo"] if direccion == "largo" else datos["señal_pendiente_corto"]
    salida = simular_trade(
        datos["df"], idx, direccion, close[idx], niveles, DIAS_MAXIMO,
        senal_externa=señal_pendiente,
        senal_con_confirmacion=racha, serie_confirmacion=datos["pendiente"],
        caida_relativa_confirmacion=CAIDA_RELATIVA_CONFIRMACION,
        venta_parcial_umbral=VENTA_PARCIAL_UMBRAL, venta_parcial_fraccion=VENTA_PARCIAL_FRACCION,
        trailing_activacion_pct=TRAILING_ACTIVACION_PCT, trailing_retroceso_pct=TRAILING_RETROCESO_PCT,
    )
    if salida is None:
        return None
    pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
    return dict(salida=salida, idx_entrada=idx, direccion=direccion, probabilidad=prob,
                precio_entrada=close[idx], unidades=pos.unidades)


def simular_cuenta(datos, candidatos):
    close = datos["df"]["close"].to_numpy()
    capital = CAPITAL_INICIAL
    trades = []
    abierta = None

    def _cerrar(pos, motivo_switch=None):
        nonlocal capital
        s = pos["salida"]
        signo = 1 if pos["direccion"] == "largo" else -1
        fraccion_vendida = 1.0 - s.fraccion_restante
        pnl_parcial_por_unidad = fraccion_vendida * signo * (s.precio_venta_parcial - pos["precio_entrada"]) \
            if s.idx_venta_parcial is not None else 0.0
        pnl_resto = pos["unidades"] * s.fraccion_restante * (s.precio_salida - pos["precio_entrada"]) * signo
        pnl_parcial = pos["unidades"] * pnl_parcial_por_unidad
        pnl = pnl_resto + pnl_parcial
        capital += pnl
        trades.append(dict(direccion=pos["direccion"], idx_entrada=pos["idx_entrada"], idx_salida=s.idx_salida,
                            precio_entrada=pos["precio_entrada"], precio_salida=s.precio_salida,
                            motivo=motivo_switch or s.motivo, pnl_eur=round(pnl, 2), capital_tras=round(capital, 2)))

    for idx, direccion, prob in candidatos:
        if np.isnan(datos["atr"][idx]):
            continue
        if abierta is not None and idx > abierta["salida"].idx_salida:
            _cerrar(abierta)
            abierta = None
        if abierta is None:
            nueva = _abrir(datos, capital, idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
            continue
        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= UMBRAL_SWITCH:
            abierta["salida"].idx_salida = idx
            abierta["salida"].precio_salida = close[idx]
            _cerrar(abierta, motivo_switch="cambio_candidato_fuerte")
            abierta = _abrir(datos, capital, idx, direccion, prob)

    if abierta is not None:
        _cerrar(abierta)

    valores = np.array([CAPITAL_INICIAL] + [t["capital_tras"] for t in trades])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, trades, ganadoras, drawdown_max_pct


if __name__ == "__main__":
    AÑOS = [2021, 2022, 2023, 2024]
    print("=== Cuenta de referencia (ejecucion/) -- migrada del laboratorio, mismos parametros ===\n")
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        datos = cargar(moneda)
        print(f"-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(datos["df"], año)
            cap, trades, gan, dd = simular_cuenta(datos, cand)
            print(f"  {año}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- {len(trades)} trades, "
                  f"{gan} ganadoras ({gan/len(trades)*100:.0f}%), drawdown maximo {dd:.2f}%")
        print()
