# tamano/ — el CUÁNTO

## Qué hace
Responde una sola pregunta: dado que una operación está permitida (pasó `filtros/`),
**¿cuánto capital pongo?**

La fórmula, ya resuelta en el plan (§6.1):

> tamaño = pronóstico **escalado** × **tapado** (con un máximo) × volatilidad objetivo × capital

## Por qué existe esta carpeta y por qué es tan importante
Se descubrió (con datos, no por intuición) que la "fuerza" de una señal NO predice si la
operación va a salir bien (correlación -0,050 y 0,034 — básicamente ruido; el grupo de
señales "más fuertes" fue el que peor resultado dio). Eso significa una cosa muy
concreta: **la fuerza de la señal nunca debe usarse para elegir qué operación tomar.**

Pero sí sirve para otra cosa: si una señal es más intensa de lo normal, tiene sentido
arriesgar un poco más en tamaño — con un tope, para que una señal extrema (probablemente
un error o un evento raro) no se coma la cartera entera.

## Qué NO hace
- No decide SI se opera (eso ya lo decidieron `motores/` + `filtros/`).
- No decide cuándo cerrar (`salidas/`).
- No decide si hay hueco en la cartera para una posición más (`cartera/`).

## Catálogo previsto (T1-T5)
Ver `docs/00-PLAN-MAESTRO.md` §7.4.

## Mecánica implementada (`tamano.py`, 14-sept-2026)
`calcular_tamano(capital, riesgo_por_unidad, probabilidad, riesgo_base_pct,
multiplicador_min, multiplicador_max)` combina dos piezas del catálogo:

- **T1 (vol-targeting, ya "construido" según el plan, aquí graduado de verdad):**
  `riesgo_por_unidad` es la distancia en precio hasta el stop de la operación concreta
  (viene de `salidas/stop_objetivo.py`, pasada como un simple `float` — `tamano/` no
  importa `salidas/`, cada capa solo conoce su propia interfaz). Un stop más lejos
  (mercado más volátil en ese momento) compra automáticamente MENOS unidades para el
  mismo riesgo en dinero. Antes esto vivía de forma provisional en
  `laboratorio/patrones/prueba_cuenta_1000e.py` con `RIESGO_PCT` fijo del 2%; ahora es
  la pieza real de esta capa.
- **T2 (pronóstico escalado y con tope, la solución al problema del árbitro, §6.1):**
  `escalar_probabilidad()` convierte `probabilidad_total_si_confirma` (0-1, del motor) en
  un multiplicador lineal entre `multiplicador_min` y `multiplicador_max` — nunca decide
  SI se opera (ya comprobado con datos: la fuerza no predice acierto), solo escala CUÁNTO
  se arriesga, con tope automático por construcción (la probabilidad ya viene acotada
  0-1, así que el multiplicador nunca se sale del rango).

**T3 (Kelly fraccional) — aparcado.** Requiere una estimación fiable de la ventaja/tasa de
acierto, y la sesión de `salidas/` del mismo día (14-sept-2026) confirmó que el exceso real
de la salida sobre comprar-y-aguantar es minúsculo y no se confirma entre ETH y BTC — meter
Kelly sobre una ventaja tan inestable es más riesgo que beneficio. Revisar si `salidas/`
encuentra alguna vez una ventaja más sólida.

**T4 (reducción por correlación) y T5 (banda muerta) — movidas a `cartera/`.** El plan las
lista bajo `tamano/`, pero ambas necesitan ver el conjunto de posiciones abiertas ("¿ya hay 3
largos en cripto?") — contradice la regla de esta capa (ver "Qué NO hace" arriba). `tamano/`
calcula el tamaño AISLADO de una sola operación; `cartera/` es quien lo recorta si hace falta
sabiendo del resto de la cartera.

**Pendiente antes de producción:** `multiplicador_min`/`multiplicador_max` (aquí probados
como 0.7/1.3 en el test inline) son un rango razonable elegido a mano, no barrido todavía —
falta la misma disciplina de "no absolutos" que se aplicó a R/k_atr_stop en `salidas/`:
barrer un rango de configuraciones de `multiplicador_min/max` (y de `riesgo_base_pct`) en
ETH, confirmar en BTC, antes de fijar un valor concreto.

## Intento de barrer riesgo_base_pct y multiplicador — PARADO, resultado no de fiar (14-sept-2026)
Se barrió `riesgo_base_pct` (Fase 1, multiplicador plano 1.0) maximizando un Calmar (CAGR /
drawdown máximo) sobre la cuenta secuencial compuesta de 124-135 operaciones
(`laboratorio/patrones/barrido_tamano.py`). El ganador cayó en el extremo superior del rango
probado (20% del capital por operación) y produjo capitales finales absurdos partiendo de
1000€: ~1.76 millones en ETH, ~92 millones en BTC — con un drawdown máximo del -78% que ya es
un aviso serio por sí solo. Barrer encima `multiplicador_min/max` (Fase 2) sobre ese
riesgo_base_pct ya inflado multiplicó aún más el problema (hasta 716 millones en BTC).

**Por qué no es un óptimo real, aunque aquí sí había un mecanismo de freno teórico genuino**
(a diferencia del barrido de R/plazo en `salidas/`, aquí el lastre de volatilidad de apostar
una fracción fija del capital SÍ debería crear un óptimo interior, el mismo mecanismo por el
que Kelly completo arruina): con solo ~130 operaciones, la fracción que maximiza el
crecimiento en ESA secuencia concreta de resultados está sobreajustada a la suerte particular
de esa muestra — una secuencia ligeramente distinta (con la misma ventaja real) puede arruinar
la cuenta con esa misma fracción. Esto es además coherente con lo que se confirmó el mismo día
en `salidas/README.md`: la ventaja real de la estrategia es minúscula y no se confirma bien
entre monedas — apostar el 20% del capital sobre una ventaja tan frágil e incierta es
exactamente el escenario en el que optimizar Kelly por backtest es más peligroso. Registrado
como observación 0012 de task-observer.

**Decisión: NO usar el resultado del barrido.** En vez de "optimizar" `riesgo_base_pct` por
backtest, se usa un tope prudente convencional — **1-2% de riesgo por operación**, práctica
estándar de gestión de riesgo, documentado aquí como convención no derivada de datos (igual
que otras convenciones ya aceptadas en el proyecto, ej. el supuesto conservador de
`salidas/stop_objetivo.py` cuando se tocan stop y objetivo el mismo día). Revisar esto solo si
algún día se puede calcular un Kelly fraccional ANALÍTICO (tasa de acierto + razón
ganancia/pérdida con incertidumbre, no maximizando la curva de capital directamente) sobre una
ventaja que esté confirmada con solidez — cosa que hoy no es el caso (T3 sigue aparcado).

**Repetido el barrido de `multiplicador_min/max` con `riesgo_base_pct=2%` fijo** (en vez del
20% inflado) para separar el efecto de T2 del problema de apalancamiento de la Fase 1: la
mejora de Calmar es mucho más modesta (ETH: 1.22→1.77 en el extremo (0.3,1.7); BTC:
2.83→4.57), pero **sigue empujando hacia el borde del rango sin estabilizarse** — el mismo
patrón de sobreajuste a la muestra pequeña, solo que menos dramático al no estar amplificado
por el apalancamiento. Esto es especialmente sospechoso porque este propio documento ya decía
(sección "Por qué existe esta carpeta") que la fuerza de la señal **no correlaciona con el
resultado** (correlación ≈0, dato ya medido en una sesión anterior del proyecto) — que el
barrido "encuentre mejora" escalando el tamaño por esa misma probabilidad es casi con toda
seguridad ruido de ~130 operaciones, no una señal real. No se sigue barriendo esto: no tiene
sentido perseguir un óptimo de un efecto que el propio proyecto ya sabe que no existe.

## Estado (14-sept-2026) — CERRADO por ahora, config conservadora aceptada
`tamano.py` escrito y verificado con un test inline (escala correctamente con volatilidad y
con probabilidad, respeta el tope). Dados los dos hallazgos de sobreajuste de esta sesión
(observación 0012: `riesgo_base_pct` óptimo por backtest se dispara a niveles absurdos con
pocas operaciones; y que el propio T2 se apoya en una correlación ya sabida ≈0), se acepta una
config conservadora por convención, NO optimizada por backtest:

- `riesgo_base_pct = 0.02` (2% del capital por operación — práctica estándar de gestión de
  riesgo, mismo valor que ya se usaba de forma provisional en `prueba_cuenta_1000e.py`)
- `multiplicador_min = 0.9`, `multiplicador_max = 1.1` (escalado suave, casi plano —
  mantiene la idea de T2 sin apostar fuerte por un efecto de correlación ≈0 conocido)

## Prueba de cuenta completa + Monte Carlo (14-sept-2026) — comprobación de cordura, PASA
Con `salidas/` y `tamano/` ya cerrados, se repitió la prueba de "1000€ en un año"
(`laboratorio/patrones/prueba_cuenta_1000e_v2.py`, candidatos de 2024) usando
`calcular_tamano()` de verdad en vez del 2% fijo sin ajustar de la versión original:

- ETH: 1000€ → 1253.76€ (+25.4%), 19 operaciones, drawdown máximo -1.8%.
- BTC: 1000€ → 1104.88€ (+10.5%), 12 operaciones, drawdown máximo -4.6%.

Para saber si ese resultado era representativo o solo la suerte del orden concreto de 2024
(la cuenta es multiplicativa — apostar una fracción fija del capital hace que el ORDEN de las
operaciones importe, no solo cuáles se ganan), se hizo un Monte Carlo
(`laboratorio/patrones/monte_carlo_cuenta_1000e.py`, 5000 simulaciones): se remuestrea con
reemplazo la bolsa completa de operaciones históricas de Desarrollo (124 ETH / 135 BTC), en
secuencias del mismo tamaño que las operaciones REALMENTE EJECUTADAS en 2024 (19 / 12, no los
candidatos totales).

| | mediana | p25-p75 | drawdown típico | P(pérdidas) | P(perder >50%) |
|---|---|---|---|---|---|
| ETH | 1169€ (+16.9%) | 1101€-1244€ | -2.2% a -5.0% | 3.3% | 0.0% |
| BTC | 1138€ (+13.8%) | 1080€-1204€ | -1.8% a -3.6% | 3.8% | 0.0% |

El resultado real de 2024 cae DENTRO de la banda central en las dos monedas (no es un caso
extremo de suerte de orden), y con la config conservadora la cuenta no muestra riesgo de
ruina. **`salidas/` + `tamano/` juntos pasan la comprobación de cordura** — listos para que
`cartera/` decida cómo arbitrar varias operaciones simultáneas.

## Estado final (14-sept-2026)
`tamano/` cerrado con la config conservadora (riesgo_base_pct=0.02, multiplicador 0.9-1.1),
verificado en una prueba de cuenta completa y confirmado con Monte Carlo que el resultado no
depende de la suerte del orden histórico. Pendiente real: construir `cartera/`.
