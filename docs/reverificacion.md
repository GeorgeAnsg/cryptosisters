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

## 2a. Canal (Donchian) — RoturaCanalLargo

**Situación de partida, distinta de StochRSI:** esto no es un cribado a medio
probar — es un motor ya construido como estrategia real de Freqtrade en
`corvus2` (`user_data/strategies/rotura_canal.py` + `rotura_canal_largo.py`),
con evidencia pre-registrada mucho más dura que un cribado por horizonte fijo.
Código portado (adaptado a BTC-solo) en `laboratorio/canal.py`.

Regla: compra cuando BTC rompe su máximo de 20 días Y está por encima de su
media de 200 días; cierra cuando cae a su canal de 10 días O la media de 200
días pasa a bajista (protección) — lo que ocurra antes.

| Puerta | Qué comprueba | Resultado | Fuente |
|---|---|---|---|
| 1. Causalidad | ¿Usa datos del futuro? | **PASA** — re-confirmado en corvus4, 30 cortes sobre BTC 2017-2026, 0 diferencias. El código ya usaba `shift(1)` a propósito. | `tests/puerta1_causalidad.py`, 2026-09-08 |
| 2. Paridad backtest-vivo | ¿Backtest y vivo son el mismo código? | **No evaluable todavía** — mismo motivo que StochRSI: no existe pieza "de vivo" separada hasta que exista `ejecucion/`. En corvus2 al menos backtest/dry-run/vivo comparten el mismo `IStrategy` de Freqtrade (Regla 1 de corvus2), que es la mitad de esta garantía. | — |
| 3. Costes reales | ¿Sobrevive con costes? | **PASA (heredado)** — validación 2025: +15% neto de costes (PF 1,31) vs BTC -6,6%. Grupo B sellado: +37% neto de costes vs cesta -10,9%. | `corvus2/docs/preregistro_validacion_2025.md`, `preregistro_sellado.md` |
| 4. Presupuesto de intentos (DSR) | ¿Es azar por cuántas veces se probó? | **PASA (heredado, con matiz)** — es una configuración fijada de antemano sin barrido de parámetros (20/10 días = "Donchian System 1" de los Turtles, valor de convención, no ajustado a los datos), lo que reduce mucho el riesgo de sobreajuste. No se ha recalculado un DSR formal en corvus4 todavía. | `corvus2/user_data/strategies/rotura_canal.py` (docstring) |
| 5. Recursividad/calentamiento | ¿Cambia según cuánta historia tenga el bot en vivo? | **PASA** — probado en corvus4: con solo 1500 velas de historial (vs 19.794 totales), 0 diferencias en 30 puntos al azar. Es matemáticamente esperable: media móvil y máximos/mínimos de ventana fija no tienen memoria más allá de su ventana (a diferencia de EMA/RSI/ADX, que sí la tienen). | `tests/puerta5_recursividad.py`, 2026-09-08 |
| 6. Riesgo de cartera | ¿Se comporta bien combinado con otras posiciones? | **No evaluable todavía** — hace falta al menos un segundo motor y `cartera/` construida para que esta pregunta tenga sentido; con una sola pieza no hay nada que combinar. | — |

**Qué significa esto para decidir:** de las 6 puertas, 4 tienen veredicto
positivo — dos re-confirmadas hoy mismo en corvus4 (1 y 5), dos heredadas de
evidencia pre-registrada honesta de corvus2 (3 y 4). Las 2 que faltan (2 y 6)
no es que hayan fallado — es que todavía no existe la pieza del sistema
(`ejecucion/`, `cartera/`) necesaria para probarlas de verdad. **Canal es, con
diferencia, el candidato más sólido de todo el proyecto hasta ahora.**

**El matiz importante que no hay que perder:** esto es "beta con riesgo
gestionado", no alfa — no le gana a comprar BTC y no tocarlo nunca durante un
mercado alcista completo (2020-2025: +95% la estrategia vs +1.336% BTC solo).
Su valor es otro: gestiona bien el capital que SÍ se mueve activamente,
recortando caídas fuerte (27% vs 77% de comprar-y-aguantar en el peor caso
visto). Pendiente de re-plantear con el usuario cómo encaja esto con la regla
de riesgo ya cerrada (1%/operación, 3-4% pérdida diaria máxima).

## 2b. Doble suelo

**No es un motor terminado — está a medio construir.** El roadmap de corvus2
lo marca explícitamente: *"⚙️ afinando: buena forma, aún no bate costes"*. No
hay una versión validada que re-verificar; hay trabajo sin acabar. Se trata
como una decisión aparte (¿merece la pena terminarlo, o se prioriza otra
cosa?) en vez de meterlo en la cola de re-verificación como si ya existiera.
Pendiente de decidir con el usuario.

## 3. Resto del catálogo heredado

Pendiente.

## 4. Motores nuevos (M1-M4)

No se abre hasta cerrar los tres puntos anteriores.
