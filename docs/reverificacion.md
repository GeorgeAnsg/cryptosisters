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

## 2a-bis. Ideas nuevas propuestas por el usuario (8-sept-2026), en cola

1. **Canal diagonal (rebote dentro de un canal ascendente/descendente)** —
   ❌ **DESCARTADO (8-sept-2026).** Código: `laboratorio/canal_diagonal_rebote.py`
   (pivotes causales confirmados con ventana de 10 velas, líneas ajustadas
   por regresión sobre los últimos 3 pivotes, sin dibujar a ojo). Puerta 1
   (causalidad): PASA. Backtest real entrada→salida, Desarrollo 2020-2024,
   229 operaciones: retorno medio +0,03% (~cero), retorno total compuesto
   **-13,6%**, caída máxima -41%, t=0,12 p=0,91 contra cero — indistinguible
   de ruido puro incluso antes de restar ningún coste. Confirma con datos
   propios lo que ya decía la investigación: soporte/resistencia es la
   categoría peor evidenciada de todo el trading discrecional, incluso
   definida de forma objetiva y sin sesgo de mirar hacia atrás.

   **Segunda vuelta, a petición del usuario (no conforme con una sola
   configuración) — barrido de 108 combinaciones + verificación cruzada en
   1h.** Correcto pedir esto: una sola configuración no basta para descartar
   nada. Resultado, con tres comprobaciones independientes:
   - **Inestable:** mediana de retorno total = -6,7% (media +7,3%, inflada
     por pocos casos extremos — firma típica de sobreajuste, no de ventaja
     real). Solo 30,6% de las 108 combinaciones superan +20%.
   - **La mejor esquina se apaga con el tiempo:** retorno medio por
     operación +0,45% (2020) → +0,37% (2021) → -0,04% (2022) → +0,10%
     (2023) → +0,07% (2024). Patrón de "foto vieja" (regla 8 heredada de
     corvus3): fuerte en el bull viejo, casi plano en lo reciente.
   - **No se repite en 1h:** misma ventana equivalente en horas, retorno
     total -21%, retorno medio ~0%, sin patrón por año.

   **DESCARTADO tras la segunda vuelta** (no una config con suerte, sino
   ausencia de robustez en tres ejes distintos).

   **Tercera vuelta, a petición del usuario — margen/tolerancia relativos a
   la ALTURA del canal** (no % fijo del precio; corrección metodológica
   válida, un canal ancho y uno estrecho no deberían tener el mismo margen
   absoluto). Resultado, esta vez más prometedor a primera vista: mediana
   +3,4% (vs -6,7% del barrido anterior), 53,1% de combinaciones positivas,
   la mejor combinación (167 operaciones) sin decaer por año y con algo
   parecido apareciendo en 1h. **Pero la prueba decisiva lo tumba igual:**
   comparado contra el baseline correcto (comprar BTC al azar la misma
   duración que cada operación, ~2,6 días), el exceso es de solo +0,13
   puntos porcentuales con **p=0,83** — estadísticamente cero. El +0,82%
   contra cero (p=0,043) que parecía prometedor es un falso positivo
   esperable de probar 192 configuraciones (se esperan ~10 así solo por
   azar). La estrategia gana porque está comprada en BTC la mayor parte
   del tiempo durante un periodo muy alcista, no por ninguna ventaja real
   del canal — mismo mecanismo exacto que tumbó a StochRSI+ADX.

   **DEFINITIVAMENTE DESCARTADO** tras 3 vueltas de verificación (config
   única → barrido fijo → barrido relativo a altura + baseline correcto).
   `registro/intentos.jsonl` guarda las tres vueltas por separado.
2. **Bloques de acumulación / soporte-resistencia** — propuesta del usuario:
   zonas donde el precio se acumula fuerte y rebota repetidamente entre dos
   bloques, hasta que algo lo rompe. Ya investigado en
   `investigacion/06-traders-discrecional.md`: es la categoría con **peor
   evidencia real de todo el trading discrecional** (order blocks ICT:
   0 de 648 backtests le ganó a comprar-y-esperar en un estudio serio; el
   propio gurú más seguido de soporte/resistencia admite que "es muy difícil
   de backtestear porque es subjetivo"). El sub-componente más objetivable
   (Spring de Wyckoff: ruptura falsa + recuperación rápida) sigue en la cola
   del catálogo con prioridad media. **Pendiente, en cola.**

## 2b. Doble suelo — ✅ APROBADO CONDICIONAL (2 de 6 puertas, alta robustez)

**Corrección importante:** la nota "aún no bate costes" del roadmap de
corvus2 estaba **desactualizada** — corresponde a una versión anterior sin
confirmación de volumen. La versión final (`DobleFondoVolVolumen`) sí
llegó a validarse en 2025 (+17,7% no visto), aunque en universo
**multi-moneda**, no BTC solo — mismo patrón que StochRSI, así que había
que comprobar si sobrevive en BTC solo antes de fiarse.

Código: `laboratorio/doble_suelo.py` + `laboratorio/doble_suelo_backtest.py`.
Regla: doble suelo (≥2 toques en ventana de 120 velas/~20 días, patrón
≥15% de altura) + confirmación de volumen (>1,5x su media de 30 velas) al
romper el neckline. Salida: objetivo fijo 30% / stop fijo -12% (sin salida
dinámica todavía, igual que el original).

| Puerta | Resultado |
|---|---|
| 1. Causalidad | **PASA** — 30 cortes, 0 diferencias |
| 2. Paridad backtest-vivo | No evaluable — falta `ejecucion/` |
| 3. Costes reales | Pendiente formal, pero operaciones duran semanas/meses → spread previsiblemente irrelevante |
| 4. Presupuesto de intentos (DSR) | Pendiente de cálculo formal |
| 5. Recursividad/calentamiento | **PASA** — con calentamiento correcto (≥500 velas; el primer intento con 200 falló por warmup insuficiente en la prueba, no por problema real del indicador) |
| 6. Riesgo de cartera | No evaluable — falta `cartera/` |

**BTC solo, Desarrollo 2020-2024:** 15 operaciones, +16,2% media, **+620,6%
total compuesto**, 66,7% ganadoras, caída máxima -36,3%. Contra el baseline
correcto (comprar BTC al azar, misma duración): exceso **+20,1pp, p=0,021**
— pasa la prueba que tumbó a StochRSI y al canal diagonal.

**Barrido de robustez, 108 combinaciones** (ventana/altura/tolerancia/
vol_mult): **100% positivas**, peor caso +12,2%, mediana +257,1%. Mucho más
robusto que canal diagonal (que solo "ganaba" en una esquina concreta).

**Matiz honesto:** muestra pequeña por configuración (15-19 operaciones en
5 años) y la evidencia original de corvus2 era multi-moneda — aquí se
confirma que SÍ hay algo real en BTC solo, a diferencia de StochRSI, pero
con menos operaciones que si se contara sobre varias monedas. Candidato
serio, segundo junto a Canal. Pendiente: Puertas 2, 3 (formal), 4, 6.

## 2c. Patrones nuevos propuestos por el usuario (8-sept-2026)

1. **Hombro-cabeza-hombro invertido (alcista)** — ❌ **DESCARTADO.** Nunca
   se había probado en ningún corvus anterior (estaba anotado como "el
   siguiente motor natural" tras doble suelo, pero corvus2 cambió de
   arquitectura antes de construirlo). Código: `laboratorio/hch_invertido.py`
   (detección causal por pivotes, objetivo por measured move). Config por
   defecto: -32,1% total, p=0,609 contra baseline. Barrido de 25
   combinaciones: mediana -7,7% pese a media +6,6% (misma firma de
   sobreajuste que canal diagonal). Mejor combo (46 trades) contra
   baseline correcto: p=0,417, no significativo, con decaimiento claro por
   año (+7,99%/trade en 2020 → -2,22% en 2024). Descartado con la misma
   solidez que canal diagonal.
2. **Doble techo (corto, filtro downtrend estricto)** — ✅ **APROBADO
   CONDICIONAL.** Corvus2 solo tenía el bear de 2022 para probarlo (n=1).
   Con los 9 años de histórico BTC descargados para corvus4, se pudo
   probar contra **tres mercados bajistas independientes**: 2018, marzo
   2020 (COVID) y 2022 — ya no es n=1. Código: `laboratorio/doble_techo.py`
   + `doble_techo_backtest.py` (espejo de doble_suelo, con filtro de
   tendencia bajista estricta: precio bajo su media de 200 días Y esa
   media cayendo, no un bajón pasajero).

   | Puerta | Resultado |
   |---|---|
   | 1. Causalidad | **PASA** |
   | 5. Recursividad | **PASA** (1600 velas de calentamiento) |
   | 2, 3 (formal), 4, 6 | Pendientes |

   BTC solo, 2017-2024 (excluyendo 2025 validación y 2026 reserva,
   intactos): 7 operaciones repartidas en los 3 bears, +26,4% media,
   **+380,2% total compuesto**, 85,7% ganadoras, caída máxima -13%.
   Contra baseline correcto (vender al azar, misma duración): exceso
   **+34,45pp, p=0,011**. Barrido de 108 combinaciones: **100% positivas**,
   peor caso +39,2%, mediana +123,7% — incluso más robusto que doble
   suelo. Muestra absoluta pequeña (7 trades) pero repartida en 3
   regímenes bajistas distintos, no concentrada en uno solo. Tercer
   candidato serio del proyecto.
3. **Hombro-cabeza-hombro normal** (bajista) — mismo problema que doble
   techo (cortos + evidencia bajista limitada a un año). Nunca probado.
   En cola, prioridad baja mientras no haya más de un mercado bajista con
   el que contrastar.

## 3. Resto del catálogo heredado

Pendiente.

## 4. Motores nuevos (M1-M4)

No se abre hasta cerrar los tres puntos anteriores.
