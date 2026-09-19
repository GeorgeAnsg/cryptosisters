"""Motor "canal ascendente" -- graduado 15-sept-2026.

Separado de "canal descendente" en su propio fichero (15-sept-2026, mismo
criterio que doble_techo.py/doble_suelo.py: no se tratan como un espejo
asumido el uno del otro). Los pesos y la fraccion de confirmacion que
ganaron son distintos entre ascendente y descendente, y su dinamica
temporal tambien lo es (ver mas abajo) -- son dos motores independientes
que comparten la misma FORMULA de forma/confirmacion, no el mismo motor
con una bandera de direccion.

("Canal lateral/neutro" NO es un tercer motor todavia: existe el
detector, `canal_flexible.detectar_lateral`, pero nunca paso por la
validacion de 5 monedas + Monte Carlo que si pasaron ascendente y
descendente hoy. Sigue en `laboratorio/`, pendiente de probarse desde
cero antes de graduarlo.)

Idea del usuario, refinada durante toda la sesion de hoy: tras descartar
dos vias de composicion (canal como filtro de contexto sobre doble
techo/suelo, y canal construido combinando sus puntos ya emparejados --
ver laboratorio/patrones/canal_como_filtro_contexto.py y
canal_via_4puntos_geometria.py, ambas sin ventaja real y la segunda
limitada de raiz porque doble techo/suelo solo empareja techos/suelos a
NIVEL PARECIDO, incompatible con un canal con pendiente), la version que
si funciona es canal como MOTOR PROPIO, con sus propios minimos/maximos
(canal_flexible.py), en dos capas:

CAPA 1 -- FORMA (geometria pura): pendiente, paralelismo, ancho,
consistencia del ancho y contencion (el precio real no se sale de la
banda) -- ver canal_flexible.py para la formula completa. Pesos
congelados en `laboratorio/patrones/validacion_canal_excedente_benchmark.py`
(seleccion en ETH-ajuste, exceso sobre benchmark incondicional).

CAPA 2 -- CONFIRMACION: un canal no es un patron de reversion con
neckline horizontal, es una estructura diagonal -- "confirmar" es que el
precio cruce la PROYECCION hacia adelante de la resistencia (misma
pendiente que ya tenia), no un nivel fijo. Formula extraida de
`laboratorio/patrones/validacion_cruzada_pesos.py::_entradas_confirmadas_canal`
(no se reimplementa suelta -- misma logica exacta).

**Fix critico de hoy, ya incorporado en la seleccion de pesos/fraccion:**
el retorno de exito se mide SIEMPRE desde `idx_pico2` (fin del canal),
nunca desde el dia de confirmacion -- medirlo desde la confirmacion
penalizaba de forma artificial a descendente (ver docstring de
canal_descendente.py para el detalle). No afecta a la formula de este
motor en si (que solo emite candidatos, no calcula retorno), pero
condiciono toda la validacion de abajo.

Validacion (15-sept-2026): 5 monedas (ETH/BTC/XRP/SOL/BNB), Monte Carlo
(5000 sims, permutacion con/sin confirmacion), diferencia con p=0.0000 --
ver `laboratorio/patrones/canal_confirmacion_5monedas_montecarlo.py` para
el detalle completo, moneda a moneda. Puerta 1 (causalidad) y puerta 5
(recursividad) ya PASADAS sobre el motor batch de canal_flexible.py
(`laboratorio/patrones/puerta1_canal_motor.py`,
`puerta5_canal_motor.py`). Puerta 4 (presupuesto/DSR) PASA (t-stat 4.03,
listón por azar 2.68 con 155 intentos). **Puerta 3 (costes reales) se
evalua a nivel de CARTERA, no por motor individual** (regla del usuario,
15-sept-2026) -- no se hace aqui.

Pendiente, no bloqueante para graduar (documentado para la siguiente
iteracion, igual que motores/doble_techo.py deja sus propias constantes
"NO DERIVADO AUN"):
- CAPA 3 (contexto de mercado: regimen_mercado.py, distancia al ATH,
  volumen...) todavia no se ha probado para canal. Los candidatos que
  emite este motor NO tienen contexto todavia -- solo forma + confirmacion.
- `confirmado=False` no significa "señal mala": significa "todavia sin
  ventaja demostrada" -- la ventaja validada hoy es especificamente el
  contraste confirmado-vs-no-confirmado, no la forma sola.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from laboratorio.patrones import canal_flexible as cf

# Pesos y fraccion de confirmacion ya congelados esta mañana en
# validacion_canal_excedente_benchmark.py (seleccion en ETH-ajuste).
PESOS = dict(
    peso_pendiente=0.55, peso_paralelismo=0.10, peso_ancho=0.15,
    peso_consistencia=0.10, peso_contencion=0.10,
)
FRACCION_CONFIRMACION = 0.35

# Minimo de dias de ventana de confirmacion, igual que
# validacion_cruzada_pesos.DIAS_CONFIRMACION -- evita que un canal muy
# corto (pocos dias) se quede con una ventana de confirmacion ridicula.
DIAS_CONFIRMACION_MINIMO = 10


@dataclass
class CandidatoCanalAscendente:
    idx_fondo1: int
    idx_pico1: int
    idx_fondo2: int
    idx_pico2: int
    probabilidad_forma: float  # CAPA 1 -- geometria pura (0-1)
    confirmado: bool  # CAPA 2 -- ¿rompio la proyeccion de la resistencia?
    idx_confirmacion: int | None


def calcular(df: pd.DataFrame) -> list[CandidatoCanalAscendente]:
    """CAPA 1 + CAPA 2. La ventaja validada es especificamente el
    contraste `confirmado=True` vs `confirmado=False` (ver docstring del
    modulo) -- todavia sin Capa 3 de contexto."""
    close = df["close"].to_numpy()
    n = len(df)
    candidatos = cf.detectar_ascendente(df, **PESOS)
    out = []
    for c in candidatos:
        dias_confirmacion = max(DIAS_CONFIRMACION_MINIMO, round(FRACCION_CONFIRMACION * c.dias_total))
        fin_conf = min(c.idx_pico2 + 1 + int(dias_confirmacion), n)
        idx_confirmacion = None
        slope_abs = (c.precio_pico2 - c.precio_pico1) / (c.idx_pico2 - c.idx_pico1)
        for x in range(c.idx_pico2 + 1, fin_conf):
            proyeccion = c.precio_pico2 + slope_abs * (x - c.idx_pico2)
            if close[x] > proyeccion:
                idx_confirmacion = x
                break
        out.append(CandidatoCanalAscendente(
            idx_fondo1=c.idx_fondo1, idx_pico1=c.idx_pico1,
            idx_fondo2=c.idx_fondo2, idx_pico2=c.idx_pico2,
            probabilidad_forma=c.probabilidad_forma,
            confirmado=idx_confirmacion is not None, idx_confirmacion=idx_confirmacion,
        ))
    return out
