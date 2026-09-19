# cartera/ — el riesgo GLOBAL y el ÁRBITRO

## Qué hace (dos trabajos, una carpeta)

**1. El árbitro.** Cuando varios motores señalan candidatos a la vez y solo hay hueco
para 5 posiciones (límite operativo del usuario), alguien tiene que decidir cuáles se
toman. Regla ya resuelta: como la fuerza de la señal no sirve para elegir (ver
`tamano/README.md`), se elige por **prioridad fija según la calidad ya demostrada de
cada motor** en su re-verificación. Repartir entre huecos limitados no cambia el signo
del resultado esperado, solo la varianza — ya se comprobó en corvus3.

**2. El riesgo de cartera.** Un multiplicador (de 0 a 1) que se aplica a TODAS las
posiciones a la vez, tomando el más conservador de estos tres:
- El riesgo esperado total es demasiado alto.
- Hay una sacudida de correlación con posiciones ya extremas (todo se mueve junto de
  golpe — el peor momento para tener 5 posiciones sin relación entre sí).
- La volatilidad se ha vuelto errática de repente.

Este multiplicador reduce todas las posiciones a la vez, no una por una.

**3. Banda muerta (dead-band).** No se reajusta una posición por cambios pequeños del
pronóstico, solo cuando cruza un umbral. En ejecución manual por Telegram esto es la
diferencia entre 3 avisos al día y 40 — y el usuario ejecuta a mano, así que esto
importa de verdad.

## Por qué es nueva respecto a corvus3
En corvus3 esto quedó como pregunta abierta ("el árbitro, pendiente"). Aquí ya está
resuelto en el plan (§6.1) antes de escribir una sola línea de código.

## Estado (8-sept-2026)
Vacío. Necesita al menos dos motores re-verificados para tener sentido (con uno solo no
hay nada que arbitrar).

## Primera prueba del límite de posiciones simultáneas (15-sept-2026)

Motivada por la revisión visual del 14/15-sept: en la subida de ETH del 04-feb al
11-mar-2024, el sistema descartó 4 candidatos de largo con probabilidad 0.79-0.96 solo
porque ya había un corto abierto. Se probó `laboratorio/patrones/prueba_cartera_multiposicion.py`:
mismo doble suelo/techo + racha rota de siempre, pero permitiendo varias posiciones
simultáneas (sin arbitraje por calidad -- solo hay un motor todavía -- y SIN límite de
riesgo conjunto, ver aviso abajo), barriendo el límite de huecos en vez de aceptar el 5
del plan original sin comprobarlo:

| max_posiciones | ETH capital final | ETH descartadas | BTC capital final | BTC descartadas |
|---|---|---|---|---|
| 1 (actual) | 1153.10€ (+15.3%) | 60 de 79 | 1142.59€ (+14.3%) | 52 de 70 |
| 2 | 1409.40€ (+40.9%) | 40 | 1275.40€ (+27.5%) | 36 |
| 3 | 1730.45€ (+73.0%) | 27 | 1448.98€ (+44.9%) | 22 |
| **5 (límite ya decidido)** | **1990.46€ (+99.0%)** | 9 | **1640.33€ (+64.0%)** | 5 |
| 10 (~sin límite) | 2001.45€ (+100.1%) | 0 | 1787.73€ (+78.8%) | 0 |

El límite de 1 posición (el que hay hoy en producción) deja sobre la mesa la inmensa
mayoría de la ganancia disponible en 2024 -- confirma cuantitativamente la sospecha del
usuario. El límite de 5 ya decidido en este mismo README (8-sept-2026, antes de tener
datos) captura casi todo el beneficio (99% de la subida de ETH, 64% la de BTC, frente al
100.1%/78.8% de no tener límite práctico) con muy pocos descartes -- no fue una elección
arbitraria, los datos la confirman razonable. El drawdown máximo también sube con más
posiciones (de -2.7%/-4.2% con 1, a -6.2%/-7.1% con 5) pero se mantiene moderado.

**Aviso importante, todavía sin resolver:** esta prueba dimensiona cada posición de forma
INDEPENDIENTE con `tamano/calcular_tamano()` (~2% de riesgo cada una), sin ningún tope al
riesgo TOTAL abierto a la vez -- con 5 posiciones simultáneas el riesgo conjunto puede
llegar a ~10% del capital si las 5 van mal a la vez, y esto NO está limitado por
correlación (todas las posiciones de este sistema salen del mismo par de motores, muy
correlacionadas entre sí -- si un techo/suelo falla, varios pueden fallar juntos). Este es
precisamente el "riesgo de cartera" que este README ya identificaba como pendiente en
`riesgo_global.py` -- sin él, este resultado sobreestima la ganancia real sin mostrar el
riesgo real de una racha mala con varias posiciones abiertas a la vez. Pendiente antes de
aceptar esto como candidato de producción: (1) implementar el multiplicador de riesgo
conjunto de `riesgo_global.py`, (2) repetir esta misma tabla con ese tope puesto, (3)
probar con Monte Carlo si una racha mala simultánea en las 5 posiciones es tan dañina como
parece a simple vista.

**Todavía no probado:** correr BTC y ETH como una única cartera con capital compartido
(aquí cada moneda se probó como una cuenta de 1000€ separada) -- es la extensión natural
de esta misma pregunta, pendiente de construir.

## Corrección del usuario (15-sept-2026): 5 posiciones en el MISMO activo no es realista

El usuario aclaró que la prueba anterior estaba mal planteada: no se pueden tener 5
posiciones simultáneas en el MISMO activo -- lo realista es 1 posición por activo (BTC y
ETH, cada uno su propio hueco, como ya funciona). El problema real que señaló es otro y más
difícil: dentro de UN solo activo, con 1 solo hueco, un short mediocre ya abierto bloquea un
long mucho mejor que aparece después.

## Cambio de posición por candidato más fuerte — PROBADA Y VALIDADA (15-sept-2026)

`laboratorio/patrones/prueba_cambio_candidato_fuerte.py`: en vez de descartar un candidato
nuevo de dirección contraria solo por no haber hueco, se permite CERRAR la posición abierta
HOY (al precio de cierre de hoy, sin mirar al futuro) y abrir la nueva, pero solo si su
probabilidad supera a la de la abierta por un margen mínimo (`UMBRAL_SWITCH`, barrido, no un
número fijo a ojo). 100% causal: la comparación usa solo probabilidades ya conocidas en ese
momento, nunca el resultado futuro real de ninguna operación.

Resultado en la cuenta secuencial completa de 2024 (1 solo hueco por activo, en todo
momento -- nunca 2 operaciones abiertas a la vez en la misma moneda):

| | sin cambio (actual) | con cambio (umbral óptimo) |
|---|---|---|
| ETH (ajuste) | 1153.10€ (+15.3%) | **1743.22€ (+74.3%)** |
| BTC (confirmación, mismo umbral sin retocar) | 1142.59€ (+14.3%) | **1507.99€ (+50.8%)** |

Mejora fuerte y confirmada en las dos monedas, sin retocar nada al pasar de ETH a BTC. El
drawdown máximo NO empeora (ETH -2.74%→-2.17%, BTC se mantiene en -4.2%) y la tasa de
acierto sube en ambas (ETH 13/19→32/35, BTC 12/18→29/34). Verificado con el caso concreto
que motivó la idea: en el rally de ETH de 04-feb a 11-mar-2024, el long de probabilidad
0.882 (23-feb) y el de 0.959 (19-mar) que antes se descartaban por tener un corto mediocre
abierto (prob. 0.502 y 0.57) ahora SÍ se toman, cortando el corto ese mismo día -- ambos
cambios resultan ganadores.

**Aviso honesto sobre el barrido de `UMBRAL_SWITCH`:** el resultado NO tiene un óptimo
interior -- es monótono, cuanto más bajo el umbral (más fácil cambiar), mejor, hasta el
límite `umbral=0` (cambiar en cuanto el contrario tenga probabilidad ESTRICTAMENTE mayor,
sin exigir ningún margen). Es decir, el "margen mínimo" que se quería probar no aporta nada
real -- la regla que de verdad funciona es la más simple posible: "si aparece un candidato
contrario mejor, cambia, sin más condición". Esto no es el problema de borde de un barrido
mal diseñado (no absolutos) -- es que esa dimensión concreta (el margen) no existe como
palanca útil; se deja documentado para no repetir la prueba pensando que falta ampliar el
rango.

**Pendiente antes de producción:** (1) el mismo aviso de riesgo conjunto que la prueba
anterior -- aquí no hay más de 1 posición a la vez por activo, así que el riesgo por
operación nunca se acumula, pero SÍ falta comprobar el coste de comisión/slippage de cada
cambio de posición (aquí se asume gratis, coherente con "spread real ~0% en BTC" ya medido,
pero no verificado para ETH ni para el caso de varios cambios seguidos); (2) probar si
permitir también cambios en la MISMA dirección (un long mejor sustituyendo a un long peor
ya abierto) aporta algo más, no probado todavía; (3) ~~Monte Carlo de esta regla~~ ver
validación multi-año más abajo, que cubre la misma preocupación con datos reales en vez de
remuestreo.

## Validación multi-año (15-sept-2026): ¿es un efecto real o solo de 2024?

Aviso del propio usuario: todo lo anterior se había ajustado y confirmado SOLO en 2024
(ETH para ajustar, BTC para confirmar) -- pero las dos monedas comparten el mismo año, y
2024 fue alcista en ambas. Riesgo real de estar sobreajustando a la forma concreta de un
solo gráfico. `laboratorio/patrones/prueba_multi_anio.py`: se repite la MISMA cuenta de
1000€ (mismo motor, misma señal de racha rota N=4/M=5, mismo `UMBRAL_SWITCH=0.0` ya
validado, sin retocar nada entre años) en 2021 (alcista fuerte), 2022 (bajista fuerte),
2023 (lateral/recuperación) y 2024 (alcista) -- los cuatro únicos años completos
disponibles en el histórico (2017-2024).

| Año | ETH sin cambio | ETH con cambio | BTC sin cambio | BTC con cambio |
|---|---|---|---|---|
| 2021 (buy&hold ETH +404%, BTC +58%) | +19,8% | **+56,6%** | +21,0% | **+48,2%** |
| 2022 (buy&hold ETH -68%, BTC -65%) | +11,7% | **+17,2%** | +41,0% | **+64,8%** |
| 2023 (buy&hold ETH +90%, BTC +155%) | +0,8% | **+19,6%** | +1,6% | **+34,4%** |
| 2024 (buy&hold ETH +42%, BTC +112%) | +15,3% | **+74,3%** | +14,3% | **+50,8%** |

**Gana en las 8 combinaciones (2 monedas × 4 años), sin retocar ningún parámetro entre
años.** El caso más importante es 2022 (mercado bajista brutal, ETH -68% en el propio
precio): el cambio de candidato sigue ganando y además reduce el drawdown máximo frente a
no cambiar (-2,17% vs -4,09% en ETH). No es un efecto que dependa de estar en un mercado
alcista como 2024 -- se sostiene en los cuatro regímenes de mercado disponibles. Esto no
sustituye una validación en datos fuera de 2017-2024 (no existen en este proyecto), pero sí
descarta que el resultado sea un artefacto de un único año o de la casualidad de que ETH y
BTC compartieran régimen en la prueba original.

**Sigue pendiente, no resuelto por esto:** el coste de comisión/slippage por cambio y los
cambios en la misma dirección (puntos 1 y 2 arriba).
