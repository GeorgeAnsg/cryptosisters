# Metodología de validación cuantitativa: cómo no engañarte a ti mismo

> Documento de investigación para CORVUS. Objetivo: llevar el rigor de validación más allá de las 4 puertas actuales (causalidad, paridad backtest-vivo, costes x2, Deflated Sharpe Ratio), explicando cada concepto primero en lenguaje llano y después con precisión técnica, con las fuentes originales (papers, SSRN, arXiv, documentación) para poder profundizar cuando haga falta.

---

## Índice

1. Sobreajuste y validación (DSR, PBO, walk-forward, purged CV, CPCV, multiple testing)
2. Tests estadísticos: ¿esto es mejor que el azar?
3. Etiquetado y Machine Learning (López de Prado)
4. Regímenes de mercado
5. Tamaño de posición y riesgo
6. Costes y ejecución real
7. Métricas: cuáles importan y cuáles engañan
8. Proceso: el cuaderno de laboratorio
9. Errores clásicos que arruinan un backtest
10. **Protocolo de validación paso a paso** (checklist final)

---

## 0. Por qué hace falta ir más allá de las 4 puertas

Las 4 puertas que ya usas (causalidad, paridad, costes x2, DSR) son un filtro excelente pero incompleto. Cada una responde a una pregunta distinta, y hay preguntas que se quedan sin responder:

- Causalidad te protege de "tu bot ve el futuro sin querer".
- Paridad backtest-vivo te protege de "tu simulador miente sobre cómo se ejecutaría de verdad".
- Costes x2 te protege de "ganas dinero solo porque asumiste fricción cero".
- DSR te protege de "ganaste porque probaste 200 variantes y una salió bien por azar".

Lo que falta y este documento cubre: **cuántos años de datos necesitas para el número de cosas que probaste, cómo saber si el resultado es mejor que el puro azar con un test estadístico independiente del DSR, cómo etiquetar y validar si metes Machine Learning sin hacer trampas sin darte cuenta, cómo dimensionar la apuesta sin arruinarte aunque el edge sea real, cómo modelar el coste de una plataforma "gratis" como Quantfury, y una lista de errores concretos (no abstractos) que hunden backtests de gente que creía estar haciéndolo bien.**

---

## 1. Sobreajuste y validación

### 1.1 La idea en una frase

Si le pides a 1.000 personas que adivinen 20 lanzamientos de moneda seguidos, unas cuantas acertarán casi todos por pura suerte. Si luego solo te fijas en la que más acertó y dices "qué buena prediciendo monedas es esta persona", te estás engañando: no la elegiste por su habilidad, la elegiste **porque era la mejor de 1.000**, y entre 1.000 siempre hay alguna que parece un genio sin serlo.

Esto es exactamente lo que pasa cuando pruebas 50, 200 o 2.000 combinaciones de parámetros en un backtest y te quedas con la mejor: **el número de intentos infla la métrica de la ganadora**, aunque el proceso subyacente no tenga ningún valor predictivo real. Todo este capítulo trata de una sola cosa: **medir y corregir esa inflación**.

### 1.2 Deflated Sharpe Ratio (DSR) — Bailey y López de Prado (2014)

**Analogía**: es como ajustar la nota de un examen sabiendo que el alumno tuvo 200 intentos y solo te enseña el mejor. El DSR "descuenta" el Sharpe observado por el número de intentos, la varianza entre esos intentos, y la forma de la distribución de los retornos (asimetría y curtosis), y te devuelve la probabilidad de que el Sharpe real (no el de casualidad) sea positivo.

**Fórmula técnica.** El DSR se construye en dos pasos.

Paso 1 — Sharpe Ratio Probabilístico (PSR), que ya usas parcialmente:

```
PSR(SR*) = Φ( (SR̂ − SR*) · √(T−1) / √(1 − γ₃·SR̂ + (γ₄−1)/4 · SR̂²) )
```

donde `SR̂` es el Sharpe observado, `SR*` es el Sharpe de referencia contra el que comparas, `T` es el número de observaciones (barras/periodos, no operaciones), `γ₃` la asimetría (skewness) y `γ₄` la curtosis de los retornos, y `Φ` la función de distribución normal acumulada.

Paso 2 — en vez de usar `SR* = 0`, el DSR usa como referencia el **Sharpe máximo esperado bajo la hipótesis nula de que ninguna de las N variantes probadas tiene edge real**:

```
E[max{SR_k}] ≈ √Var[{SR_k}] · [ (1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) ]
```

donde `N` es el número de configuraciones independientes probadas, `Var[{SR_k}]` es la varianza de los Sharpes obtenidos entre esas configuraciones, `γ ≈ 0,5772` es la constante de Euler-Mascheroni, `e` el número de Euler, y `Φ⁻¹` la inversa de la normal estándar.

**Dato que hay que interiorizar**: con `N=1.000` backtests independientes y varianza típica, el Sharpe máximo esperado **por pura casualidad, con edge real = 0, es de aproximadamente 3,26**. Es decir: si pruebas 1.000 variantes de tu estrategia y la mejor tiene un Sharpe de 3, eso **no dice nada todavía** — es exactamente lo que cabría esperar del ruido puro.

**Qué hay que registrar para poder calcular el DSR** (esto es una lista de obligaciones de tu cuaderno de laboratorio, ver sección 8):
- El número total de configuraciones/variantes probadas, N (no solo la ganadora).
- El Sharpe de cada una de esas N configuraciones (para calcular la varianza entre trials).
- El número de observaciones T (barras) del backtest.
- Asimetría y curtosis de la serie de retornos de la estrategia final.

Fuentes: Bailey & López de Prado (2014), *"The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality"*, Journal of Portfolio Management 40(5), SSRN 2460551 — PDF: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf · https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551 · resumen en https://en.wikipedia.org/wiki/Deflated_Sharpe_ratio

### 1.3 Probability of Backtest Overfitting (PBO) y CSCV

**Analogía**: imagina que divides tu historial de datos en 8 trozos. Coges la mitad de los trozos para "entrenar" (elegir la mejor configuración) y la otra mitad para "comprobar". Si repites esto con todas las combinaciones posibles de qué mitad usas para entrenar y cuál para comprobar, y casi siempre la configuración que ganó en el entrenamiento queda **por debajo de la mediana** en la comprobación, eso es la prueba directa de que estás sobreajustando: la estrategia solo "brilla" en el trozo de datos que usaste para elegirla.

**Definición técnica**: el PBO es la probabilidad de que la configuración con mejor rendimiento in-sample (dentro de la muestra usada para optimizar) tenga un rendimiento por debajo de la mediana out-of-sample (fuera de esa muestra). Se calcula con **Combinatorially Symmetric Cross-Validation (CSCV)**: se parte la serie temporal en S bloques iguales, se forman todas las combinaciones de la mitad de bloques como "in-sample" (IS) y la otra mitad como "out-of-sample" (OOS), se identifica en cada combinación la configuración ganadora en IS, se mide su rango relativo en OOS, se transforma ese rango en un logit, y el PBO es la proporción de combinaciones donde ese logit es negativo (es decir, el ganador en IS quedó peor que la mediana en OOS).

Un resultado clave del paper: **bajo CSCV, el PBO tiende a 1 a medida que N (el número de configuraciones probadas) crece, incluso si alguna configuración individual tuviera de verdad poder predictivo** — otra forma de decir que probar muchas variantes casi garantiza encontrar una que parece buena por azar.

Fuentes: Bailey, Borwein, López de Prado & Zhu, *"The Probability of Backtest Overfitting"*, Journal of Computational Finance (2015) — PDF: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf · repositorio con implementación en R/Python: https://github.com/mrbcuda/pbo · paquete R: https://cran.r-project.org/web/packages/pbo/readme/README.html

### 1.4 Longitud mínima de backtest (MinBTL)

**La idea**: cuantas más configuraciones pruebas, más años de historia necesitas para que un Sharpe alto en la muestra no sea pura casualidad. Bailey, Borwein, López de Prado y Zhu proponen una cota superior aproximada:

```
MinBTL ≈ 2·ln(N) / E[max SR_k]²
```

(medido en años), donde N es de nuevo el número de configuraciones independientes probadas. El ejemplo citado en el propio trabajo: **con solo 5 años de datos, no deberías probar más de unas 45 configuraciones independientes** si no quieres acabar casi garantizado con una estrategia con Sharpe in-sample de 1 pero Sharpe esperado out-of-sample de cero. Con tu histórico de BTC (varios años, pero limitado), esto es un límite práctico y muy concreto al número de variantes/parámetros que te puedes permitir explorar sin pedir más historia o sin agrupar pruebas en familias no independientes.

Fuente: mismo paper que 1.3, sección de aplicaciones — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253 y herramienta online de demostración: https://www.davidhbailey.com/dhbpapers/overfit-tools.pdf

### 1.5 Walk-forward: anclado vs. rodante

**Analogía**: es como estudiar para un examen re-haciendo exámenes de años anteriores en orden cronológico, sin mirar nunca el examen del año que todavía no has "vivido". El walk-forward *anclado* siempre empieza a estudiar desde el primer año disponible (la ventana de entrenamiento crece); el walk-forward *rodante* solo estudia con los últimos X años (la ventana se desplaza y "olvida" lo más viejo).

- **Anclado**: el inicio de la ventana de entrenamiento queda fijo en el origen de los datos; cada paso añade más historia. Favorece estrategias que dependen de patrones lentos y persistentes, y usa el máximo de historia disponible en cada paso.
- **Rodante**: la ventana de entrenamiento tiene tamaño fijo (p.ej. 2 años) y se desplaza hacia delante, descartando los datos más antiguos. Se adapta más rápido a condiciones de mercado recientes; más apropiado para modelos intradía o mercados que cambian de régimen con frecuencia (como cripto).

Ninguno es "mejor" de forma absoluta — de hecho, correr ambos y comparar cuánto se degrada el resultado entre uno y otro es en sí mismo informativo sobre qué tan rápido "caduca" tu edge.

Fuente: https://www.susanpotter.net/quant/walk-forward-optimization/ · https://en.wikipedia.org/wiki/Walk_forward_optimization

### 1.6 Purged K-Fold con embargo

**El problema, en llano**: el k-fold clásico de Machine Learning baraja los datos al azar y asume que cada fila es independiente de las demás. En series temporales eso es falso: si etiquetas "sube en las próximas 4 horas", esa etiqueta se solapa con la información de las 3-4 barras siguientes. Si por azar una de esas barras cae en "entrenamiento" y la barra etiquetada cae en "test", tu modelo ha visto, indirectamente, parte del futuro que se supone debía predecir. El resultado es un backtest que **parece** funcionar de maravilla y luego se hunde en producción.

**Solución técnica — purga + embargo**:
- **Purga (purging)**: se elimina de entrenamiento cualquier observación cuya ventana de etiqueta se solape en el tiempo con alguna observación del bloque de test. Ejemplo concreto: si el bloque de test cubre las barras 120–150 y tu etiqueta mira 30 barras hacia delante, se purgan del entrenamiento todas las observaciones entre la barra 90 y la 150 (porque su etiqueta "toca" el rango de test).
- **Embargo**: incluso purgando, puede quedar fuga de información por la autocorrelación serial justo después del bloque de test. El embargo añade un colchón adicional de barras excluidas de entrenamiento inmediatamente después del bloque de test.

Fuentes: capítulo 7 de *Advances in Financial Machine Learning* (López de Prado, Wiley) — resumen técnico: https://en.wikipedia.org/wiki/Purged_cross-validation · explicación paso a paso con ejemplos numéricos: https://quantmemo.com/concepts/purged-embargoed-cv · https://blog.quantinsti.com/cross-validation-embargo-purging-combinatorial/

### 1.7 Combinatorial Purged Cross-Validation (CPCV)

**La idea**: en vez de hacer un único backtest walk-forward (que te da **un solo número** de rendimiento fuera de muestra), la CPCV divide la serie en N grupos secuenciales y prueba **todas las combinaciones posibles** de qué grupos usar como test (purgando y con embargo en cada combinación), generando así toda una **distribución** de resultados out-of-sample en vez de un único punto.

**Fórmula del número de combinaciones**: con N grupos totales y k grupos usados como test en cada partición, el número de combinaciones es el coeficiente binomial:

```
C(N,k) = N! / (k!·(N−k)!)
```

Por ejemplo, con 10 grupos y 2 usados como test en cada combinación, `C(10,2) = 45` particiones distintas, que a su vez se pueden recombinar en varias "trayectorias" (paths) completas de backtest fuera de muestra — el propio López de Prado describe en su libro un ejemplo con 6 grupos y k=2 que produce 15 combinaciones y 5 trayectorias completas.

**Por qué importa**: un solo walk-forward te dice "en esta única secuencia histórica, el resultado fue X". La CPCV te dice "en decenas de particiones distintas y válidas de la misma historia, la distribución de resultados fue esto" — lo que te permite calcular, directamente, tanto el PBO como el DSR sobre resultados reales y no sobre un solo escenario. Estudios comparativos muestran que las estrategias validadas con CPCV tienen menor PBO y mejor DSR que las validadas solo con walk-forward simple.

Fuentes: capítulo 12 de *Advances in Financial Machine Learning* · explicación con código: https://www.quantbeckman.com/p/with-code-combinatorial-purged-cross · https://quantoisseur.com/2019/11/05/combinatorial-purged-cross-validation-explained/ · comparación empírica de métodos out-of-sample: https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110

### 1.8 El ajuste "multiple testing" de Harvey, Liu y Zhu

**La idea en llano**: en física de partículas, para declarar un descubrimiento hace falta un nivel de confianza de "5 sigma" precisamente porque se hacen miles de comparaciones y hay que protegerse de falsos positivos. En finanzas ha pasado lo contrario durante décadas: se aceptaba como "significativo" cualquier hallazgo con un t-estadístico > 1,96 (95% de confianza para un único test), sin tener en cuenta que, en agregado, la profesión ha probado **cientos de factores** sobre los mismos datos históricos de mercado.

**El hallazgo concreto**: Harvey, Liu y Zhu documentan que, hacia 2016, se habían probado al menos **316 "factores"** distintos para explicar los retornos de las acciones. Dado ese historial acumulado de intentos, un nuevo factor necesita superar un listón mucho más alto: **t-estadístico > 3,0** (no 1,96) para considerarse genuinamente significativo. Además, publican un marco (Harvey & Liu, 2015, *"Backtesting"*) que convierte el Sharpe Ratio de una estrategia en un t-ratio, y aplica un "recorte" (haircut) a ese Sharpe en función del número de pruebas previas asumidas — cuantas más pruebas asumas que se han hecho (en tu propio proyecto o en la literatura), mayor es el recorte necesario para que el resultado siga siendo creíble.

En su discurso presidencial de 2017 ante la American Finance Association (*"The Scientific Outlook in Financial Economics"*), Harvey fue más allá: advirtió que la combinación de tests no reportados, falta de corrección por tests múltiples, y p-hacking directo e indirecto significa que **muchos resultados publicados en economía financiera no se van a sostener en el futuro**, y propuso alternativas como el "mínimo factor de Bayes" en vez de depender solo del p-valor.

**Aplicación práctica para ti**: cada vez que pruebas una variante de tu estrategia (un umbral distinto, un indicador nuevo, un filtro adicional) es un "test" en este sentido. El listón de "esto es de verdad bueno" tiene que subir con el número acumulado de variantes que hayas probado **a lo largo de toda la vida del proyecto**, no solo en la sesión de hoy.

Fuentes: Harvey, Liu & Zhu, *"… and the Cross-Section of Expected Returns"*, Review of Financial Studies 29(1), 2016 — https://academic.oup.com/rfs/article-abstract/29/1/5/1843824 · NBER working paper: https://www.nber.org/system/files/working_papers/w20592/w20592.pdf · Harvey & Liu (2015) *"Backtesting"*, SSRN 2345489: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2345489 · Harvey (2017) *"Presidential Address: The Scientific Outlook in Financial Economics"*, Journal of Finance 72(4): https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12530 · Harvey (2020) *"False (and Missed) Discoveries in Financial Economics"*, Journal of Finance: https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12951

---

## 2. Tests estadísticos: ¿esto es mejor que el azar?

### 2.1 White's Reality Check (1997/2000) y el estudio de Sullivan, Timmermann y White

**Analogía**: si dejas que 1.000 "expertos" opinen sobre si el mercado sube o baja mañana y te fijas solo en el que más veces acertó, ese "mejor experto" no demuestra nada por sí solo — hace falta comparar su acierto contra la distribución de acierto que *cualquier grupo de 1.000 opinantes al azar* habría producido.

**Qué hace el test**: la Reality Check de White evalúa si la **mejor** regla de un universo grande de reglas de trading (p.ej. 26 reglas de medias móviles distintas, aplicadas a 100 años de datos del Dow Jones en el estudio original de Sullivan-Timmermann-White) tiene de verdad una capacidad predictiva superior a un benchmark, **una vez descontado el efecto de haber buscado entre muchas reglas**. Se implementa con bootstrap: se remuestrea la serie de retornos de todas las reglas simultáneamente (preservando su correlación), se recalcula cuál sería la "mejor regla" en cada remuestreo, y se compara la distribución resultante contra el resultado observado de la mejor regla real. Si el resultado real está muy por encima de esa distribución simulada, hay evidencia de que no es pura casualidad.

**Limitación**: es un test conservador — su distribución nula se construye bajo la "configuración menos favorable" (asumiendo que todas las reglas son igual de malas), lo que le hace perder poder estadístico cuando el universo de reglas incluye muchas reglas claramente malas mezcladas con alguna buena.

Fuentes: Sullivan, Timmermann & White (1999), *"Data-Snooping, Technical Trading Rule Performance, and the Bootstrap"*, Journal of Finance 54(5): https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00163 · PDF: https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf

### 2.2 Hansen's Superior Predictive Ability (SPA) test

Hansen (2005) mejora la Reality Check evitando precisamente esa "configuración menos favorable": el test SPA da más peso a las reglas que de verdad compiten por ser las mejores y penaliza menos por incluir reglas obviamente malas en el universo probado, ganando poder estadístico sin perder el control de falsos positivos. Es, en la práctica, la versión recomendada hoy en día cuando tienes un conjunto grande y heterogéneo de variantes (algunas buenas, muchas mediocres) y quieres saber si la mejor es genuinamente mejor que el benchmark, ajustando por el hecho de haber buscado entre todas ellas.

Fuente: Hansen (2005), *"A Test for Superior Predictive Ability"* — resumen y aplicaciones: https://www.researchgate.net/publication/4724332_A_Test_for_Superior_Predictive_Ability · aplicación a reglas técnicas: https://homepage.ntu.edu.tw/~ckuan/pdf/Step-SPA-20090720.pdf

### 2.3 Test de permutación Monte Carlo

**Analogía**: coges la cinta de precios real, la cortas en trocitos y la barajas al azar (de forma que las medias, la volatilidad y otras propiedades estadísticas básicas se mantienen, pero cualquier tendencia o autocorrelación real desaparece). Si tu estrategia sigue "funcionando" sobre esa cinta barajada tan bien como sobre la real, es que tu estrategia no está capturando ninguna estructura genuina del mercado — está sobreajustada al ruido específico de esa serie.

**Cómo se implementa conceptualmente**:
1. Corre tu backtest completo sobre los datos reales y guarda la métrica de interés (Sharpe, retorno total, lo que sea).
2. Baraja/permuta la serie de retornos (o los residuos, o el orden temporal según la variante) de forma que se destruya la estructura temporal pero se preserven propiedades estadísticas básicas.
3. Re-ejecuta la **misma lógica de la estrategia** (esto es clave: no solo mezclar los trades ya generados, sino volver a generar las señales sobre la serie barajada) y guarda la métrica.
4. Repite 1.000-10.000 veces.
5. El p-valor es la fracción de las series barajadas en las que la estrategia (re-ejecutada desde cero) iguala o supera el resultado real. Si de 1.000 permutaciones tu resultado real solo es superado por 10, tu p-valor es 0,01.

**Distinción importante**: esto es más fuerte que "barajar los trades" porque vuelve a correr la lógica de decisión sobre datos sintéticos que nunca tuvieron ninguna estructura predecible — responde literalmente a la pregunta "¿mi estrategia habría parecido igual de buena sobre datos sin ningún edge real?". Debe combinarse con walk-forward y con un backtest libre de sesgos (no sustituye a las puertas de causalidad/paridad, las complementa).

Fuentes: explicación práctica y código: https://www.buildalpha.com/monte-carlo-permutation/ · https://www.susanpotter.net/quant/monte-carlo-permutation-tests-strategy-significance/ · ejemplo aplicado con ROC/momentum: https://medium.com/@NFS303/validating-trading-strategies-with-permuted-monte-carlo-a-practical-guide-using-roc-momentum-d083180d4213

### 2.4 Bootstrap estacionario de bloques (Politis & Romano, 1994)

**El problema**: el bootstrap clásico remuestrea observaciones individuales asumiendo que son independientes entre sí. Los retornos financieros no lo son (hay autocorrelación, rachas de volatilidad, etc.) — remuestrear observación a observación destruiría esa dependencia y te daría intervalos de confianza artificialmente estrechos (falsa sensación de precisión).

**Solución**: el bootstrap estacionario remuestrea **bloques** de observaciones consecutivas, con una longitud de bloque **aleatoria** (siguiendo una distribución geométrica), en vez de bloques de tamaño fijo. Esto preserva la dependencia de corto plazo dentro de cada bloque mientras genera una pseudo-serie que sigue siendo estacionaria en su conjunto. Es el método recomendado por defecto para calcular errores estándar o intervalos de confianza de estadísticos (media, Sharpe, drawdown máximo) sobre una serie temporal financiera con autocorrelación no trivial.

**Cuándo usar cada test**:
- ¿Mi única estrategia es mejor que el azar? → **Test de permutación Monte Carlo**.
- ¿La mejor de mi conjunto de variantes probadas es mejor que un benchmark, descontando que probé muchas? → **White's Reality Check** o, mejor, **Hansen SPA**.
- ¿Qué tan preciso es mi Sharpe/drawdown estimado, dado que los retornos están autocorrelacionados? → **Bootstrap estacionario de bloques** para el intervalo de confianza.
- ¿Mi Sharpe sobrevive al número de configuraciones que probé? → **DSR / PBO** (sección 1).

Fuentes: Politis & Romano (1994), *"The Stationary Bootstrap"* — implementación y explicación: https://mathweb.ucsd.edu/~politis/impactBOOT.pdf · calculadora conceptual: https://metricgate.com/docs/stationary-bootstrap-politis-romano/

---

## 3. Etiquetado y Machine Learning (López de Prado)

### 3.1 Triple-barrier labeling

**Analogía**: en vez de preguntar "¿subirá el precio dentro de exactamente 4 horas?" (una pregunta rígida que ignora que en 10 minutos el precio ya podría haber tocado tu stop), preguntas: "de estas tres líneas de meta — toma de beneficio arriba, stop-loss abajo, límite de tiempo al frente — ¿cuál toca primero el precio?". Esa es la etiqueta.

**Definición técnica**: para cada observación en el tiempo t, se fijan tres barreras: una superior (take-profit, a una distancia proporcional a la volatilidad reciente), una inferior (stop-loss) y una vertical (límite de tiempo/número de barras). La etiqueta es +1, -1 o 0 según cuál de las tres barreras se toca primero. Esto hace que la etiqueta refleje de forma realista **cómo se gestionaría de verdad la operación** (con stop y take-profit), y que el horizonte de la etiqueta se adapte a la volatilidad del momento en vez de ser un número de barras fijo arbitrario.

Fuente: capítulo 3 de *Advances in Financial Machine Learning* · explicación aplicada: https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/ · https://www.quantmemo.com/concepts/triple-barrier-labeling

### 3.2 Meta-labeling

**La idea en llano**: separa dos preguntas que normalmente se mezclan en un solo modelo: "¿en qué dirección debería operar?" (el modelo primario, que puede ser tan simple como una media móvil o una regla técnica) y "¿debería fiarme de esta señal concreta y con qué tamaño?" (el modelo secundario o "meta-modelo", que solo aprende a filtrar). El modelo primario puede tener **recall alto** (detecta casi todas las oportunidades reales, aunque también dispara muchos falsos positivos) y el meta-modelo se dedica exclusivamente a subir la **precisión** vetando las señales de baja confianza — normalmente esto mejora el F1-score y el Sharpe más que intentar que un único modelo aprenda dirección y tamaño a la vez.

**Evidencia empírica citada**: en un caso de estudio con una estrategia simple de reversión a la media, aplicar meta-labeling elevó la precisión out-of-sample del 17% al 63% sin sacrificar apenas recall. Esto encaja con la experiencia de tu propio proyecto (StrategyML en v7): un modelo primario de reglas + un filtro ML de confianza es, según la literatura, un patrón más robusto que pedirle a un único modelo que decida dirección y tamaño simultáneamente.

Fuentes: Wikipedia (resumen técnico con referencias): https://en.wikipedia.org/wiki/Meta-Labeling · caso práctico con métricas: https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/ · ejemplo didáctico: https://hudsonthames.org/meta-labeling-a-toy-example/ · discusión crítica ("no es una bala de plata"): https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/

### 3.3 Pesos por unicidad y bootstrap secuencial

**El problema en llano**: si tu etiqueta mira "qué pasa en las próximas 8 horas" y generas una observación cada 15 minutos, cada etiqueta se solapa muchísimo con las de sus vecinas — no son 32 eventos independientes, son casi el mismo evento visto 32 veces. Si entrenas un Random Forest con bagging estándar (que asume observaciones independientes), estás dándole al modelo información redundante disfrazada de información nueva, e infla artificialmente su confianza.

**Solución técnica**: se calcula la "concurrencia" de cada etiqueta (cuántas otras etiquetas activas se solapan con ella en cada punto del tiempo) y se deriva un peso de "unicidad promedio" — las etiquetas más solapadas con otras pesan menos. El **bootstrap secuencial** usa estos pesos para construir cada muestra de entrenamiento del bagging añadiendo observaciones con una probabilidad inversamente proporcional a cuánto se solapan con lo que ya está en la muestra, en vez de un muestreo aleatorio uniforme.

Fuente: capítulo 4 de *Advances in Financial Machine Learning* · implementación de referencia: https://hudsonthames.org/bagging-in-financial-machine-learning-sequential-bootstrapping-python/

### 3.4 Diferenciación fraccional

**El dilema en llano**: para que un modelo estadístico funcione bien necesitas que la serie sea "estacionaria" (que su comportamiento estadístico no cambie con el tiempo). El precio de BTC no lo es. La forma clásica de arreglarlo es tomar el retorno (diferencia de orden 1, `precio(t) - precio(t-1)`), pero al hacerlo **se borra casi toda la memoria de largo plazo de la serie** — información que podría ser útil para el modelo.

**Solución técnica**: en vez de diferenciar a un orden entero (0 = nada, 1 = retorno completo), López de Prado propone diferenciar a un orden fraccional `d` (un número real entre 0 y 1, o incluso mayor), buscando el **mínimo `d`** que hace que la serie pase un test de estacionariedad (como el ADF) mientras conserva la máxima correlación posible con la serie original — es decir, conserva memoria de largo plazo mientras cumple el requisito estadístico mínimo de estacionariedad. El resultado es una serie estacionaria pero que sigue "pareciéndose" mucho a los precios originales, útil como feature para ML.

Fuentes: capítulo 5 de *Advances in Financial Machine Learning* · explicación con ejemplos: https://hudsonthames.org/fractional-differentiation/ · https://pauliusztin.medium.com/fractionally-differentiated-features-to-preserve-memory-in-stationary-time-series-7be91947c9d6

### 3.5 Importancia de variables: MDI, MDA y SFI

- **MDI (Mean Decrease Impurity)**: se calcula directamente del árbol/bosque durante el entrenamiento, mide cuánto reduce cada variable la "impureza" en las divisiones del árbol. Es rápido pero **usa rendimiento in-sample** — puede sobrevalorar variables que solo ayudan a memorizar el training set.
- **MDA (Mean Decrease Accuracy)**: se aplica a cualquier clasificador (no solo árboles), y mide cuánto empeora el rendimiento **out-of-sample** cuando se baraja (shuffle) una variable al azar, rompiendo su relación con el resto. Al usar rendimiento fuera de muestra, corrige la principal limitación del MDI.
- **Ambos** sufren de "efecto sustitución": si dos variables están muy correlacionadas, el modelo puede repartir la importancia entre ambas o volcarla en una y dejar la otra como "redundante", enmascarando la importancia real de ese grupo de información.
- **SFI (Single Feature Importance)**: evalúa cada variable **de forma aislada** (un modelo por variable), evitando el efecto sustitución, aunque al precio de no capturar interacciones entre variables.
- **Clustered Feature Importance (CFI)**: agrupa primero las variables correlacionadas en clusters y calcula la importancia a nivel de cluster, resolviendo el problema de sustitución sin perder la capacidad de capturar interacciones dentro del grupo.

**Regla práctica**: nunca uses solo MDI (es la más fácil de calcular y la más engañosa). Como mínimo, cruza MDI con MDA; si tienes variables candidatas a estar correlacionadas (típico en indicadores técnicos: RSI, estocástico, etc., que suelen moverse juntos), usa SFI o CFI para no descartar por error un grupo de variables genuinamente útil.

Fuentes: capítulo 8 de *Advances in Financial Machine Learning* · resumen con código: https://medium.com/@lucasastorian/understanding-financial-feature-importance-7eeb49c2df0b · documentación de implementación: https://random-docs.readthedocs.io/en/latest/implementations/feature_importance.html

### 3.6 Por qué el train/test aleatorio está mal en series temporales

Ya lo hemos visto en la sección 1.6 desde el ángulo de la validación cruzada, pero merece remarcarse como principio general: **cualquier método que asuma que las filas de tu dataset son independientes e idénticamente distribuidas (IID) está mal aplicado a series temporales financieras**, porque (a) las etiquetas se solapan en el tiempo (sección 3.3), (b) hay autocorrelación en los propios retornos, y (c) hay dependencia estructural del régimen de mercado (sección 4). Un split aleatorio 80/20 puede poner una barra de "test" justo al lado (en el tiempo) de una barra de "training" cuya etiqueta la incluye, filtrando información del futuro hacia el pasado sin que el código tenga ningún bug aparente — es una fuga de información puramente estadística, no un error de programación.

### 3.7 ¿Qué evidencia hay de que el ML aporta valor en cripto frente a reglas simples?

La evidencia es **mixta y débil, no una victoria clara del ML**:

- Estudios de trend-following simple en BTC (medias móviles) muestran resultados sólidos: por ejemplo, una estrategia de media móvil de 50 días obtuvo un Sharpe de 1,9 frente a 1,3 del buy-and-hold en el periodo estudiado, con menor volatilidad — es decir, **una regla trivial ya captura buena parte del "edge" disponible en tendencia**.
- Algunos estudios individuales muestran que modelos más sofisticados (p.ej. redes de funciones de base radial, RBFNN) superan a la media móvil simple, pero son estudios aislados, sin la validación estadística rigurosa de las secciones 1-2 de este documento (sin DSR, sin PBO, sin corrección por múltiples pruebas) — exactamente el patrón de resultado que hay que sospechar por defecto.
- Estudios de ensembles de ML sobre cripto reportan Sharpes anualizados en el rango 0,8-0,9 **después de costes** en algunos activos — resultados respetables pero no dramáticamente superiores a las reglas simples bien ejecutadas, y muy sensibles a qué activos/periodos se reportan (riesgo de selección de resultados).
- Cuando se incluyen costes de transacción realistas, el número de estrategias con retorno positivo cae significativamente en varios de estos estudios — coherente con la sección 6 de este documento.

**Conclusión práctica**: no hay evidencia robusta de que el ML domine sistemáticamente a las reglas simples bien validadas en cripto. Lo que sí hay evidencia sólida es de que el ML mal validado (sin las técnicas de las secciones 1 y 3) genera resultados de backtest engañosamente buenos que no sobreviven en vivo — que es justamente el tema del siguiente apartado.

Fuentes: comparación de modelos en BTC: https://arxiv.org/html/2407.18334v1 · estrategia de medias móviles en BTC: https://www.researchgate.net/publication/389395534_Bitcoin_Financial_Forecasting_Analyzing_the_Impact_of_Moving_Average_Strategies_on_Trading_Performance · revisión de ML para predicción/trading de cripto: https://www.sciencedirect.com/science/article/pii/S2405918822000174 · resultados con costes de transacción: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7785332/

### 3.8 Por qué la mayoría de fondos de Machine Learning fracasan

López de Prado, con experiencia directa dirigiendo equipos cuantitativos, documenta un patrón recurrente de errores en *"The 10 Reasons Most Machine Learning Funds Fail"* (Journal of Portfolio Management, 2018) y su versión previa *"The 7 Reasons..."*. Entre los puntos confirmados en múltiples fuentes están: el **"paradigma de Sísifo"** (cada investigador reinventa desde cero en vez de acumular en un meta-modelo compartido — solucionado con lo que él llama el paradigma de meta-estrategia), **investigar mediante backtesting repetido** en vez de análisis de importancia de variables (backtesting debería ser el último paso de verificación, no la herramienta de descubrimiento — exactamente el error que las secciones 1 y 2 de este documento buscan prevenir), **muestreo cronológico** (barras de tiempo fijo) en vez de muestreo por actividad/información (barras de volumen o dólar), e **diferenciación entera** en vez de fraccional (sección 3.4). El resto de causas que documenta se solapan directamente con el resto de errores cubiertos en las secciones 3, 8 y 9 de este documento (etiquetado de horizonte fijo en vez de triple-barrera, aprender dirección y tamaño a la vez en vez de meta-labeling, pesos de muestra no-IID ignorados, fuga en validación cruzada, y sobreajuste de backtest).

Fuentes: SSRN 3104816: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3104816 · whitepaper GARP: https://www.garp.org/white-paper/the-10-reasons-most-machine-learning-funds-fail · versión previa (7 razones): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3031282

---

## 4. Regímenes de mercado

### 4.1 La idea en llano

No siempre llueve igual: hay días de sol, de lluvia suave y de tormenta, y no ves directamente "el tiempo que va a hacer" sino pistas indirectas (nubes, presión, humedad). Un **régimen de mercado** es parecido: no observas directamente si el mercado está "en tendencia" o "en rango", pero sí observas pistas (retornos, volatilidad, volumen) de las que puedes inferir, con cierta probabilidad, en qué "estado oculto" está el mercado ahora mismo.

### 4.2 Hidden Markov Models (HMM)

**Definición técnica**: un HMM asume que el mercado está en cada momento en uno de varios estados "ocultos" (p.ej. tendencia alcista de baja volatilidad, rango de volatilidad media, pánico de alta volatilidad), y que solo observas variables derivadas de ese estado (retornos, volatilidad realizada, volumen, desequilibrio del order book). El modelo se entrena (algoritmo de Baum-Welch) para estimar las probabilidades de transición entre estados y la distribución de las variables observables en cada estado, y luego se usa (algoritmo de Viterbi, o el filtro de Hamilton) para inferir en qué estado es más probable que estés ahora mismo, dado lo observado hasta este instante.

**Aplicación práctica**: estrategias de tendencia (cruces de medias, momentum) tienden a funcionar mejor cuando la probabilidad de "régimen de tendencia" es alta; estrategias de reversión a la media funcionan mejor en "régimen de rango". El régimen también puede usarse para ajustar el tamaño de posición (reducir en régimen de alta volatilidad).

### 4.3 El punto crítico: cómo NO hacer trampa al etiquetar el régimen

Este es el punto donde casi todo el mundo se equivoca sin darse cuenta, y merece la mayor atención de esta sección:

- **Filtro (Hamilton) vs. suavizado (Kim)**: el filtrado calcula la probabilidad del estado en el instante t **usando solo información hasta t** — esto es lo único válido para generar una señal de trading en tiempo real o para un backtest honesto. El **suavizado** (Kim smoother) reestima la probabilidad del estado en el instante t usando **toda la muestra, pasado y futuro** — es útil para análisis histórico *a posteriori* ("¿en qué régimen estuvimos en marzo de 2022?"), pero **usarlo para generar señales de entrada es lookahead bias puro**, aunque no lo parezca a primera vista porque no estás "mirando el precio de mañana" directamente — estás dejando que la reestimación completa del modelo, con datos futuros, cambie retroactivamente tu creencia sobre el pasado.
- **Reentrenamiento walk-forward del propio HMM**: los parámetros del HMM (medias, volatilidades y matriz de transición de cada estado) no se pueden estimar una sola vez con todo el histórico y aplicarse "hacia atrás" — hay que reestimarlos de forma expansiva o rodante, igual que cualquier otro modelo, para que en cada punto del backtest el HMM solo "sepa" lo que un HMM entrenado en tiempo real habría sabido.
- **Etiquetar regímenes a toro pasado para excluir periodos malos**: definir explícitamente "esto fue un régimen malo" después de ver que la estrategia perdió dinero ahí, y luego excluir ese régimen del backtest, es una forma encubierta de survivorship bias / data snooping — estás usando el resultado para definir el filtro que luego "explica" el resultado.
- **Umbral de detección vs. falsos positivos**: umbrales de probabilidad más bajos detectan el cambio de régimen más rápido (p.ej. ~1,5 días con umbral 0,3) pero a costa de disparar muchos más falsos cambios de régimen; umbrales más altos (~4 días con umbral 0,7) son más lentos pero más fiables. Este trade-off debe fijarse *a priori*, como hiperparámetro dentro de tu proceso de validación walk-forward — no ajustarse después de ver qué umbral "habría ido mejor".

**Evidencia de que filtrar por régimen ayuda**: es plausible y coherente con la intuición de mercado (adaptar el estilo de estrategia al contexto), pero introduce una capa adicional de parámetros (número de estados, features de entrada del HMM, umbral de decisión) que es, en sí misma, **otra superficie de sobreajuste** que hay que descontar con las técnicas de la sección 1 (DSR, PBO) igual que cualquier otro parámetro de la estrategia — el régimen no es gratis, es un componente más del modelo que también hay que penalizar por el número de configuraciones probadas.

Fuentes: introducción práctica con Python: https://blog.quantinsti.com/regime-adaptive-trading-python/ · aplicación con QSTrader: https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/ · sobre el sesgo de latencia filtro vs suavizado: https://mathandmarkets.com/p/regime-detection-part-2-the-latency · glosario técnico: https://questdb.com/glossary/market-regime-detection-using-hidden-markov-models/

---

## 5. Tamaño de posición y riesgo

### 5.1 Kelly y Kelly fraccional

**La fórmula, en llano**: el criterio de Kelly te dice qué fracción de tu capital apostar en cada operación para maximizar el crecimiento **geométrico** a largo plazo, dado tu porcentaje de acierto y tu ratio ganancia/pérdida. La fórmula clásica para una apuesta binaria:

```
f* = (p·b − q) / b
```

donde `p` = probabilidad de ganar, `q = 1−p`, y `b` = ratio de la ganancia sobre la pérdida (odds).

**Por qué el Kelly completo arruina en la práctica** (aunque sea matemáticamente "óptimo" bajo supuestos perfectos): (1) `p` y `b` nunca se conocen con certeza, se **estiman** con error a partir de un histórico limitado, y el tamaño óptimo de Kelly es extremadamente sensible a esos errores de estimación — una sobrestimación pequeña del edge convierte la fórmula, de herramienta de maximización de riqueza, en un mecanismo de destrucción de capital; (2) incluso con `p` y `b` exactos, el crecimiento óptimo de Kelly acepta una probabilidad alta de **drawdowns muy profundos** en el camino (es óptimo en el larguísimo plazo, no en la experiencia de un trader real con un horizonte y una tolerancia psicológica y financiera concretos); (3) apostar por encima del Kelly óptimo ("over-betting") hace que la tasa de crecimiento *compuesto* se vuelva negativa, garantizando la ruina eventual con probabilidad 1.

**Kelly fraccional**: en la práctica, ningún fondo serio usa Kelly completo. Se usa una fracción — mitad (½ Kelly) o un cuarto (¼ Kelly) — del tamaño calculado. Medio Kelly conserva aproximadamente el **75% de la tasa de crecimiento compuesto** del Kelly completo, pero reduce drásticamente la volatilidad del camino — una propiedad matemática derivada, no una regla empírica arbitraria. AQR, en su gestión de futuros administrados, documenta el uso de un multiplicador de Kelly de aproximadamente **0,40** combinado con objetivo de volatilidad y límites de apalancamiento — un ejemplo concreto y público de cómo un fondo real implementa esto.

Fuentes: explicación con simulaciones: https://www.quantifiedstrategies.com/why-the-kelly-criterion-is-dangerous-for-most-traders/ · comparación Kelly completo vs. fraccional: https://astuteinvestorscalculus.com/full-kelly-vs-fractional-kelly/ · AQR *"Understanding Managed Futures"*: https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Understanding-Managed-Futures.pdf · AQR *"Demystifying Managed Futures"*: https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Demystifying-Managed-Futures.pdf

### 5.2 Volatility targeting (objetivo de volatilidad)

**La idea**: en vez de apostar el mismo tamaño (en euros o en %) siempre, ajustas el tamaño de la posición de forma **inversamente proporcional a la volatilidad reciente** del activo, para mantener el riesgo del portfolio aproximadamente constante en el tiempo. Ejemplo: si tu objetivo es un 10% de volatilidad anualizada y la volatilidad de BTC se dispara al 30%, tu posición se reduce a un tercio del tamaño que tendrías con BTC al 10% de volatilidad. Esto es lo que hacen sistemáticamente los fondos de futuros administrados (managed futures) tipo AQR: **el objetivo de volatilidad hace que el riesgo sea consistente en el tiempo**, lo que a su vez hace los resultados más fáciles de interpretar y evita "explosiones" repentinas de riesgo cuando el mercado se vuelve más salvaje sin que tú lo hayas notado.

**Ventaja frente a Kelly puro cuando el histórico es corto**: el objetivo de volatilidad necesita estimar solo la volatilidad (relativamente fácil y estable de estimar incluso con poca historia), mientras que Kelly necesita estimar con precisión el edge (`p` y `b`), que es mucho más ruidoso y requiere muchísimos más datos para estimarse con confianza razonable — por eso combinar ambos (Kelly fraccional pequeño, más objetivo de volatilidad como "cinturón y tirantes") es más robusto que depender solo de uno de los dos, especialmente con el histórico limitado que tiene cualquier bot de cripto reciente.

### 5.3 Riesgo de ruina (Risk of Ruin)

**Definición**: la probabilidad de que tu cuenta llegue a un umbral catastrófico de pérdidas antes de alcanzar tu objetivo, dado tu edge (acierto × ratio ganancia/pérdida), tu porcentaje de riesgo por operación, y el número de operaciones. Ralph Vince formalizó esta matemática en *"The Mathematics of Money Management"* (1992); Nauzer Balsara publicó tablas de referencia el mismo año.

**Ejemplo concreto (orden de magnitud, no receta exacta para tu caso)**: con 40% de acierto y una ganancia media de 1,2R (donde R es el riesgo asumido por operación), arriesgar un 2% de la cuenta por operación implica una probabilidad de ruina de aproximadamente 40-60% en 1.000 operaciones; bajar al 1% de riesgo por operación reduce esa probabilidad a menos del 5% en el mismo horizonte. **El hallazgo clave**: el tamaño de la posición (% arriesgado por operación) es, con diferencia, la palanca más determinante para la supervivencia — más que el propio win-rate. Los traders profesionales suelen fijar como objetivo un riesgo de ruina por debajo del 5%; los fondos institucionales, por debajo del 1%.

Fuentes: explicación con tablas: https://journalplus.co/learn/guides/risk-of-ruin-guide/ · calculadora y fórmula: https://www.backtestbase.com/education/risk-of-ruin-calculator-trading · https://www.quantifiedstrategies.com/risk-of-ruin-in-trading/

### 5.4 Control de drawdown

Ligado a lo anterior: fija de antemano (no a posteriori) un umbral de drawdown que **dispara automáticamente** una reducción de tamaño o una parada completa (kill-switch). Este mecanismo — reducir riesgo cuando el modelo empieza a fallar o la volatilidad se dispara — está integrado explícitamente en el diseño de sistemas como el de Renaissance Technologies (donde el control de riesgo no es una capa separada, sino parte del propio diseño del modelo: reduce posiciones automáticamente cuando las estrategias no están funcionando o la volatilidad del mercado se dispara) y en el objetivo de volatilidad dinámico de AQR. La clave práctica es que el umbral se define **antes** de operar, con datos, y no se relaja de forma discrecional cuando "esta vez parece diferente".

### 5.5 Correlación entre posiciones simultáneas: el problema específico de cripto

**El error típico**: pensar que tener posiciones abiertas en BTC, ETH, SOL y otras 5 altcoins simultáneamente es "diversificación", cuando en realidad casi todas están dominadas por los mismos factores macro (liquidez global, sentimiento de riesgo, dominancia de BTC). La evidencia de mercado es clara: los movimientos de las principales criptomonedas están altamente correlacionados entre sí, especialmente durante caídas ("todo cae junto"), y ese co-movimiento sistémico socava la lógica de diversificar *dentro* de cripto — la diversificación real solo aparece cuando se combina cripto con clases de activos genuinamente distintas (renta variable, bonos), no dentro del propio universo cripto.

**Implicación práctica de sizing**: si tu bot puede abrir posiciones simultáneas en varios pares de cripto, **debes tratar esas posiciones como una sola apuesta agregada a efectos de límite de exposición total**, no como N apuestas independientes que "promedian" su riesgo. Calcular el riesgo de la cartera con una matriz de correlación (o, más simple y conservador dado el histórico limitado, asumir una correlación alta por defecto, p.ej. 0,7-0,9, entre cualquier par de posiciones cripto simultáneas) y fijar un límite de exposición neta total del book, no solo un límite por operación individual.

Fuentes: https://research.grayscale.com/reports/crypto-in-diversified-portfolios · discusión sobre correlación sistémica intra-cripto: (ver también hallazgos del NBER sobre wash trading en sección 9, que además contamina las métricas de volumen usadas para medir esa correlación)

### 5.6 Dimensionar con histórico corto

Cuando el histórico disponible es limitado (como suele ser el caso en cripto, sobre todo en pares que no sean BTC/ETH), la estimación del edge (`p`, `b`) tiene un error estándar grande, lo que hace que aplicar Kelly (fraccional o no) directamente sobre el edge estimado sea peligroso — estás dimensionando con precisión una cantidad que no conoces con precisión. Prácticas razonables:
- Aplicar un "descuento" (shrinkage) al edge estimado hacia cero o hacia un valor de referencia conservador, proporcional a la incertidumbre de la estimación (más operaciones en el histórico → menos shrinkage necesario).
- Preferir el objetivo de volatilidad (que necesita estimar una cantidad más estable, la volatilidad) sobre el Kelly puro (que necesita el edge, mucho más ruidoso) cuando el histórico es corto.
- Usar directamente los intervalos de confianza del bootstrap estacionario (sección 2.4) sobre el Sharpe/edge, y dimensionar en función del extremo pesimista del intervalo, no del punto central.

---

## 6. Costes y ejecución real

### 6.1 Por qué un backtest con coste cero es una mentira, con números

La literatura cuantitativa es contundente en este punto: ignorar o subestimar comisiones y slippage puede inflar dramáticamente los resultados simulados — un backtest que muestra un 15% de retorno anual puede colapsar a casi cero al incorporar costes realistas, especialmente en estrategias de alta rotación. Un estudio dinámico de costes encontró que el **coste real de ejecutar una estrategia sistemática típica es 2-4 veces la estimación de coste fijo habitual** en la investigación académica — en su ejemplo concreto, el Sharpe anualizado cae de 0,84 (con un coste fijo de 1 punto básico por contrato) a 0,61 (con un modelo de coste dinámico más realista). Esto valida directamente la regla que ya usas de "doblar el coste estimado" como mínimo razonable — y sugiere que en momentos de estrés (justo cuando más necesitas liquidez) el multiplicador real puede ser aún mayor.

Fuente: https://onepagecode.substack.com/p/backtesting-a-trading-strategy · modelización dinámica de costes: referenciado en resultados de búsqueda sobre "Implementation Risk in Portfolio Backtesting" https://arxiv.org/pdf/2603.20319

### 6.2 Componentes del coste real: spread, slippage, impacto, funding

- **Spread**: la diferencia entre el precio de compra y venta que existe en todo momento, incluso sin que tú operes. Es un coste que pagas en cada entrada y cada salida.
- **Slippage**: la diferencia entre el precio al que "decidiste" operar (la señal) y el precio al que realmente se ejecutó la orden, por el tiempo que pasa entre decisión y ejecución y por la latencia del sistema.
- **Impacto de mercado**: el efecto de que tu propia orden mueva el precio en tu contra, relevante sobre todo si operas tamaños grandes relativos a la liquidez disponible en ese instante. El modelo de referencia es **Almgren-Chriss** (2000): el precio de ejecución se descompone en impacto **permanente** (que persiste, proporcional a la cantidad acumulada negociada) y un impacto **temporal** (que solo afecta a la orden actual, proporcional a la velocidad de negociación), ambos modelados típicamente con leyes de potencia (`g(v) = γ·v^α`, `h(v) = η·v^β`), con la conocida "ley de la raíz cuadrada" como aproximación empírica habitual del impacto frente al tamaño de la orden.
- **Funding de perpetuos**: en los contratos perpetuos (el instrumento más habitual para ir largo/corto apalancado en cripto), se paga o cobra periódicamente (típicamente cada 8 horas) una tasa de financiación entre posiciones largas y cortas, cuyo objetivo es mantener el precio del perpetuo anclado al spot. Ejemplo numérico ilustrativo: una tasa de 0,03% cada 8h equivale a ~0,09%/día, ~33% anualizado de coste (o ingreso, según el lado) — para cualquier bot que mantenga posiciones abiertas varias horas o días, **este coste hay que acumularlo barra a barra, no solo en el cierre de la posición**, porque una operación que "cruza" varias ventanas de funding puede ver su coste total superar fácilmente el objetivo de beneficio de la operación.

Fuentes: modelo Almgren-Chriss: https://en.wikipedia.org/wiki/Almgren%E2%80%93Chriss_model · paper original y extensiones: https://arxiv.org/pdf/1403.2229 · funding de perpetuos explicado: https://www.coinbase.com/learn/perpetual-futures/understanding-funding-rates-in-perpetual-futures · ejemplo de arbitraje de funding y su coste: https://medium.com/@DolphinDB_Inc/profiting-from-perpetuals-implementing-a-funding-rate-arbitrage-strategy-with-backtesting-e8b9b8766ac1

### 6.3 El caso concreto de Quantfury: cómo cobra una plataforma "sin comisiones"

Quantfury anuncia operar "libre de comisiones y fees", pero **no es gratis** — su propio centro de ayuda explica el modelo de negocio: las operaciones de los usuarios se cruzan internamente (o Quantfury actúa como contraparte), garantizando la ejecución a los mejores precios de mercado disponibles **sin cobrar comisión explícita**; en cambio, la plataforma **captura el spread natural entre compra y venta** que normalmente iría a un market maker externo, y adicionalmente monetiza datos agregados de trading de sus usuarios para su propio desk propietario.

**Consecuencia práctica para tu validación de costes**: como no hay una comisión visible que puedas simplemente sumar, el coste real está **escondido dentro de cada precio de ejecución** frente al precio "verdadero" de mercado en ese instante. La forma correcta de estimarlo no es asumir un número de la documentación, sino **medirlo empíricamente**: comparar, para una muestra de operaciones, el precio de ejecución reportado por Quantfury contra un feed de referencia externo independiente (p.ej. el mid-price de un exchange grande) en el mismo timestamp, y calcular la diferencia media (el "spread efectivo" round-trip). Ese spread efectivo medido es el número que debe entrar en el backtest — y, siguiendo la regla ya validada en la sección 6.1, aplicar como mínimo el doble de esa medición como margen de seguridad.

Fuente oficial: https://support.quantfury.com/hc/en-us/articles/360032797191-How-Quantfury-Makes-Money · https://help.quantfury.com/en/articles/5448744-how-quantfury-makes-money

---

## 7. Métricas: cuáles importan y cuáles engañan

### 7.1 Familia Sharpe / Sortino / Calmar / MAR

- **Sharpe** = (retorno − tasa libre de riesgo) / desviación estándar de los retornos. Penaliza toda la volatilidad, tanto al alza como a la baja.
- **Sortino** = igual que Sharpe pero solo penaliza la **desviación a la baja** (downside deviation) — más indulgente que Sharpe con estrategias que tienen ganancias muy grandes ocasionales (asimetría positiva), porque no las penaliza como "riesgo".
- **Calmar** = retorno anualizado (normalmente de los últimos 36 meses) dividido entre el **drawdown máximo** en ese mismo periodo. Fue creado por Terry W. Young en 1991 para evaluar CTAs y hedge funds.
- **MAR** = igual que Calmar pero usando **todo el historial desde el inicio**, no solo 36 meses. Calmar y MAR se confunden a menudo pero no son lo mismo: Calmar es una ventana móvil de 3 años, MAR es "desde el origen".

### 7.2 Drawdown máximo, duración y "tiempo bajo el agua"

- **Drawdown máximo**: la mayor caída porcentual desde un máximo (pico) hasta el valle posterior, en todo el periodo analizado.
- **Duración del drawdown / tiempo bajo el agua**: cuánto tiempo pasa desde que se toca un máximo hasta que se **recupera** ese máximo (no solo hasta el valle). Una estrategia puede tener un drawdown máximo moderado pero tardar años en recuperarse — esa duración es psicológica y prácticamente tan importante como la profundidad.
- **Ulcer Index**: combina profundidad y duración del drawdown en un único número, cuantificando cuánto y cuánto tiempo la cartera pasa por debajo de su máximo previo — más informativo que el drawdown máximo aislado, que solo captura el peor instante.

### 7.3 Profit factor, expectativa y la trampa del win-rate alto

- **Profit factor** = ganancia bruta total / pérdida bruta total. Por encima de 1 significa que ganas más de lo que pierdes en conjunto; un objetivo profesional habitual está entre 1,5 y 2,5.
- **Expectativa por operación** = (% acierto × ganancia media) − (% fallo × pérdida media). Es la métrica más honesta de "cuánto esperas ganar de media por operación", y la que de verdad determina si el sistema tiene un edge real, independientemente del win-rate.
- **La trampa del win-rate alto**: un sistema con 75% de acierto pero un ratio ganancia/pérdida de solo 0,5:1 es, en palabras de la propia literatura de trading, "una trampa de dinero" — pierde más en las operaciones malas de lo que gana en las buenas y puede tener expectativa negativa o marginal a pesar del "impresionante" 75%. En cambio, un sistema con solo 45% de acierto pero un ratio 2,2:1 tiene una expectativa claramente positiva; incluso un 40% de acierto con ratio 1:3 puede superar a un 60% de acierto con mal ratio. Win-rate y ratio ganancia/pérdida están, además, inversamente relacionados en la práctica: ampliar el objetivo de beneficio (mejor ratio) casi siempre reduce el win-rate, porque menos operaciones llegan a tocar un objetivo más lejano. **Mejorar el ratio ganancia/pérdida suele tener más impacto en la rentabilidad final que mejorar el win-rate**, y por eso un win-rate alto, sin mirar el ratio, no dice nada sobre la calidad real del sistema.

### 7.4 ¿Cuántas operaciones hacen falta para que un Sharpe sea creíble? (con fórmula)

Esta es la pregunta que casi nadie responde con números. Existen dos herramientas del propio marco de Bailey/López de Prado directamente aplicables:

**Sharpe Ratio Probabilístico (PSR)** — ya introducido en la sección 1.2, aquí con la fórmula completa y el detalle de cada variable:

```
PSR(SR*) = Φ( (SR̂ − SR*) · √(T−1) / √(1 − γ₃·SR̂ + ((γ₄−1)/4)·SR̂²) )
```

- `SR̂`: Sharpe observado (por periodo, no anualizado, para ser consistente con T).
- `SR*`: Sharpe de referencia contra el que quieres comparar (p.ej. 0, o el Sharpe de un benchmark buy-and-hold).
- `T`: número de observaciones (barras, no operaciones — si usas velas de 15 minutos, T es el número de velas del backtest).
- `γ₃`, `γ₄`: asimetría y curtosis muestral de la serie de retornos de la estrategia.
- El resultado `PSR(SR*)` es la probabilidad (entre 0 y 1) de que el Sharpe real de la estrategia sea mayor que `SR*`, dado lo observado.

**Longitud mínima de historial (MinTRL)** — la pregunta inversa: dado el Sharpe que observas, ¿cuántas observaciones necesitas para poder afirmar con confianza `1−α` que el Sharpe real supera `SR*`?

```
MinTRL(c) = ( 1 − γ₃·SR̂ + ((γ₄−1)/4)·SR̂² ) · ( z_(1−α) / (SR̂ − c) )²
```

donde `z_(1−α)` es el valor crítico de la normal estándar (p.ej. 1,645 para 95% de confianza a una cola) y `c` es el Sharpe de referencia. Cuanto más alta la asimetría/curtosis "mala" (colas pesadas a la izquierda) y más bajo el Sharpe observado respecto al de referencia, más observaciones necesitas.

**Regla práctica adicional citada en la literatura de trading**: como mínimo 30 operaciones para empezar a hacer cualquier inferencia estadística, y 100+ para que las métricas de rendimiento sean razonablemente fiables — con 20 operaciones, incluso un Sharpe de 2,0 puede no ser estadísticamente significativo; con 100 operaciones, un Sharpe de 1,0 ya puede serlo al 95% de confianza. La relación exacta depende además de la autocorrelación de los retornos de la estrategia (retornos correlacionados requieren más observaciones para el mismo nivel de confianza que retornos independientes).

Fuentes: fórmulas completas con derivación: https://portfoliooptimizer.io/blog/the-probabilistic-sharpe-ratio-bias-adjustment-confidence-intervals-hypothesis-testing-and-minimum-track-record-length/ · paper aplicado *"Testing Sharpe ratio: luck or skill?"*: https://arxiv.org/abs/1905.08042 · guía práctica sobre número de operaciones: https://medium.com/@trading.dude/how-many-trades-are-enough-a-guide-to-statistical-significance-in-backtesting-093c2eac6f05

---

## 8. Proceso: el cuaderno de laboratorio

### 8.1 Pre-registro de hipótesis

**La idea**: antes de tocar ni un dato, escribes en un documento append-only (que nunca se borra ni se edita retroactivamente) una ficha con: la afirmación económica/de mercado concreta que crees cierta, la variable objetivo (el label), el/los predictor(es), el universo y rango temporal exacto de datos que vas a usar, la hipótesis nula, y el criterio numérico de éxito — **todo esto antes de ver ningún resultado**. Forzar la hipótesis a este esquema fijo es, según la práctica documentada en investigación cuantitativa, la restricción individual más importante de todo el proceso: hace imposible que salga algo "interesante pero infalsificable" — si no puedes rellenar la ficha con precisión, no tienes todavía una hipótesis, tienes una corazonada.

### 8.2 Registro de todos los intentos (no solo el ganador)

El experiment log debe funcionar como cuaderno de laboratorio de todo el proyecto: cada intento se registra con marca de tiempo, una hipótesis de una línea, y los resultados obtenidos — **incluidos los fallidos**. Esto no es burocracia opcional: es el insumo obligatorio para calcular el DSR, el PBO y el ajuste de Harvey-Liu-Zhu (secciones 1.2, 1.3 y 1.8) — todos ellos necesitan saber `N`, el número total de configuraciones probadas, no solo la que finalmente aprobaste. Un proyecto que "olvida" cuántas variantes probó no puede, por definición, corregir su propio sobreajuste.

### 8.3 Particiones: development / validation / holdout

- **Development (desarrollo)**: los datos donde construyes y ajustas libremente — aquí es donde vives, iteras, pruebas ideas.
- **Validation (validación)**: datos fuera de development que usas repetidamente durante la investigación para comparar configuraciones entre sí (alimenta la CPCV, el PBO). Se puede "mirar" muchas veces, pero cada vez que lo haces cuenta como un test más a efectos de la corrección por múltiples pruebas.
- **Holdout**: datos que **no se tocan nunca** durante todo el proceso de desarrollo y validación — ni siquiera para "solo mirar cómo va, sin ajustar nada". Se abren **una sola vez**, al final, cuando todo lo demás (desarrollo, validación, costes, riesgo) ya está aprobado. Por qué solo una vez: en cuanto miras el holdout y decides "no, vamos a ajustar algo más", el holdout deja de ser holdout — se ha convertido en parte de tu conjunto de validación (aunque sea sin querer), y cualquier resultado posterior sobre esos mismos datos ya está contaminado. Buenas prácticas documentadas en equipos de investigación cuantitativa llegan a **eliminar físicamente el fichero del holdout del sistema de archivos** mientras corren los experimentos de desarrollo/validación, precisamente para hacer imposible la tentación de "echar un vistazo".

### 8.4 Ejemplos reales de disciplina de proceso

- **Renaissance Technologies**: el control de riesgo no es una capa añadida al final, sino parte del diseño, ejecución y gestión de capacidad del propio modelo desde el principio.
- **AQR**: publica metodología de forma relativamente transparente en sus whitepapers (asignación de riesgo por volatilidad, Kelly fraccional, límites de apalancamiento) — un patrón de proceso replicable aunque no dispongas de sus recursos.
- **La cifra que resume por qué todo esto importa**: la literatura documenta que **más del 90% de las estrategias académicas publicadas fracasan al implementarse con capital real** — la disciplina de proceso (pre-registro, registro de intentos, particiones estrictas) es precisamente lo que separa a quienes descubren esto en un paper de quienes lo descubren con dinero real.

Fuentes: prácticas de experiment tracking en equipos quant: https://medium.com/@online-inference/mlops-best-practices-for-quantitative-trading-teams-59f063d3aaf8 · framework de hipótesis falsificable: https://medium.com/@NFS303/quant-research-best-practices-a-practical-guide-to-robust-trading-strategies-a9ea923ff495 · sobre Renaissance: https://breakingthemarket.com/the-greatest-geometric-balancers-renaissance-technologies-part-ii/

---

## 9. Errores clásicos que arruinan un backtest

Para cada uno: qué es, cómo se detecta, cómo se evita.

**1. Look-ahead bias (sesgo de mirar al futuro)** — existe en tres formas distintas: (a) *directo*, usar el dato de mañana para decidir hoy (el más obvio); (b) *por revisión de datos*, usar una versión de un dato que fue corregida/revisada después del momento de la decisión (ver punto 9 más abajo); (c) *por conocimiento*, aplicar información o técnicas que "sabías" que iban a funcionar porque las descubriste mirando todo el histórico a la vez (p.ej. elegir un indicador porque ya sabías, viendo el gráfico completo, dónde estaban los giros). *Detección*: auditar cada feature y comprobar que solo usa timestamps ≤ t; reconstruir el backtest bar a bar simulando que los datos posteriores a t literalmente no existen todavía. *Evitación*: pipeline de datos con corte estricto de tiempo, nunca cargar el CSV completo en memoria y "mirar hacia adelante" por accidente en el código de features.

**2. Survivorship bias (sesgo de supervivencia)** — probar la estrategia solo sobre activos/exchanges que siguen existiendo hoy, ignorando los que quebraron, fueron deslistados o dejaron de operar durante el periodo. *Magnitud documentada*: en fondos de inversión tradicionales, sobreestima los retornos medios en ~0,9%/año; en estudios de índices bursátiles, entre 1,5% y 2,0% anual. En cripto el equivalente es no incluir exchanges o tokens que desaparecieron (hacks, quiebras, rug-pulls) en el universo de backtest. *Detección*: comparar resultados con y sin activos/exchanges desaparecidos. *Evitación*: usar bases de datos que incluyan explícitamente los activos muertos, no solo el universo "vivo" de hoy.

**3. Data snooping / sobreajuste por reutilización del mismo test set** — probar y reajustar repetidamente sobre los mismos datos de "test" hasta que algo funciona. *Detección*: PBO, degradación entre in-sample y out-of-sample, DSR. *Evitación*: particiones estrictas (sección 8.3), CPCV, y contar cada mirada al validation set como un test más.

**4. Precios de cierre no ejecutables** — comprobar si un stop-loss o take-profit se activó usando solo el precio de cierre de la vela, en vez de comprobar el rango intravela (máximo/mínimo). Esto genera "supervivencias fantasma" (operaciones que en el backtest sobreviven porque el cierre no tocó el stop, pero que en la realidad sí lo habrían tocado durante la vela) y métricas de drawdown optimistas. *Detección*: comparar resultados de backtest en base a cierre vs. en base a OHLC completo — una diferencia grande es señal de alerta. *Evitación*: siempre comprobar stops/objetivos contra el rango completo de la vela (o, mejor, datos a nivel de tick cuando sea posible), asumiendo el peor caso razonable de secuencia intravela (p.ej. open→low→high→close en vez de open→high→low→close si el movimiento del stop es más probable).

**5. Relleno de huecos hacia atrás (backward-fill)** — rellenar un valor faltante con el **siguiente** valor disponible en el tiempo (en vez de con el anterior) es, literalmente, meter información del futuro en el pasado. *Detección*: auditar la función de relleno de NaNs en el pipeline; revisar manualmente 5-10 huecos conocidos del histórico. *Evitación*: política explícita de forward-fill únicamente (o dejar el hueco como NaN y excluir esa barra), nunca `bfill`.

**6. Resample mal etiquetado / convención de timestamp inconsistente entre exchanges** — cada exchange etiqueta sus velas de forma distinta: algunos (Binance) usan el timestamp de **apertura** de la vela, otros (Hyperliquid, o algunas configuraciones de NinjaTrader) usan el de **cierre** — se han documentado inconsistencias incluso dentro de la misma librería de acceso a datos (ccxt) entre exchanges. Si combinas datos de varias fuentes o resampleas de 1m a 15m sin verificar la convención, puedes desplazar tus features/etiquetas por una barra entera sin que el código falle nunca — un desalineamiento de un solo paso es suficiente para invalidar todo el backtest. *Detección*: verificar explícitamente, para cada fuente de datos, si el timestamp reportado corresponde al inicio o al final de la vela, comparando con un reloj de referencia conocido. *Evitación*: normalizar todas las fuentes a una única convención (recomendado: timestamp de apertura, exclusivo al final) antes de cualquier resample o combinación.

**7. Usar el máximo/mínimo de la vela como precio "ejecutable" exacto** — asumir que podrías haber comprado exactamente en el mínimo de la vela o vendido exactamente en el máximo es, en la práctica, casi imposible salvo con una orden límite puesta de antemano exactamente en ese nivel, y no considera que el spread/slippage también se aplica ahí. *Evitación*: ver punto 4 — usar el rango intravela para *detectar* si un nivel se tocó, pero para el precio de *ejecución* real aplicar el coste de spread/slippage de la sección 6, no el precio exacto teórico.

**8. Ignorar el funding de perpetuos** — omitir el coste (o ingreso) periódico de financiación en estrategias que mantienen posiciones abiertas durante horas o días infla silenciosamente el resultado de estrategias de carry o de tendencia de medio plazo. Ver sección 6.2 para el modelo de coste.

**9. Datos revisados (point-in-time vs. datos "limpios" actuales)** — usar la versión de un dato tal como está disponible **hoy** (ya corregida/revisada) en vez de la versión que existía en el momento histórico de la decisión. Menos relevante para el precio puro de cripto (que no se "revisa"), pero muy relevante en cuanto tu bot incorpora datos macro, on-chain o de sentimiento (CPI, índice de miedo/codicia, indicadores que se recalculan con revisiones metodológicas). *Detección*: comparar la fecha de publicación/revisión de cada dato contra la fecha de la barra donde se usa como feature. *Evitación*: usar bases de datos point-in-time (p.ej. ALFRED en vez de FRED para series macro de EE.UU.) cuando el feature dependa de datos externos revisables.

**10. Wash trading / volumen falso en cripto** — investigación académica cuantifica que el volumen wash-traded en exchanges no regulados puede promediar **más del 70% del volumen reportado**. Cualquier feature basado en volumen (filtros de liquidez, confirmación de ruptura por volumen, VWAP) construido sobre datos de un exchange con volumen inflado está, en la práctica, aprendiendo ruido fabricado. *Detección*: los exchanges con volumen fabricado tienden a mostrar una distribución de compras/ventas anormalmente equilibrada (parecida a un lanzamiento de moneda), a diferencia del patrón desigual típico de actividad económica real; contrastar volumen entre múltiples fuentes independientes. *Evitación*: usar volumen de exchanges grandes y regulados como referencia, o contrastar con datos on-chain cuando sea aplicable, en vez de fiarse de un único exchange pequeño.

**11. Liquidez fragmentada y "libros de órdenes" obsoletos** — asumir que puedes ejecutar 20 BTC al precio de venta mostrado en una instantánea (snapshot) del libro de órdenes que puede tener varios segundos de antigüedad es una de las formas más caras y menos visibles de sesgo de ejecución en investigación cuantitativa de cripto. *Evitación*: si usas profundidad de libro como feature o para estimar impacto, usar datos con marca de tiempo de alta resolución y descartar snapshots obsoletos.

**12. Sesgo de búsqueda de parámetros ("incluso el ruido puro parece bueno si buscas suficiente")** — un hallazgo cuantificado documentado en la literatura: incluso una búsqueda de parámetros **sin ninguna señal real** (ruido puro) produce Sharpes esperados de hasta ~3,7 con 1.000 combinaciones probadas al azar. Esto es la sección 1 (DSR/PBO) aplicada de forma muy concreta: nunca reportar el resultado de una búsqueda de parámetros sin aplicar la corrección correspondiente.

**13. Sesgo narrativo ("storytelling bias")** — inventar una explicación plausible y convincente **después** de encontrar un patrón casual, confundiendo correlación con causalidad. *Evitación*: la disciplina de pre-registro de la sección 8.1 — si la hipótesis no estaba escrita antes de ver el resultado, cualquier "explicación" posterior es sospechosa por definición.

**14. Costes asimétricos de apalancamiento/financiación entre largo y corto** — asumir que ir corto cuesta lo mismo que ir largo (en cripto vía margen o perpetuos, las tasas de funding pueden ser marcadamente distintas y variables según el lado y el momento; en mercados tradicionales, el corto a veces ni siquiera está disponible por falta de acciones que tomar prestadas). *Evitación*: modelar explícitamente el coste de cada lado por separado, no asumir simetría.

**15. Regímenes definidos a toro pasado** — ya cubierto en la sección 4.3, se repite aquí por su gravedad: excluir del backtest los periodos que "ya sabes" que fueron malos es survivorship bias disfrazado de sofisticación técnica.

**Nota final importante**: estos sesgos **no se suman, se multiplican**. Un backtest con survivorship bias, más un look-ahead de una barra, más coste de transacción cero, no tiene "tres pequeños sesgos" — tiene tres sesgos cuyos efectos se combinan multiplicativamente a través de toda la serie de retornos compuestos, y el resultado final puede estar inflado en un orden de magnitud, no en un simple porcentaje.

Fuentes: taxonomía completa con ejemplos: https://www.susanpotter.net/quant/backtest-bias-taxonomy/ · guía de errores de backtesting: https://hedgefundalpha.com/education/backtesting-mistakes-kill-quant-strategies-guide/ · wash trading en cripto (NBER): https://www.nber.org/system/files/working_papers/w30783/w30783.pdf · datos point-in-time: https://perspectives.refinitiv.com/future-of-investing-trading/how-to-use-point-in-time-data-to-avoid-bias-in-backtesting/ · inconsistencias de timestamp entre exchanges: https://github.com/ccxt/ccxt/issues/21783

---

## 10. PROTOCOLO DE VALIDACIÓN — checklist paso a paso, de la hipótesis al dinero real

### Fase 0 — Pre-registro (antes de tocar datos)

1. Escribe la hipótesis en una ficha fija: afirmación de mercado, variable objetivo (label), predictor(es), universo y rango temporal de datos, hipótesis nula, y criterio numérico de éxito — **todo antes de mirar ningún resultado**.
2. Registra la hipótesis con fecha y hora en el cuaderno de laboratorio (append-only; nunca se edita ni se borra a posteriori).
3. Congela físicamente las tres particiones: development, validation, holdout. El holdout se guarda aparte (otro archivo/carpeta, idealmente fuera del entorno de trabajo activo) y no se toca.

### Fase 1 — Datos

4. Usa datos lo más cercanos a point-in-time posible; documenta exchange(s) de origen y la convención de timestamp (apertura vs. cierre de vela) de cada fuente.
5. Verifica ausencia de survivorship bias (incluye pares/exchanges desaparecidos si tu universo lo requiere) y contrasta el volumen entre al menos dos fuentes para detectar wash trading.
6. Define explícitamente la política de huecos (forward-fill únicamente, nunca back-fill) y audita manualmente 5-10 huecos reales del histórico.

### Fase 2 — Etiquetado y features

7. Etiqueta con triple-barrera (o el esquema que uses) empleando solo información disponible en el instante t.
8. Si usas ML con bagging: calcula pesos por unicidad de etiquetas solapadas y usa bootstrap secuencial.
9. Si necesitas estacionariedad, usa diferenciación fraccional (mínimo `d` que pasa el test ADF) en vez de diferenciar directamente a retornos.
10. Calcula importancia de variables con MDA como mínimo (nunca solo MDI); usa SFI/CFI si sospechas variables correlacionadas.

### Fase 3 — Validación interna (sobre development)

11. Usa walk-forward (anclado y/o rodante) o purged k-fold con embargo — nunca k-fold aleatorio estándar sobre series temporales.
12. Si pruebas más de ~5-10 configuraciones, usa CPCV para obtener una **distribución** de resultados fuera de muestra, no un único número.
13. Registra en el cuaderno **todas** las configuraciones probadas, incluidas las descartadas — es el insumo obligatorio de `N` para los pasos 15-16.

### Fase 4 — Validación estadística (sobre validation)

14. Calcula el Probability of Backtest Overfitting (PBO) sobre el conjunto completo de configuraciones probadas.
15. Calcula el Sharpe Ratio Deflactado (DSR) con el `N` real de intentos, su varianza entre configuraciones, y la asimetría/curtosis de los retornos de la estrategia final.
16. Aplica el ajuste de Harvey-Liu-Zhu (haircut) usando el número acumulado de estrategias/variantes probadas en la vida del proyecto, no solo en esta sesión.
17. Corre un test de permutación Monte Carlo (¿mejor que reejecutar la lógica sobre datos barajados?); si comparas varias reglas a la vez, usa White's Reality Check o, preferiblemente, Hansen SPA.
18. Calcula intervalos de confianza con bootstrap estacionario de bloques para Sharpe y drawdown máximo.
19. Verifica que tu historial cumple la longitud mínima de backtest (MinBTL) dado el `N` de configuraciones probadas; si no la cumple, o reduces `N` en futuras rondas o consigues más historia antes de confiar en el resultado.

### Fase 5 — Costes y ejecución realista

20. Modela spread + slippage + impacto + funding con al menos el doble del coste estimado, y **repite los pasos 14-19 con ese coste**, no con coste cero.
21. Verifica que los fills asumidos son ejecutables: usa el rango OHLC completo para detectar toques de stop/objetivo (nunca solo el cierre), y aplica coste de spread/slippage sobre el precio de ejecución, no el precio teórico exacto del máximo/mínimo.
22. Si operas perpetuos, acumula el funding barra a barra durante toda la vida de la posición, no solo al cierre.
23. Si la plataforma es "sin comisión" tipo Quantfury, mide empíricamente el spread efectivo contra un feed de referencia externo — no asumas coste cero por la ausencia de una comisión visible.

### Fase 6 — Tamaño y riesgo

24. Dimensiona con Kelly fraccional (¼-½, nunca Kelly completo) sobre el edge estimado, combinado con un objetivo de volatilidad que mantenga el riesgo constante en el tiempo.
25. Si operas varios pares/activos cripto simultáneamente, trata las posiciones correlacionadas como una sola apuesta a efectos del límite de exposición total del book (asume correlación alta, 0,7-0,9, por defecto salvo evidencia sólida de lo contrario).
26. Fija de antemano un umbral de drawdown que dispare reducción de tamaño o parada (kill-switch), y verifica con el histórico disponible que el riesgo de ruina implícito está por debajo de tu objetivo (1-5%).
27. Si el histórico es corto, aplica shrinkage al edge estimado hacia un valor conservador antes de dimensionar, y prioriza el objetivo de volatilidad (más estable de estimar) sobre el Kelly puro.

### Fase 7 — Holdout (se abre una sola vez)

28. Solo cuando development, validation, costes y riesgo estén todos aprobados, se abre el holdout **una única vez**. El resultado se documenta tal cual sale, se apruebe o no la estrategia.
29. Si el holdout falla: la estrategia se descarta o se rediseña desde la Fase 0 con datos nuevos. **Nunca** se reutiliza el mismo holdout tras un ajuste — eso lo convierte en validation contaminado.

### Fase 8 — Piloto en vivo y escalado

30. Corre un piloto en real con tamaño mínimo, comparando operación a operación contra lo que el backtest habría predicho — esta es tu puerta de paridad backtest-vivo, ahora aplicada con todo el rigor estadístico previo ya superado.
31. Solo tras confirmar paridad sostenida (no solo rentabilidad puntual) se escala el tamaño gradualmente, respetando siempre los límites de exposición y drawdown de la Fase 6.
32. Repite periódicamente el PBO/DSR con cada nueva ronda de intentos: el número de configuraciones probadas sigue creciendo con el tiempo, y el listón de "esto es de verdad bueno" debe recalcularse, no quedarse congelado en la aprobación inicial.

---

*Documento elaborado a partir de fuentes primarias (SSRN, arXiv, Journal of Finance, Journal of Portfolio Management, documentación oficial de Quantfury) citadas en cada sección. Última actualización: septiembre 2026.*
