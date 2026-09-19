---
name: deteccion-flexible-patrones
description: >
  Metodología para construir un detector de patrones de precio (canal,
  bandera, martillo, cabeza-hombros, etc.) en corvus4 con probabilidad
  continua en vez de reglas estrictas sí/no. Usar cuando el usuario pida
  "hacer flexible" un patrón, meter probabilidades a un patrón nuevo, o
  crear un motor de detección para bandera/martillo/canal siguiendo el
  mismo enfoque que se validó con doble suelo el 10-sept-2026. También
  aplica si el usuario menciona "consenso de configuraciones", "que sea
  dinámico, no un número fijo", o pide evitar umbrales estrictos.
---

# Detección flexible de patrones — metodología validada en corvus4

Desarrollada y validada el 10-sept-2026 sobre doble suelo
(`laboratorio/patrones/doble_suelo_flexible.py`,
`laboratorio/patrones/doble_suelo_consenso.py`). Antes de aplicarla a un
patrón nuevo (bandera, martillo, cabeza-hombros...), lee esos dos ficheros
como referencia de implementación real, no solo esta descripción.

## Principio rector, del propio usuario

"Estamos jugando con absolutos" — el usuario rechaza explícitamente
cualquier regla binaria (es/no es patrón) y cualquier número fijo elegido
a mano (un umbral, un peso, una tolerancia). La alternativa no es "una
fórmula con números distintos" — es **probar muchas configuraciones
distintas a la vez y quedarse con el consenso**, dejando que la propia
distribución de resultados hable.

**"Apretar" un parámetro no significa fijarlo a un valor más estricto.**
Significa desplazar hacia arriba (o abajo) el RANGO de valores que se
prueban en el conjunto — de `[0.4, 0.5, 0.55, 0.65, 0.7]` a
`[0.6, 0.7, 0.75, 0.8, 0.9]`, por ejemplo — pero siempre varios valores
compitiendo, nunca uno solo. Un corte duro (`if x < umbral: descartar`)
está PROHIBIDO como mecanismo de calidad: se probó explícitamente
(`altura_minima_pct` como filtro binario) y **empeoró** los resultados,
porque cambia qué candidatos entran en la comparación, no solo su nota —
ver la lección completa más abajo.

## Los pasos, en orden

1. **Detección causal de los puntos base** (mínimos/máximos locales,
   fondos, etc.) — nunca mirar al futuro más allá del margen de
   confirmación estrictamente necesario. Reutilizar
   `_detectar_fondos_simple()` como base si aplica.

2. **Función de puntuación con varias dimensiones continuas**, cada una
   0-1, cada una con su propio "ideal" de saturación (no un umbral duro):
   nivel/parecido, tamaño del rebote intermedio, tamaño GRANDE del patrón
   (dimensión separada del anterior, con un ideal más alto — mide "es
   grande" en vez de "hay algo"), tiempo, y **volumen en la confirmación**
   (pieza que resultó ser la más determinante — ver lección 2).

3. **Conjunto de MUCHAS configuraciones (grid), variando también los
   PESOS internos, no solo las tolerancias.** Si todas las configs
   comparten los mismos pesos, tienden a coincidir aunque cambien las
   tolerancias, y el consenso no discrimina nada — este fue el primer
   fallo real encontrado (ver lección 1).

4. **Agregación: probabilidad = promedio de todas las configs que
   encontraron algún candidato**, penalizada por ambigüedad
   (`probabilidad / (1 + n_parejas_alternativas_decentes)`) — no contar
   cuántas configs superan un umbral fijo (eso reintroduce un corte duro
   por la puerta de atrás).

5. **Comprobación de cordura obligatoria antes de dar nada por bueno:**
   si ya existe una versión ESTRICTA validada del mismo patrón en el
   proyecto (ej. `doble_suelo.py`), comprobar que sus señales conocidas
   caen en un percentil ALTO de la distribución del detector flexible. Si
   no es así, al flexible le falta una pieza real que el estricto sí
   captura — no asumir que el flexible ya está bien solo porque "parece
   razonable".

6. **Confirmación posterior (Etapa 2), no solo la forma inicial.** Añadir
   un chequeo de qué pasa DESPUÉS del patrón detectado (ej. rotura de la
   línea de cuello/resistencia en N días) casi siempre aporta más que
   seguir refinando la puntuación de la Etapa 1 — en doble suelo, esto
   solo, aisladamente, duplicó la tasa de acierto (30-40% → 54-62%).

7. **Validación cruzada obligatoria, dos cortes:** ajustar SOLO con una
   moneda (ETH), congelar los parámetros, confirmar SIN TOCAR NADA en la
   otra (BTC). Y ajustar SOLO con un tramo temporal, confirmar en el
   tramo posterior. Sin esto, cualquier resultado bueno puede ser
   sobreajuste, no señal real.

## Lecciones concretas ya aprendidas (no repetir el error)

1. **Pesos compartidos entre configs = falso consenso.** Variar solo
   tolerancias con los mismos pesos produjo que el 90%+ de los candidatos
   cayeran en el bucket más alto de "consenso" — sin discriminar nada.
   Hubo que variar también los pesos internos entre configs.

2. **El volumen en la confirmación fue la pieza que más aportó**, de
   lejos — más que ajustar tolerancias de nivel o de tiempo. Si el patrón
   nuevo tiene un equivalente conocido en el detector estricto (ej.
   "rotura con volumen"), replicarlo como dimensión continua desde el
   principio, no como añadido tardío.

3. **Un corte duro de calidad (ej. "altura mínima 15% o se descarta")
   EMPEORA el consenso**, no lo mejora — aunque intuitivamente parezca lo
   correcto. Motivo: cambia la población de candidatos que se está
   comparando (los configs estrictos rechazan a los débiles en vez de
   puntuarlos bajo), lo que sube la media general y comprime la
   diferencia relativa entre buenos y mediocres. La misma idea aplicada
   como dimensión CONTINUA con su propio peso sí funcionó.

4. **Vigilar el solapamiento de ventanas al medir significancia.** Si el
   horizonte de "éxito" se mide vela a vela con ventanas que se solapan
   (ej. retorno a 20 días calculado en cada vela), el tamaño de muestra
   aparente está muy inflado frente al real (independiente). Usar tramos
   NO solapados para cualquier test de significancia, o al menos
   verificarlo antes de confiar en un p-valor bajo.

5. **Escalar las ventanas temporales en DÍAS REALES, no en velas**, al
   portar un detector entre timeframes (15m/1h/4h/1d) — un parámetro
   "ventana=20" son 20 días en velas diarias pero 20 velas (3h20) en 15m
   si no se convierte explícitamente con las velas-por-día de cada
   timeframe.

6. **Comparar siempre contra el baseline correcto.** "Comprar tras una
   caída fuerte" pareció bueno hasta compararlo con "comprar cualquier
   día al azar" en el mismo periodo — en mercados con tendencia alcista
   fuerte, el baseline ingenuo ya es alto, y hay que superarlO, no solo
   superar el azar puro.

7. **Persistir SIEMPRE el script de validación/comparación como fichero,
   nunca dejarlo "al vuelo".** Al revisar doble suelo y doble techo el
   10-sept-2026 se encontró que la función de agregación
   (`probabilidad_media_por_*`) sí se había guardado para techo pero no
   para suelo, y que el método exacto de EMPAREJAR cada señal del
   detector estricto (que dispara el día de la ROTURA) con su candidato
   flexible correspondiente (indexado por el día del fondo2/techo2, no
   el de la rotura) nunca se guardó en ningún fichero — solo existió en
   código ad-hoc de una respuesta anterior. Consecuencia real: al corregir
   varios cortes duros y ampliar el grid, hubo que RECONSTRUIR ese
   emparejamiento desde cero, y el percentil de cordura cambió (81/67 →
   ~59/~59) sin poder saber cuánto del cambio era el bug corregido y
   cuánto era una diferencia del método reconstruido. Un resultado solo
   es reproducible si el código que lo produjo existe en el repositorio,
   no en el historial de la conversación. Ver
   `laboratorio/patrones/validacion_confirmacion.py` como plantilla a
   reutilizar para bandera/martillo.

   **Resuelto el 10-sept-2026:** el propio emparejamiento de cordura tenía
   dos números fijos elegidos a mano (ventana de 20 días, quedarse solo con
   el candidato más cercano) — la misma clase de "absoluto" que la lección
   3 prohíbe para la puntuación. Se sustituyó por un rango de ventanas
   (`VENTANAS_CORDURA_DIAS = [10,15,20,25,30]`) promediando TODOS los
   candidatos de cada ventana, y se reporta un percentil medio + rango en
   vez de un número único. Con esto, doble techo quedó confirmado como
   estable por TRES métodos distintos en tres momentos (~68/70 original,
   ~73/71 reconstrucción ad-hoc, ~69/71 dinámico) — cerrado con confianza
   alta. Doble suelo, en cambio, bajó de forma consistente en los dos
   métodos posteriores al bugfix (~59/59 y ~57/58, ambos muy por debajo
   del ~81/67 original) — ya no es artefacto de reconstrucción, es un
   efecto real de los pesos nuevos (volumen+altura dominantes): esos pesos
   ganan la confirmación de ruptura (etapa 2) pero discriminan peor la
   cordura (etapa de puntuación inicial). Son dos chequeos distintos y
   pueden dar lecturas distintas del mismo cambio — no asumir que "mejoró
   una métrica" implica "mejoró la otra".

8. **Medir el retorno desde el día REAL de confirmación, no desde el día
   del patrón.** En la Etapa 2 (confirmación de ruptura, lección 6/paso 6),
   la confirmación puede tardar hasta `DIAS_CONFIRMACION` días en llegar
   tras el fondo2/techo2. Medir el retorno de éxito desde el día del
   patrón (en vez de desde el día en que la ruptura realmente se confirma)
   cuenta como "resultado de la señal" un movimiento de precio que ya
   había ocurrido ANTES de que la señal estuviera confirmada — inflando
   el acierto aparente sin que sea un error visible a simple vista.
   Detectado el 10-sept-2026: con este bug, doble suelo/techo ETH parecían
   tener 68-81% de acierto "con confirmación"; corregido (medir desde
   `idx_confirmacion`, no desde `idx_fondo2/idx_techo2`) y confirmado con
   validación cruzada rigurosa (paso 7, ETH→tiempo y ETH→BTC) más Monte
   Carlo (5000 simulaciones, tramos no solapados), el acierto real cae a
   20-41%, indistinguible del azar (p=0.37-0.99 probando TODO un rango de
   umbrales de éxito, no solo uno). Ver
   `laboratorio/patrones/validacion_cruzada_pesos.py` y
   `laboratorio/patrones/monte_carlo_confirmacion.py`. **Esto no invalida
   el motor base** (la detección de la forma sigue limpia y pasa las
   puertas de causalidad/presupuesto/recursividad de `tests/`) — invalida
   solo el filtro concreto de confirmación binaria tal como estaba medido.

9. **El umbral de "éxito" en una prueba de validación es tan "absoluto"
   como un umbral de detección — aplica la misma regla del principio
   rector.** Corrección del usuario el 10-sept-2026: se había usado
   `UMBRAL_EXITO_PCT = 5.0` fijo (un solo número elegido a mano) para
   decidir si una operación "acertó". Aunque no afecta a qué candidatos
   detecta el patrón, sigue siendo un absoluto disfrazado: cambia si el
   umbral elegido, por casualidad, favorece o perjudica el resultado.
   Sustituido por `UMBRALES_EXITO_PCT = [2, 3, 5, 7, 10]`, reportando
   rango/media de aciertos y de p-valores en vez de un número único —
   igual que se hizo con la ventana de cordura (lección 7). Cualquier
   prueba de validación futura (de este patrón o de uno nuevo) debe medir
   "éxito" así: un rango de umbrales, nunca uno solo. La métrica de
   retorno medio (sin umbral) es el complemento ideal porque no depende
   de ningún corte en absoluto.

## Qué NO hacer

- No declarar un patrón "confirmado" con una sola prueba de correlación
  sin comprobar el solapamiento de ventanas.
- No usar el mismo peso/tolerancia en todas las configuraciones del
  conjunto — mata la capacidad de discriminar.
- No añadir un requisito mínimo como filtro binario — convertirlo siempre
  en una dimensión de puntuación continua con su propio peso.
- No dar un resultado como definitivo sin la validación cruzada de
  moneda Y de tiempo.
- No abandonar una idea por un resultado flojo sin agotar variantes
  razonables antes (ver `feedback_no_abandonar_ante_resultado_negativo`
  en la memoria persistente del usuario).
- No medir el retorno de una señal "con confirmación" desde el día del
  patrón — medirlo desde el día real en que la confirmación ocurre.
- No usar un solo umbral fijo de "éxito" (ej. "sube 5%") en ninguna
  prueba de validación — usar un rango de umbrales y reportar el rango
  de resultados, igual que con cualquier otro absoluto.
