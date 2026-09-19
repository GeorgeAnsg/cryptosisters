# salidas/ — el CUÁNDO CERRAR

## Qué hace
Una vez que una posición está abierta, esta capa decide cuándo cerrarla:
- Objetivo de beneficio (take-profit).
- Stop de pérdida.
- Tiempo máximo en la operación (si no ha pasado nada, se cierra igualmente).
- Trailing (mover el stop a favor si el precio avanza).

## Por qué es su propia carpeta y no parte del motor
Un hallazgo ya documentado en `corvus3` (Regla 10 del catálogo heredado): un cribado
rápido puede parecer que funciona porque mide "qué pasa a N velas fijas", pero la
operación real no llega a esa vela — sale antes por el stop o por una salida dinámica.
`bb_extremo` pasó el cribado y luego falló el backtest real por esta razón exacta.
Separar "cuándo entro" (motor) de "cuándo salgo" (esta carpeta) obliga a probar la
salida de verdad, con las reglas de salida de verdad, no con un horizonte de mentira.

## Qué NO hace
- No decide si abrir la operación.
- No decide el tamaño.
- No sabe nada de otras posiciones abiertas.

## Catálogo previsto (S1-S4)
Ver `docs/00-PLAN-MAESTRO.md` §7.5.

## Mecánica implementada (`stop_objetivo.py`, 13-sept-2026)
Ni el stop ni el objetivo son un porcentaje fijo — los dos se calculan en función del
ATR (`motores/volatilidad.py`, graduado desde `laboratorio/` el mismo día porque
`laboratorio/` no se puede importar desde una capa de producción), para que el margen se
adapte a si el mercado está tranquilo o revuelto en el momento de entrar. Dos variantes
del multiplicador de riesgo/recompensa (R), construidas juntas para compararlas, no para
asumir cuál es mejor:

- **Fija**: R es el mismo número para cualquier candidato.
- **Dinámica**: R escala con `probabilidad_total_si_confirma` del candidato (idea del
  usuario, 13-sept-2026) — un patrón más limpio aguanta un objetivo más lejano.

Si en el mismo día se tocan stop y objetivo (vela volátil), se asume que el stop se
ejecutó primero — supuesto conservador estándar sin datos intradía.

## Estado de la comparación fija vs dinámica (13-sept-2026, segunda vuelta) — SIN RESOLVER
Se barrieron ambas variantes en ETH (Desarrollo) y se confirmó el mejor resultado de
cada una en BTC sin retocar parámetros — misma disciplina que
`feedback_validacion_cruzada_solo_eth` (memoria persistente del usuario)
(`laboratorio/patrones/comparacion_salida_fija_vs_dinamica.py`).

**Primera vuelta** (rango de R estrecho): la dinámica ganaba por un margen mínimo en ETH
(+0.2 puntos) pero el orden se invertía al confirmar en BTC — indistinguible de ruido. El
ganador de ambas variantes caía además en el extremo superior del rango probado (ver
observación de task-observer 0008), así que ese resultado no era de fiar.

**Segunda vuelta** (rangos mucho más anchos + una métrica ajustada por riesgo, sharpe por
operación, además del retorno medio):

| métrica | ganador en ETH | mismo ganador en BTC |
|---|---|---|
| retorno medio | FIJA 18.4% | **FIJA 12.2% (gana a dinámica, 12.0%)** |
| sharpe por operación | FIJA 0.60 | **FIJA 0.66 (gana a dinámica, 0.55)** |

Con el rango ampliado, la FIJA gana con claridad en ETH y esa ventaja se confirma en BTC,
en las dos métricas — a diferencia de la primera vuelta, esto ya no parece ruido: escalar
el objetivo por `probabilidad_total_si_confirma` no mejoró el resultado en esta prueba.

**Pero el problema del borde del rango sigue sin resolverse** — y de una forma más
reveladora que solo "hace falta más rango": optimizando por retorno medio, el ganador
sigue queriendo el `dias_maximo` MÁS LARGO probado (120 días, "aguanta siempre más" —
probablemente refleja el sesgo alcista de fondo del periodo, no una salida mejor);
optimizando por sharpe por operación, el ganador se va al objetivo MÁS PEQUEÑO y al plazo
MÁS CORTO probados (k_atr_stop y R mínimos — un objetivo minúsculo reduce la dispersión
de los retornos mecánicamente, sin ser una estrategia mejor). Las dos métricas empujan a
extremos opuestos: ampliar el rango de nuevo no lo arregla, el problema es que la
desviación típica simétrica castiga la dispersión BUENA (ganar más de lo esperado) igual
que la mala — justo lo contrario de lo que se busca en una salida con objetivo lejano.
Registrado como observación 0009 de task-observer.

**No usar ninguna variante en producción todavía.** Hallazgo robusto que sí tenemos: R
fijo bate a R dependiente de la probabilidad en las dos monedas y las dos métricas
probadas — la idea de escalar el objetivo por la fuerza del patrón no se sostiene con
esta prueba. Pendiente antes de fijar los niveles concretos de R/k_atr_stop/dias_maximo:
sustituir la métrica de dispersión simétrica por una asimétrica (Sortino, o expectancy
por tasa de acierto) antes de volver a barrer.

## Dos ideas nuevas del usuario: señal de patrón contrario y cambio de régimen (13-sept-2026)
Dos formas adicionales de cerrar una operación, más allá de precio/tiempo: (1) cerrar si
aparece un candidato del patrón CONTRARIO con probabilidad suficiente (ej. cerrar un corto
de técho si surge un candidato de suelo) — cubre reversiones que confirman con forma; (2)
cerrar si el régimen deja de ser favorable durante varios días seguidos (`motores/
regimen_mercado.py`) — cubre reversiones que NO forman ningún patrón reconocible (ej. una
subida en V), el hueco que deja la señal (1) por sí sola. Implementado como dos ganchos
GENÉRICOS en `simular_trade()` (`senal_externa`, `condicion_persistente` +
`dias_persistencia`) — `salidas/` no importa `entradas/` ni `motores/` para esto, quien
llama precalcula los arrays y se los pasa, cada capa sigue sin saber de las demás.

**Primera prueba, con una cuenta de 1000€ en 2024** (`laboratorio/patrones/
prueba_cuenta_1000e.py`) — **resultado con una trampa metodológica real, detectada antes de
aceptarlo:** en la cuenta secuencial (una operación a la vez, simplificación porque
`cartera/` no existe), añadir la señal de patrón contrario parecía disparar el capital
(1010€ → 1303€ en ETH). Pero al medir el retorno POR OPERACIÓN AISLADA (mismos candidatos,
sin la restricción de solapamiento), la conclusión se invierte: la señal contraria da PEOR
retorno medio por operación (4.87% vs 7.21% de la base en ETH; 3.40% vs 4.55% en BTC). La
subida de capital de la cuenta secuencial no era la salida siendo mejor — era que al cerrar
antes se liberaba la cuenta antes y entraban muchas más operaciones (11→40), puro efecto de
capacidad (trabajo de `cartera/`, no de `salidas/`). Registrado como observación 0010 de
task-observer: "medir siempre el retorno por operación aislada además del capital
secuencial, o el efecto de capacidad se confunde con calidad de la salida."

El cambio de régimen dio un resultado más ambiguo (ETH: 5.29% vs 7.21% de la base, peor;
BTC: 4.63% vs 4.55%, prácticamente igual) — tampoco mejora claramente por ahora.

**Barrido de los dos umbrales (14-sept-2026)** —
`laboratorio/patrones/barrido_señales_salida.py`, retorno por operación aislada, población
completa de Desarrollo (547 candidatos ETH / 542 BTC, no solo 2024), ajuste en ETH,
confirmación en BTC sin retocar nada, config moderada fija (k_atr_stop=2.5, r_fijo=3.0,
dias_maximo=45) para aislar el efecto de cada señal:

- **Señal de patrón contrario — SÍ AYUDA, con el umbral correcto.** Retorno medio en ETH
  sube de 5.73% (umbral=0, cualquier candidato) a un máximo de **9.64% en umbral=0.7**
  (interior del rango, no en el borde — baja de nuevo en 0.8/0.9) frente a 8.53% de la base
  sin esta señal. Confirmado en BTC sin tocar el umbral: **7.24% con la señal vs 6.88% de la
  base** — gana, margen más modesto pero misma dirección. El primer intento (umbral=0.5,
  solo con los 79 candidatos de 2024) salía mal por un umbral demasiado laxo y una muestra
  pequeña — con el umbral correcto y la muestra completa, la señal contraria sí aporta.
  **Candidata seria para producción.**
- **Cambio de régimen — NO AYUDA, a ningún nivel probado.** Retorno medio en ETH sube con
  más días de persistencia (6.15% en 1 día → 7.96% en 15 días) pero nunca supera la base sin
  esta señal (8.53%) — el patrón es "cuanto más exigente, menos daño hace", nunca "aporta
  valor": siempre que dispara, resta. Confirmado en BTC: 5.93% con la señal vs 6.88% de la
  base — pierde también ahí. **Aparcada, no se usa en producción** tal como está diseñada
  (podría reconsiderarse combinada solo como filtro adicional, no como salida
  independiente, pero eso es una idea nueva a probar aparte).

## Intento de resolver R/k_atr_stop/dias_maximo con Sortino (14-sept-2026) — REVELÓ UN PROBLEMA MÁS GRANDE
Se sustituyó el sharpe por operación (simétrico) por un Sortino (solo penaliza la
dispersión mala, no la buena) y se amplió el rango de R hasta 20 y de días máximo hasta
260 (`laboratorio/patrones/barrido_fija_sortino.py`). El problema del "ganador en el borde"
(observación 0008) no se resolvió — reapareció igual de fuerte con las tres métricas
(retorno medio, sharpe, sortino): todas seguían queriendo el R más grande y el plazo más
largo probados, sin estabilizarse por mucho que se ampliara el rango.

Causa real, no era la métrica de riesgo: **ninguna de las tres restaba la deriva alcista de
fondo del periodo.** En una muestra mayormente alcista, "objetivo más lejano + aguantar más
tiempo" tiende asintóticamente a comprar-y-aguantar, que gana casi siempre ahí,
independientemente de si la regla de salida (ATR, patrón, etc.) aporta algo real. Corregido
midiendo el EXCESO sobre comprar/vender y aguantar el MISMO número de días que la operación
real estuvo abierta (mismo idx de entrada y de salida), en vez del retorno bruto:

| métrica (ya como exceso sobre benchmark) | ganador en ETH | mismo ganador en BTC |
|---|---|---|
| retorno medio | +0.671% | +0.248% |
| sharpe por operación | +0.416% | **+0.044% (colapsa, indistinguible de ruido)** |
| sortino por operación | +0.416% | **+0.044% (colapsa, indistinguible de ruido)** |

Con el benchmark restado, el barrido dejó de converger a los extremos del rango — pero el
exceso real es minúsculo y NO se confirma en BTC. Conclusión: **gran parte de lo que parecía
"el R/stop/plazo correcto" en los barridos anteriores (incluida la propia victoria de fija
sobre dinámica) estaba mayormente midiendo la deriva alcista del periodo, no una propiedad
real de la regla de salida.** Registrado como observación 0011 de task-observer.

**Esto no invalida los otros hallazgos de esta capa** (fija > dinámica, señal de patrón
contrario con umbral≈0.7 mejora sobre la base) porque esas comparaciones eran A vs B con el
mismo plazo/R en ambos lados, no un barrido que pudiera "ganar" alargando el plazo — pero sí
significa que fijar un nivel concreto de R/k_atr_stop/dias_maximo por retorno-bruto no tiene
sentido: casi cualquier nivel razonable, en este periodo, se parece a comprar y aguantar
tanto como a una regla de salida "inteligente". Necesario antes de fijar niveles concretos:
repetir con un periodo que incluya tramos bajistas (no solo Desarrollo si es mayormente
alcista) o aceptar una config moderada sin optimizar más finamente, ya que el margen de
mejora real por encima del benchmark parece pequeño.

## RETRACTADO: la señal de patrón contrario (umbral 0.7) NO ayuda — estaba mal medida (14-sept-2026)
La conclusión de la sección anterior ("candidata seria para producción") se basaba en
retorno medio POR OPERACIÓN AISLADA — ya corregía el problema de la observación 0010, pero
seguía siendo retorno BRUTO, no exceso sobre benchmark. La observación 0011 (misma sesión,
unas horas antes) ya había establecido que el retorno bruto mezcla la deriva del mercado con
la calidad real de la regla de salida — esa corrección se aplicó al barrido de R/plazo que la
originó, pero no se reaplicó a esta conclusión sobre la señal contraria, ya aceptada antes.

Al recalcular con la métrica correcta (exceso sobre comprar-y-aguantar el mismo número de
días que la operación estuvo abierta):

| | sin señal contraria | con señal contraria (umbral 0.7) |
|---|---|---|
| ETH | +0.151% | **-0.134%** |
| BTC | -0.048% | **-0.100%** |

**Empeora en las dos monedas.** La señal contraria no se usa en producción. Registrado como
observación 0013 de task-observer ("una corrección de métrica es retroactiva a cualquier
conclusión previa que dependiera de la misma métrica, no solo al experimento donde se
detectó"). Se probaron además dos ideas para intentar salvar esta señal, ambas sin éxito
(14-sept-2026, `laboratorio/patrones/barrido_umbral_en_ganancia.py` y
`barrido_prob_en_vivo.py`):

- **Umbral más bajo una vez la operación ya va en ganancias** (idea del usuario, tras ver un
  caso real de +17% de ganancia flotante que acabó en pérdida): efecto casi nulo, el mejor
  valor probado da un exceso de +0.003%/-0.001% (ETH/BTC) — indistinguible de ruido, y cae en
  el borde del rango probado (0.0, sin exigir ninguna calidad de patrón). No aporta nada
  medible.
- **`probabilidad_en_vivo` con `dia_transcurrido`** (esperar a que el máximo/mínimo aparente
  "sobreviva" unos días antes de decidir, en vez de la nota fija del día 0): tampoco mejora de
  forma robusta — el mejor umbral probado (0.9, borde del rango) da +0.002% en ETH pero solo
  -0.079% en BTC (frente a -0.100% de la base), una mejora marginal que no se confirma con
  solidez.

**Trailing stop (S2, Chandelier) — probado y descartado también.** Empeora el resultado en
TODOS los valores probados de `k_atr_trailing`, en las dos monedas
(`laboratorio/patrones/barrido_trailing.py`). Causa: corta casi todas las operaciones que
iban camino de un objetivo grande (algunas de +50/+70/+90%) mucho antes de tiempo — la
estrategia depende de esos pocos ganadores grandes, y un trailing clásico (sigue cada nuevo
máximo desde el minuto uno) los mata sistemáticamente. Queda como idea pendiente, no probada
todavía: un trailing que no se active hasta que la operación ya tenga un colchón mínimo de
ganancia consolidada (en vez de perseguir cada máximo desde el principio).

## Estado (14-sept-2026) — CERRADO por ahora, SIN señal de salida adicional
Código escrito (`stop_objetivo.py`: fija/dinámica + señal contraria + cambio de régimen +
trailing + probabilidad continua con doble umbral). Fija vs dinámica: gana la fija
(razonablemente sólido, A/B a igual plazo — pendiente de revisar también con exceso sobre
benchmark si se quiere más rigor, no repetido todavía). Señal de patrón contrario: NO ayuda
(retractado arriba). Cambio de régimen: no ayuda. Trailing clásico: empeora. Ninguna de las
señales adicionales probadas hasta ahora bate al benchmark de forma sólida y confirmada en
las dos monedas. R/k_atr_stop/dias_maximo: dado que el margen real de mejora por encima de
comprar-y-aguantar resultó minúsculo (observación 0011), el usuario decidió (14-sept-2026) NO
seguir optimizando finamente y aceptar la **config moderada, SIN ningún añadido, como
definitiva por ahora**:

- `k_atr_stop = 2.5`
- `r_fijo = 3.0`
- `dias_maximo = 45`
- (sin señal de patrón contrario, sin cambio de régimen, sin trailing)

Pendiente para revisar esta decisión más adelante (no bloquea seguir con el resto del
pipeline): (1) repetir el barrido de R/plazo en un periodo con tramos bajistas; (2) probar el
trailing con colchón mínimo de ganancia antes de activarse; (3) revisar fija-vs-dinámica con
exceso sobre benchmark en vez de retorno bruto, para descartar que esa conclusión tenga el
mismo problema.

## Ideas pendientes de la sesión de revisión visual del 14-sept-2026

Revisando el gráfico caso a caso, surgieron varias ideas de salida nuevas, ninguna probada
todavía formalmente (quedaron para una sesión futura, había demasiadas a la vez):

1. **Trailing con colchón mínimo de ganancia — PROBADA Y DESCARTADA (15-sept-2026).**
   Motivada por DOS casos reales, no solo uno: el largo del 19-marzo-2024 (+17% flotante →
   -1.8%) y el corto del 02-enero-2024 (entra a 2355.34, cae a 2209.72 el 03-enero -- ya
   +6.2% a favor -- nadie protege esa ganancia, el precio se da la vuelta y para el stop el
   10-enero a 2584.38, -10.08%). Hipótesis: el trailing clásico empeoraba porque reaccionaba
   a cualquier avance, por pequeño, cortando demasiado pronto operaciones que solo tenían
   ruido normal. Se añadió `cushion_pct_minimo` a `simular_trade()` (no activa el trailing
   hasta que el precio ya avanzó ese % a favor) y se barrió junto con `k_atr_trailing`
   (`laboratorio/patrones/barrido_trailing_colchon.py`), sin señal contraria ni racha (una
   idea a la vez). Resultado: **la hipótesis no se sostiene.** Con `k_atr_trailing` normal
   (0.75-2.5), el colchón no salva nada — sigue empeorando el exceso medio en ETH (peor
   config: -1.5 frente a +0.151 sin trailing) y en BTC. Ampliando el grid hasta valores muy
   laxos (`k_atr_trailing` hasta 7.0, tan ancho que casi nunca llega a activarse), el
   resultado converge monótonamente HACIA la base sin superarla nunca (ETH: 0.054 en el
   mejor caso con k=7, todavía por debajo de 0.151; BTC: -0.233, peor que -0.048) — no es un
   problema de borde del grid (regla de "no absolutos"), es que la señal nunca gana, en el
   límite se limita a converger a "no hacer nada". En agregado sobre 547/542 candidatos,
   sigue perjudicando a más operaciones (los grandes ganadores que un trailing corta antes de
   tiempo) de las que ayuda. Descartada como señal de producción. Comprobado explícitamente:
   la racha rota (punto 3 abajo) TAMPOCO resuelve el caso del 02-enero -- con N=4/M=5 sigue
   parando esa operación igual, en el stop del 10-enero a -10.08% (no hay suficientes suelos
   confirmados en esos pocos días de por medio como para que una racha llegue a romperse a
   tiempo). Este caso concreto queda sin resolver por ahora -- ningún candidato probado hasta
   hoy lo arregla sin empeorar el agregado.
2. **Combinación tiempo + distancia + velocidad de subida.** El usuario propone que la
   decisión de salir no dependa de un solo eje (ni tiempo, ni distancia al objetivo por
   separado) sino de una combinación -- por ejemplo, cuánto ha subido Y en cuántos días,
   como proxy de la fuerza del movimiento.
3. **Densidad/frecuencia de techos o suelos consecutivos como señal de tendencia — CONSTRUIDA
   Y VALIDADA (14-sept-2026), candidata real.** `laboratorio/patrones/barrido_racha_tendencia.py`:
   se cierra un largo cuando una racha de N techos consecutivos, cada uno más alto que el
   anterior y a ≤M días entre sí, se ROMPE (aparece un techo más bajo) -- y simétrico para
   cortos con suelos cada vez más bajos. 100% causal (solo compara con patrones ya confirmados
   en el pasado). Barrido de N (2-5) y M (3-15 días) en ETH, confirmado en BTC:

   | | sin racha | con racha rota (N=4, M=5) |
   |---|---|---|
   | ETH | +0.151% | **+0.319%** |
   | BTC | -0.048% | **+0.231%** |

   Mejora en las dos monedas y el ganador cae DENTRO del rango probado, no en el borde -- la
   primera señal del 14-sept-2026 que se sostiene así. Verificado con dos casos reales: el
   largo del 19-marzo-2024 (que se comía un +17% hasta perder -1.8%) se cierra con esta señal
   en +13.67% el 25-marzo; el corto del 11-enero-2024 (que perdía -11.91% aguantando hasta el
   19-febrero) se cierra en +12.54% el 4-febrero. **Bug encontrado y corregido en el camino:**
   la primera versión usaba el mismo criterio "cada vez más alto" para techos Y para suelos --
   para un corto hay que vigilar lo contrario (suelos cada vez más BAJOS, romperse con uno más
   alto), no lo mismo que para un largo. Con el bug sin corregir, un corto casi nunca se
   protegía de verdad en una subida fuerte (la "racha de suelos subiendo" que detectaba en
   realidad es señal de tendencia ALCISTA, útil para proteger un LARGO, no un corto). Corregido
   con un parámetro `direccion_favorable` explícito en `_racha_rota()`.

   El propio usuario señaló que esto es conceptualmente un **filtro de contexto** (`filtros/`),
   no un motor nuevo -- interpreta la secuencia de patrones ya detectados, no detecta un patrón
   nuevo. Pendiente antes de llevarlo a producción: (a) probar sobre TODO el histórico en una
   cuenta secuencial completa, no solo candidatos aislados (aviso: en la prueba de una cuenta
   de 2024 concreta salió peor que sin la señal -- 947€ vs 1015€ -- por ser una muestra
   pequeña de solo 17 operaciones, no porque la señal esté mal; la mejora real se mide sobre
   los 547/542 candidatos, no sobre un año suelto); (b) verificar que no hay sobreajuste por
   haber barrido 20 combinaciones de N/M.
4. **Confirmado con datos: "techo de alta probabilidad" no significa "pico más alto
   visualmente"** -- significa "buen momento para apostar contra la tendencia dado el
   contexto". El régimen alcista descuenta los techos a propósito; en 2024 (ETH) el único
   tramo BAJISTA fue 7-sept a 8-nov, y ahí es exactamente donde se agrupan los techos de alta
   probabilidad del año. No es un fallo, es el diseño -- pero rompe la intuición visual de
   "el pico más grande debería ser el techo más fiable", y vale la pena documentarlo para que
   no se repita la confusión en el futuro.

También pendiente de la sesión: **tamaño de posición** en las pruebas de cruce de patrones
(hoy usadas al 100% del capital sin control de riesgo -- el usuario decidió explícitamente
aparcar esto por ahora, "no hace falta reclamar el tamaño de la posición, eso nos da igual al
principio, estamos ajustando").
