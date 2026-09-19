"""Motor "canal descendente" -- graduado 15-sept-2026.

Separado de "canal ascendente" en su propio fichero (mismo criterio que
doble_techo.py/doble_suelo.py: no se tratan como un espejo asumido el uno
del otro). Ver `canal_ascendente.py` para el contexto completo de la
sesion (dos vias de composicion descartadas, arquitectura de 2 capas).

**Por que descendente tiene su propio fichero y no es solo "ascendente
con el signo cambiado", con evidencia concreta de hoy:**
- Los pesos que ganaron son distintos: aqui domina contencion (0.35) y
  ancho (0.30), pendiente pesa solo 0.05 -- en ascendente domina pendiente
  (0.55) y contencion pesa solo 0.10.
- La fraccion de confirmacion tambien difiere (0.15 aqui, 0.35 en
  ascendente).
- La dinamica temporal es distinta de raiz: las caidas en cripto son
  mucho mas rapidas que las subidas. Medido hoy: cuando ASCENDENTE
  confirma, el precio ya se movio +6.6% de media desde el fin del canal;
  cuando DESCENDENTE confirma, ya se movio -14.5% -- mas del doble.
  **Esto causo un bug real** al medir el resultado: contar el retorno de
  exito desde el dia de CONFIRMACION (en vez de desde `idx_pico2`, fin del
  canal) hacia parecer que descendente confirmado predecia MENOS caida que
  descendente sin confirmar (al reves de lo esperado) -- porque para
  cuando confirmaba ya se habia perdido la mayor parte del movimiento, y
  lo que seguia era mas rebote que continuacion. Corregido midiendo
  SIEMPRE desde `idx_pico2`: con el fix, descendente confirmado predice
  caidas bastante mas fuertes que sin confirmar, en los 3 tramos de
  validacion cruzada, igual de consistente que ascendente.

CAPA 1 -- FORMA (geometria pura): pendiente, paralelismo, ancho,
consistencia del ancho y contencion -- ver canal_flexible.py. Pesos
congelados en `laboratorio/patrones/validacion_canal_excedente_benchmark.py`.

CAPA 2 -- CONFIRMACION: el precio cruza la PROYECCION hacia adelante del
SOPORTE (misma pendiente que ya tenia) -- confirma si cae por debajo.
Formula extraida de
`laboratorio/patrones/validacion_cruzada_pesos.py::_entradas_confirmadas_canal`.

Validacion (15-sept-2026): 5 monedas (ETH/BTC/XRP/SOL/BNB), Monte Carlo
(5000 sims), diferencia con p=0.0000 -- ver
`laboratorio/patrones/canal_confirmacion_5monedas_montecarlo.py`. Puerta 1
y puerta 5 PASADAS (`laboratorio/patrones/puerta1_canal_motor.py`,
`puerta5_canal_motor.py`). Puerta 4 (DSR) PASA (t-stat 15.05 tras invertir
el signo del retorno -- "acertar" aqui es que el precio BAJE -- listón por
azar 2.68 con 155 intentos). **Puerta 3 (costes reales) se evalua a nivel
de CARTERA, no por motor individual** (regla del usuario, 15-sept-2026).

Pendiente, no bloqueante para graduar:
- CAPA 3 (contexto de mercado) todavia no se ha probado para canal.
- `confirmado=False` no significa "señal mala": significa "todavia sin
  ventaja demostrada".
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from laboratorio.patrones import canal_flexible as cf

# Pesos y fraccion de confirmacion ya congelados esta mañana en
# validacion_canal_excedente_benchmark.py (seleccion en ETH-ajuste).
PESOS = dict(
    peso_pendiente=0.05, peso_paralelismo=0.20, peso_ancho=0.30,
    peso_consistencia=0.10, peso_contencion=0.35,
)
FRACCION_CONFIRMACION = 0.15

DIAS_CONFIRMACION_MINIMO = 10


@dataclass
class CandidatoCanalDescendente:
    idx_fondo1: int
    idx_pico1: int
    idx_fondo2: int
    idx_pico2: int
    probabilidad_forma: float  # CAPA 1 -- geometria pura (0-1)
    confirmado: bool  # CAPA 2 -- ¿rompio la proyeccion del soporte?
    idx_confirmacion: int | None


def calcular(df: pd.DataFrame) -> list[CandidatoCanalDescendente]:
    """CAPA 1 + CAPA 2. La ventaja validada es especificamente el
    contraste `confirmado=True` vs `confirmado=False` -- todavia sin
    Capa 3 de contexto. IMPORTANTE al medir retorno con estos candidatos:
    medir SIEMPRE desde `idx_pico2` (fin del canal), nunca desde
    `idx_confirmacion` -- ver docstring del modulo, ese fue el bug de hoy."""
    close = df["close"].to_numpy()
    n = len(df)
    candidatos = cf.detectar_descendente(df, **PESOS)
    out = []
    for c in candidatos:
        dias_confirmacion = max(DIAS_CONFIRMACION_MINIMO, round(FRACCION_CONFIRMACION * c.dias_total))
        fin_conf = min(c.idx_pico2 + 1 + int(dias_confirmacion), n)
        idx_confirmacion = None
        slope_abs = (c.precio_fondo2 - c.precio_fondo1) / (c.idx_fondo2 - c.idx_fondo1)
        for x in range(c.idx_pico2 + 1, fin_conf):
            proyeccion = c.precio_fondo2 + slope_abs * (x - c.idx_fondo2)
            if close[x] < proyeccion:
                idx_confirmacion = x
                break
        out.append(CandidatoCanalDescendente(
            idx_fondo1=c.idx_fondo1, idx_pico1=c.idx_pico1,
            idx_fondo2=c.idx_fondo2, idx_pico2=c.idx_pico2,
            probabilidad_forma=c.probabilidad_forma,
            confirmado=idx_confirmacion is not None, idx_confirmacion=idx_confirmacion,
        ))
    return out
