"""
18-sept-2026: traducción del riesgo a la mecánica REAL de liquidación de
QuantFury, para la vertiente de ejecución manual por Telegram.

Cómo funciona QuantFury (confirmado por el usuario, ver
[[quantfury_balance]] en memoria y la conversación del 18-sept-2026):
- Depositas capital REAL (`capital`, ej. 100€).
- QuantFury da un PODER DE TRADING = capital × APALANCAMIENTO (~20x, ej.
  2000€) -- es el tamaño nocional máximo que puedes abrir, no dinero que
  tengas de verdad.
- Las ganancias se suman al capital real y el poder de trading crece con
  ellas (100€->200€->300€... según el usuario), no es un tope fijo.
- **La liquidación es de TODA LA CUENTA, no por posición.** Si la pérdida
  acumulada de lo que tengas abierto en ese momento (una posición o varias
  a la vez) llega al 100% del capital REAL depositado, se cierra la cuenta
  entera y se pierde todo -- no hay margen aislado por operación como en
  un exchange con isolated margin.

Esto NO cambia la fórmula de `tamano/tamano.py` (`calcular_tamano` ya
arriesga un % del capital REAL -- `capital`, no `poder_de_trading` -- así
que el riesgo en dinero por operación ya está bien anclado). Lo que faltaba
y aporta este módulo son dos comprobaciones de seguridad ESPECÍFICAS de
QuantFury que no existen en un exchange normal:

1. **Techo de tamaño nocional**: el `poder_de_trading` es un límite físico
   -- no se puede pedir una posición más grande aunque el riesgo en dinero
   "cuadre" con un stop muy ajustado. `tamano.calcular_tamano` no lo sabe
   (no conoce el apalancamiento del bróker), así que hay que capar aquí.
2. **Riesgo conjunto simultáneo**: con hasta 2 huecos a la vez (BTC + ETH,
   ver `cartera/README.md`), si las dos posiciones tocan stop el MISMO día
   la pérdida se SUMA sobre el mismo capital real -- hay que vigilar que
   esa suma se quede muy por debajo del 100% que liquida la cuenta, con
   margen de sobra (no basta con "no llegar exactamente a 100%").
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass

APALANCAMIENTO_QUANTFURY = 20  # ratio confirmado en cada tramo (siempre 20x), 18-sept-2026

# Tabla de tramos REAL de QuantFury (18-sept-2026, dada por el usuario de
# memoria): el poder de trading NO escala continuo con el capital -- se
# queda FIJO en el valor del tramo hasta que el capital cruza el siguiente
# umbral, entonces salta. Ej.: con 250e de capital (entre el tramo de 100 y
# el de 300) el poder sigue siendo 2000e, NO 250*20=5000e -- ratio efectivo
# mucho menor que 20x justo antes de cruzar cada umbral. Todos los puntos
# conocidos son exactamente 20x en el umbral, pero el escalón entre medias
# es la parte que importa para no sobreestimar el poder disponible.
# Fuera de este rango (capital<50 o >10000) no hay dato confirmado --
# `poder_de_trading` extrapola con el mismo 20x del extremo más cercano,
# marcado explícitamente como extrapolación, no como tabla real.
TABLA_TRAMOS_QUANTFURY: list[tuple[float, float]] = [
    (50, 1_000),
    (100, 2_000),
    (300, 6_000),
    (500, 10_000),
    (1_000, 20_000),
    (2_000, 40_000),
    (5_000, 100_000),
    (10_000, 200_000),
]
_UMBRALES = [t[0] for t in TABLA_TRAMOS_QUANTFURY]


def poder_de_trading(capital: float, tabla: list[tuple[float, float]] = TABLA_TRAMOS_QUANTFURY) -> tuple[float, bool]:
    """Devuelve (poder_de_trading, es_extrapolado). Busca el tramo activo
    por escalón (no interpola) -- el poder se queda plano hasta cruzar el
    siguiente umbral, igual que en la app real."""
    umbrales = [t[0] for t in tabla]
    i = bisect.bisect_right(umbrales, capital) - 1
    if i < 0:
        # por debajo del tramo mas bajo conocido (50e): extrapola con el
        # mismo ratio 20x del primer tramo, sin confirmar en la app real
        return capital * APALANCAMIENTO_QUANTFURY, True
    umbral, poder = tabla[i]
    if capital >= tabla[-1][0] * 2:
        # muy por encima del ultimo tramo conocido (10000e): extrapola
        return capital * APALANCAMIENTO_QUANTFURY, True
    return poder, False


@dataclass
class Tramo:
    indice: int  # posicion en TABLA_TRAMOS_QUANTFURY, -1 si esta por debajo del primer umbral
    umbral_capital: float
    poder_de_trading: float
    extrapolado: bool


def tramo_actual(capital: float, tabla: list[tuple[float, float]] = TABLA_TRAMOS_QUANTFURY) -> Tramo:
    """Identifica EN QUE tramo esta un capital dado -- pensado para el
    seguimiento semanal manual (18-sept-2026): el usuario reporta el
    balance real cada semana y esto dice si toca subir/bajar de tramo."""
    umbrales = [t[0] for t in tabla]
    i = bisect.bisect_right(umbrales, capital) - 1
    poder, extrapolado = poder_de_trading(capital, tabla)
    umbral = tabla[i][0] if i >= 0 else 0.0
    return Tramo(indice=i, umbral_capital=umbral, poder_de_trading=poder, extrapolado=extrapolado)


def comparar_tramo_semanal(capital_anterior: float, capital_actual: float) -> dict:
    """Compara el tramo de la semana pasada contra el de ahora. Devuelve
    si ha cambiado y en que direccion -- esto es lo que se reporta al
    usuario cuando pide el balance semanal, no el capital en si."""
    anterior = tramo_actual(capital_anterior)
    actual = tramo_actual(capital_actual)
    cambio = actual.indice - anterior.indice
    return {
        "tramo_anterior": anterior,
        "tramo_actual": actual,
        "cambio": "sube" if cambio > 0 else "baja" if cambio < 0 else "igual",
        "n_tramos": cambio,
    }


@dataclass
class TamanoQuantFury:
    unidades: float
    notional: float
    riesgo_dinero: float
    capado_por_poder_trading: bool
    poder_extrapolado: bool


def capar_a_poder_trading(
    unidades: float,
    precio: float,
    riesgo_dinero: float,
    capital: float,
) -> TamanoQuantFury:
    """Toma el tamaño ya calculado por `tamano.calcular_tamano` (que solo
    conoce riesgo en dinero y distancia al stop, sin saber de bróker) y lo
    recorta si su nocional supera el poder de trading disponible en el
    TRAMO actual -- eso no reduce el riesgo en dinero planeado por el
    motor, es un límite físico de lo que QuantFury deja abrir."""
    notional = unidades * precio
    maximo, extrapolado = poder_de_trading(capital)
    if notional <= maximo:
        return TamanoQuantFury(unidades, notional, riesgo_dinero, capado_por_poder_trading=False, poder_extrapolado=extrapolado)
    factor = maximo / notional
    return TamanoQuantFury(unidades * factor, maximo, riesgo_dinero * factor, capado_por_poder_trading=True, poder_extrapolado=extrapolado)


def riesgo_conjunto_pct(riesgos_dinero_abiertos: list[float], capital: float) -> float:
    """% del capital real que se perdería si TODAS las posiciones abiertas
    a la vez tocaran su stop el mismo día -- el número que de verdad
    importa en QuantFury (liquidación de cuenta completa), no el riesgo
    por operación aislado."""
    return sum(riesgos_dinero_abiertos) / capital * 100 if capital > 0 else 0.0


UMBRAL_ALERTA_RIESGO_CONJUNTO_PCT = 20.0  # margen de seguridad muy por debajo del 100% que liquida
