# motores/ — el ALFA

## Qué es "un motor"
Un motor es una idea concreta de cuándo el precio va a moverse. Ejemplo: "cuando el
StochRSI sale de sobreventa y el ADX confirma tendencia, hay más probabilidad de subida
que de bajada en las próximas N velas". Eso es todo lo que hace un motor: mirar el
histórico de precio y decir "aquí hay una oportunidad, y creo que tiene esta fuerza".

## Qué entra y qué sale
- **Entra:** histórico de precio (velas OHLCV) y lo que se derive directamente de él
  (RSI, ADX, medias, etc.).
- **Sale:** un candidato con un **pronóstico** — no una orden, no un tamaño, solo "aquí
  probablemente pasa algo, y con esta intensidad".

## Lo que un motor NO sabe y NO debe saber
- No sabe si hay noticias importantes hoy (eso es de `filtros/`).
- No sabe cuánto capital hay ni cuánto arriesgar (eso es de `tamano/`).
- No sabe cuándo cerrar la operación (eso es de `salidas/`).
- No sabe si ya hay 5 posiciones abiertas o si el mercado entero está temblando
  (eso es de `cartera/`).

Si un motor empieza a mirar cosas de fuera de su carril, ya no es un motor: es un totum
revolutum donde nadie puede saber qué falló cuando algo va mal. Esa mezcla es exactamente
la que permitió que `bb_extremo` se colara sin pasar controles en el proyecto anterior.

## Estado (12-sept-2026)
Esta sección de "8-sept" quedó desfasada: se escribió ANTES de que existiera la
metodología de detección flexible (`laboratorio/patrones/`, validada a partir del
10-sept). El plan original de re-verificar el catálogo heredado de corvus3
(StochRSI+ADX, Canal/Donchian, MACD, EMA, Supertrend...) sigue pendiente en sí mismo
-- nadie lo ha tocado todavía -- pero el track de **patrones de precio** ha avanzado
por un camino distinto y ya tiene dos motores graduados:

- **`regimen_mercado.py`** — clasificador compartido (BAJISTA/ALCISTA/NEUTRO), usado
  por los dos motores de abajo.
- **`doble_techo.py`** — graduado el 12-sept-2026. Validado con cruce de moneda y de
  tiempo, y confirmado de nuevo en la partición de Validación (2025) nunca antes
  tocada, incluyendo aislado a BTC solo. Historial completo en
  `laboratorio/patrones/doble_techo_motor_v2.py`.
- **`doble_suelo.py`** — graduado el 12-sept-2026. Mismo nivel de validación que el
  techo (no es un espejo asumido, se probó desde cero con sus propios factores).
  Historial completo en `laboratorio/patrones/doble_suelo_motor_v2.py`.
- **`canal_ascendente.py`** y **`canal_descendente.py`** — graduados el 15-sept-2026,
  DOS motores separados (mismo criterio que techo/suelo: no se tratan como un espejo
  asumido — los pesos ganadores, la fracción de confirmación y hasta la dinámica
  temporal de cada uno son distintos, ver docstring de `canal_descendente.py`). Motor
  propio (NO composición con doble techo/suelo — se probaron dos vías de composición
  ese mismo día y ninguna dio ventaja real, limitadas de raíz porque doble techo/suelo
  solo empareja niveles parecidos, incompatible con una estructura con pendiente). Dos
  capas cada uno: forma geométrica (`canal_flexible.py`, pesos congelados en
  ETH-ajuste) + confirmación de ruptura de la proyección de la línea. Validados con 5
  monedas y Monte Carlo (p=0.0000 ambas direcciones), puertas 1/4/5 PASA. Historial
  completo en `laboratorio/patrones/canal_confirmacion_5monedas_montecarlo.py`. **Sin
  Capa 3 de contexto todavía** (regimen_mercado, ATH, volumen...) — pendiente de
  explorar. **Canal lateral/neutro NO es un tercer motor todavía** — existe el
  detector (`canal_flexible.detectar_lateral`) pero nunca pasó la validación de 5
  monedas + Monte Carlo; sigue en `laboratorio/`, pendiente de probarse desde cero.

Ambos se verificaron contra sus versiones de laboratorio con datos reales de BTC y ETH
antes de darlos por migrados (mismo `probabilidad_total`, `score_regimen`,
`score_contexto` y `tipo_regimen`, candidato a candidato) — la migración no cambió
ningún número ya validado.

**Pendiente, documentado dentro de cada fichero:** varias constantes de las que
dependen estos dos motores (los dos umbrales de `regimen_mercado.py`, la tolerancia de
"nivel repetido" del techo, y el reparto 50/50 forma/contexto de ambos) todavía no
están derivadas de un barrido de datos reales — se heredaron sin cambio para no alterar
los resultados ya cerrados, marcadas explícitamente como "NO DERIVADO AÚN" en el código.
Calibrarlas es un cambio de comportamiento real (afecta a todos los candidatos) y exige
re-confirmar la validación después — no se ha hecho todavía a propósito.

El catálogo heredado de corvus3 (StochRSI+ADX y el resto, ver `docs/00-PLAN-MAESTRO.md`
§10.1) sigue sin re-verificar — no bloquea a los motores de patrones, son pistas
independientes.

## Regla de oro
Un motor se re-escribe aquí **solo después** de demostrarse en `laboratorio/`. Nunca al
revés.
