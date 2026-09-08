# Re-verificación de los 43 intentos heredados — seguimiento

Ver `docs/00-PLAN-MAESTRO.md` §10.1 para el porqué y el orden de esta lista.
Orden: StochRSI+ADX → Canal (Donchian) y Doble suelo → resto del catálogo →
motores nuevos.

Cada candidato pasa por las 6 puertas de `tests/`. Solo cuando pasa las 6 se
re-escribe de verdad en `motores/`. Si falla una, se para ahí y se anota el
motivo — no hace falta gastar tiempo en las puertas siguientes.

## 1. StochRSI + ADX — ❌ DESCARTADO (8-sept-2026)

**Muerto para este proyecto. No se prueba más, no se construye en `motores/`,
no queda pendiente de nada.** Cayó en la Puerta 3, detalle completo abajo.

Código del candidato: `laboratorio/stochrsi_adx.py` (réplica fiel de
`~/Desktop/tr/v6/core/bot_indicators.py`). Tres variantes: A) sobreventa sin
mirar tendencia, B) sobreventa solo en tendencia bajista confirmada, C) cruce
alcista.

| Puerta | Qué comprueba, en una frase | Resultado | Fecha |
|---|---|---|---|
| 1. Causalidad | ¿El indicador usó alguna vez datos del futuro? | **PASA** — 60 cortes al azar sobre BTC 4h (2017-2026), 0 diferencias | 2026-09-08 |
| 2. Paridad backtest-vivo | ¿El código de decisión sería el mismo en vivo? | **No evaluable todavía** — no existe una segunda versión "de vivo" contra la que comparar (`ejecucion/` sigue vacío); se retoma cuando exista | 2026-09-08 |
| 3. Costes reales | ¿Sigue siendo rentable descontando el spread real? | **NO PASA** — ver detalle abajo | 2026-09-08 |
| 4. Presupuesto de intentos (DSR) | ¿El resultado podría ser azar por cuántas veces se ha probado? | No aplica — cayó en la Puerta 3 | — |
| 5. Recursividad/calentamiento | ¿Cambia la señal según cuánto histórico tenga disponible el bot en vivo? | No aplica — cayó en la Puerta 3 | — |
| 6. Riesgo de cartera | ¿Se comporta bien combinado con las demás posiciones abiertas? | No aplica — cayó en la Puerta 3 | — |

**Puerta 1 — qué significó:** solo descartaba una cosa muy concreta, que el
indicador estuviera haciendo trampa mirando al futuro. No la hacía. Eso nunca
confirmó que fuera a ganar dinero, solo que si ganaba no sería por esa trampa.

**Puerta 3 — el detalle, y por qué cae aquí:**

Medido en BTC solo (la decisión de construir "solo BTC" ya cerrada), 2023-2024,
horizonte fijo de 20 velas (~3,3 días) como cribado barato, comparando contra
comprar BTC en cualquier momento al azar en el mismo periodo:

| Variante | Eventos | Retorno medio evento | Baseline (azar) | Exceso |
|---|---|---|---|---|
| A) sobreventa | 210 | +0,538% | +0,908% | **-0,370%** |
| B) sobreventa + tendencia bajista | 75 | -0,050% | +0,908% | **-0,958%** |
| C) cruce alcista | 275 | +0,989% | +0,908% | +0,081% |

A y B pierden contra el azar sin restar ningún coste — mueren solas, el spread
no es ni siquiera el problema. C parecía ganar por +0,081 puntos, pero:

- **El dato real de spread en QuantFury** (observación directa del usuario,
  8-sept-2026, ver memoria `project_corvus4_costes_quantfury`): en BTC el
  spread es ~0%. Así que el margen de C no se lo come el coste.
- **Pero ese margen no es estadísticamente real.** Test t sobre los 275
  eventos de C contra el baseline: t=0,274, **p=0,784**. Es decir, si no
  hubiera ningún patrón real, veríamos una diferencia así de grande (o mayor)
  el 78% de las veces solo por azar. No hay ventaja demostrable.

**Por qué esto no cuadra con el catálogo de corvus3** (que hablaba de
+2,50%/+2,78%/+1,56% por evento sobre un baseline de +0,88%): aquella prueba
se hizo sobre **34 monedas a la vez**, no solo BTC. La ventaja original podría
ser en gran parte un efecto de comparar/repartir entre muchas monedas
correlacionadas, que no se sostiene operando BTC en solitario.

**Veredicto: StochRSI+ADX (las 3 variantes) NO PASA en BTC solo.** No se
re-escribe en `motores/`. Se para aquí — no tiene sentido gastar las puertas
4, 5 y 6 en algo que ya no muestra ventaja. Esto NO significa que la idea
esté "mal" en general: podría funcionar como efecto cruzado entre monedas
(quedaría pendiente si algún día se abre el universo más allá de BTC), pero
tal como está planteado el proyecto ahora mismo (solo BTC), no sirve.

**Siguiente:** pasar a Canal (Donchian) y Doble suelo, los próximos en la
cola de `docs/00-PLAN-MAESTRO.md` §10.1.

## 2. Canal (Donchian) y Doble suelo

Pendiente — siguiente en la cola.

## 3. Resto del catálogo heredado

Pendiente.

## 4. Motores nuevos (M1-M4)

No se abre hasta cerrar los tres puntos anteriores.
