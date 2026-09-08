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
