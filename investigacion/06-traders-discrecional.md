# Investigación 06 — Metodologías de trading discrecional y su evidencia

> Objetivo: convertir el conocimiento de traders discrecionales (ICT/SMC, Wyckoff, price action clásico, volumen/flujo, estructura temporal, gestión de riesgo y psicología) en hipótesis programables sobre datos OHLCV, evaluando honestamente qué evidencia empírica publicada existe detrás de cada idea.
>
> Contexto: ya se descartaron con datos propios EMAs/cruces, ADX+DI, Supertrend, roturas de resistencia simples, MACD, RSI puro, envolventes, 3 velas del mismo color, VWAP simple, Volume Profile POC aislado y estructura de mercado simple. El motivo común de fallo: "confirmar la tendencia es llegar tarde". Esta investigación busca ideas que actúen ANTES de la confirmación (liquidez, trampas, posicionamiento) o que aporten un filtro/contexto distinto (temporalidad, volumen real, gestión).

**Estado del documento:** en construcción incremental — cada sección se añade en cuanto se completa su investigación. Ver progreso en el índice.

## Índice

1. [ICT / Smart Money Concepts](#1-ict--smart-money-concepts)
2. [Wyckoff (acumulación/distribución)](#2-wyckoff-acumulacióndistribución)
3. [Price action clásico](#3-price-action-clásico)
4. [Volumen y flujo](#4-volumen-y-flujo)
5. [Estructura temporal](#5-estructura-temporal)
6. [Gestión de riesgo de traders reales](#6-gestión-de-riesgo-de-traders-reales)
7. [Psicología convertida en regla](#7-psicología-convertida-en-regla)
8. [Traders y canales concretos con metodología pública](#8-traders-y-canales-concretos-con-metodología-pública)
9. [Comunidad algo: qué funciona de verdad en 2025-2026](#9-comunidad-algo-qué-funciona-de-verdad-en-2025-2026)
10. [Las 15 hipótesis más prometedoras y programables](#10-las-15-hipótesis-más-prometedoras-y-programables)

---

## 1. ICT / Smart Money Concepts

ICT (Inner Circle Trader, Michael J. Huddleston) es la fuente de la mayoría del vocabulario "smart money" que circula hoy en YouTube (order blocks, FVG, liquidez, killzones). Es, con diferencia, la metodología discrecional más citada en foros y la que más controversia genera: en Trustpilot hay reseñas serias que acusan a Huddleston de no haber operado nunca en real y de vender "un galimatías que siempre se puede reinterpretar en retrospectiva" ([Trustpilot](https://ca.trustpilot.com/review/theinnercircletrader.com)). Dicho esto, algunos de los mecanismos subyacentes (liquidez en stops, imbalances de order flow) son observables y programables independientemente de si "ICT" es o no un vendedor de humo — lo importante es separar el envoltorio de marketing del mecanismo de mercado.

### 1.1 Fair Value Gap (FVG) / imbalance

- **Explicación llana:** cuando una vela se mueve muy rápido en una dirección, deja un "hueco" entre la sombra de la vela anterior y la de la vela siguiente que el precio no ha "negociado". La idea es que el mercado tiende a volver a rellenar ese hueco antes de continuar.
- **Definición operativa (3 velas i-2, i-1, i):**
  - FVG alcista: `low[i] > high[i-2]` (hueco entre el máximo de la vela i-2 y el mínimo de la vela i, con la vela i-1 como impulso). Zona = `[high[i-2], low[i]]`.
  - FVG bajista: `high[i] < low[i-2]`. Zona = `[high[i], low[i-2]]`.
  - Señal de entrada: primer retroceso del precio hacia el interior de esa zona tras su formación, opcionalmente exigiendo un tamaño mínimo (p. ej. gap ≥ X × ATR(14) de ese timeframe) para filtrar ruido.
- **Datos necesarios:** OHLC del timeframe operado; nada adicional.
- **Evidencia:**
  - Un backtest cuantitativo serio (StatOasis, "I Backtested ICT/SMC — What Survives") codificó reglas mecánicas de FVG, order blocks, liquidity sweeps y Optimal Trade Entry sobre SPY/QQQ/DIA/IWM (1993-2023, velas diarias, 648 backtests en total) y encontró que el FVG tuvo un edge de **-0.005%, t-stat -0.08** sobre 1122 eventos — es decir, estadísticamente indistinguible de cero. Ninguna de las 648 variantes de las 4 familias ICT batió a buy-and-hold en rentabilidad neta ([StatOasis](https://statoasis.com/overfit/research/ict-backtest-what-survives)).
  - En contraste, guías comerciales (Edgeful, Backtrex, plataformas de backtesting visual) afirman win rates de 60-70%+ cuando el FVG se filtra por: (a) dirección de la tendencia de timeframe superior, (b) tamaño del gap relativo al rango medio de vela, (c) zona de descuento/premium (retroceso Fibonacci), y (d) formación dentro de una killzone y no en sesión asiática ([Edgeful](https://www.edgeful.com/blog/posts/fair-value-gap-best-practices-guide)). Estas cifras no tienen metodología pública verificable (no publican código, muestra, ni control de curve-fitting), así que deben tratarse como marketing, no como evidencia.
  - Conclusión honesta: el FVG "puro" (sin filtros) no muestra edge en el único backtest con metodología transparente que hemos encontrado. Los filtros de "alta calidad" (tendencia + tamaño + killzone) son plausibles pero no están respaldados por estudios públicos con código y control estadístico — son afirmaciones de vendedores de cursos/indicadores.
- **Veredicto:** evidencia publicada = **negativa** (StatOasis); las variantes "filtradas" con win rate alto = **folclore/marketing sin evidencia verificable**.
- **Dificultad de programación:** baja (detección de la gap es aritmética simple sobre 3 velas).

### 1.2 Order Blocks (OB)

- **Explicación llana:** la última vela contraria antes de un movimiento impulsivo fuerte. La teoría dice que ahí es donde "el smart money" dejó órdenes sin ejecutar del todo, y que el precio volverá a esa zona para "mitigarlas" antes de continuar.
- **Definición operativa:** vela bajista (down-close) seguida, dentro de K velas, de un impulso alcista que supera M × ATR(20). El rango high-low de esa vela bajista es la zona de entrada; señal = retroceso del precio a esa zona con reacción (mecha o cierre en dirección del impulso original). Análogo para OB bajista.
- **Datos necesarios:** OHLC; ATR calculable con los mismos datos.
- **Evidencia:**
  - Mismo estudio StatOasis: order block fue la familia ICT con **mejor comportamiento relativo** (edge +0.121%, t-stat +1.22 sobre 736 eventos en SPY — no llega al umbral de significancia de t=2, pero fue la única familia que batió a entradas aleatorias en más del 50% de sus variantes en las 4 bolsas: 81.5% SPY, 66.7% DIA, 59.3% QQQ, 55.6% IWM). Aun así, **0 de 648 backtests batió a buy-and-hold** en rentabilidad neta.
  - Otros backtests de blogs de indicadores (Vestinda, Tradelybox, Alphanex, PuraVidaEdge) citan resultados dispersos: uno reporta profit factor 1.95 con solo 8 operaciones cerradas en 5 años (muestra demasiado pequeña para ser concluyente), otro reporta profit factor 1.13 con ROI anualizado de apenas 0.32% ([Vestinda](https://www.vestinda.com/academy/order-blocks-backtesting-strategies-for-high-performing-trades)). Ninguno compara contra control aleatorio riguroso salvo la metodología que ellos mismos recomiendan (probar contra zonas aleatorias ≥20 veces con semillas distintas).
- **Veredicto:** evidencia publicada = **débil pero la menos mala de ICT**: hay una señal direccional pequeña y consistente frente a azar, pero no bate al mercado ni alcanza significancia estadística formal. Tratar como "plausible con evidencia mixta", no como sistema autónomo.
- **Dificultad de programación:** media (requiere definir impulso mínimo vía ATR y ventana de confirmación K, y lógica de "mitigación" con reacción de precio).

### 1.3 Breaker Blocks y Mitigation Blocks

- **Explicación llana:** un Breaker es un order block que "falló" — el precio lo atravesó, barrió liquidez (hizo un nuevo máximo/mínimo) y luego invirtió; esa zona rota pasa a actuar como soporte/resistencia desde el lado contrario. Un Mitigation Block es similar pero sin el barrido de liquidez previo: es solo el reintento de un OB antiguo en la misma dirección del movimiento original (continuación, no reversión).
- **Definición operativa:** Breaker = OB bajista roto al alza que fue precedido de una ruptura de un swing high/low anterior (barrido de liquidez) antes de la reversión; se opera el retest de esa zona como soporte. Mitigation = retest de un OB antiguo sin ese barrido previo, operado a favor de la tendencia original.
- **Evidencia:** no se ha encontrado ningún backtest público con metodología transparente específico de breaker/mitigation blocks (solo contenido educativo de brokers e indicadores comerciales tipo LuxAlgo). Es un refinamiento de order block + liquidity sweep, así que hereda la evidencia débil-mixta de ambos componentes, pero no tiene test propio.
- **Veredicto:** **plausible pero sin evidencia propia** (combinación no testeada directamente de dos conceptos con evidencia mixta).
- **Dificultad de programación:** media-alta (requiere trackear swings, order blocks y secuencia temporal de ambos eventos).

### 1.4 Liquidity Sweep / Stop Hunt + reversión

- **Explicación llana:** el precio perfora brevemente un máximo o mínimo evidente (donde hay stops y órdenes de ruptura acumuladas), "recoge" esa liquidez, y revierte con fuerza hacia el rango anterior. La mecha larga que perfora el nivel y cierra dentro del rango es la firma visual.
- **Definición operativa:** en una ventana de N velas, si `low[i] < min(low[i-N:i-1])` pero `close[i] > min(low[i-N:i-1])` (cierre de vuelta dentro del rango) → sweep alcista, posible entrada larga en el cierre de esa vela o en la siguiente confirmación de estructura. Análogo para sweep bajista con máximos.
- **Datos necesarios:** solo OHLC.
- **Evidencia:**
  - StatOasis: liquidity sweep tuvo edge +0.119%, t-stat +0.94 sobre 547 eventos en SPY — dirección correcta pero tampoco significativo.
  - Este es, junto con order block, de los pocos conceptos ICT con **signo consistente y positivo** aunque no significativo en el único backtest riguroso disponible.
  - Es también el concepto que más se solapa con "price action clásico" (ver sección 3, stop hunt) y con literatura de microestructura de mercado (los stops son órdenes reales que sí mueven el precio cuando se disparan en cascada) — el mecanismo económico subyacente es más creíble que el de FVG.
- **Veredicto:** **plausible con evidencia mixta/débil-positiva**. Es probablemente el concepto ICT con la base económica más sólida (liquidez real = órdenes reales), aunque el backtest riguroso no encuentra significancia.
- **Dificultad de programación:** baja-media (detección de mecha + cierre de vuelta es simple; la parte difícil es decidir qué "nivel evidente" barrer — swing N-velas, máximo de sesión, máximo diario anterior, etc.).

### 1.5 Judas Swing, Killzones y Silver Bullet

- **Explicación llana:**
  - **Killzones:** ICT define ventanas horarias de alta actividad institucional: Londres (≈02:00-05:00 NY / 07:00-10:00 UTC aprox.), apertura NY (≈08:30-11:00 NY), etc. La idea es que fuera de esas ventanas el movimiento es "ruido".
  - **Judas Swing:** en la apertura de la killzone de Londres, el precio hace un movimiento falso en una dirección (barriendo el máximo/mínimo de la sesión asiática) antes de revertir en la dirección real del día.
  - **Silver Bullet:** ventana muy concreta de 1 hora (10:00-11:00 hora de Nueva York) en la que se busca una entrada tras un barrido de liquidez + FVG en la killzone de NY.
- **Definición operativa:** requiere (a) definir rango de la sesión asiática (ej. 00:00-07:00 UTC), (b) detectar barrido del máximo/mínimo de ese rango durante la ventana de Londres (07:00-10:00 UTC), (c) confirmar reversión de estructura (cierre de vuelta + swing invalidado) para entrar en la dirección contraria al barrido. Silver Bullet es análogo pero anclado a la ventana horaria de NY y exige un FVG reciente.
- **Datos necesarios:** OHLC intradía con timestamp en UTC fiable; en cripto hay que decidir qué "sesión asiática" usar ya que el mercado cotiza 24/7 (normalmente se usa igualmente el horario de Tokio/Londres/NY por convención, aunque su justificación institucional es más débil que en forex/futuros de acciones donde sí hay cierre real de mercados).
- **Evidencia:** no se ha encontrado ningún backtest público con metodología transparente de Judas Swing o Silver Bullet. Todo el material encontrado es educativo/comercial (LuxAlgo, Backtrex, ForexBee, FXNX) sin cifras de backtest verificables ni código. Es, de los conceptos ICT, el que más depende de que existan sesiones de mercado reales con aperturas y cierres — en cripto (24/7, sin campana de apertura) el fundamento institucional original (bancos/instituciones fijando posiciones en horario de oficina) es más débil, aunque en la práctica sí se observa que el volumen y la volatilidad de BTC varían con las sesiones de Londres/NY por la actividad de traders institucionales que sí operan en esos husos horarios.
- **Veredicto:** **folclore / plausible sin evidencia propia**. El componente horario (sección 5) sí tiene algo de base estadística observable (volatilidad por sesión), pero la mecánica específica "Judas Swing → Silver Bullet" no tiene test público.
- **Dificultad de programación:** media (la lógica horaria y de barrido es sencilla; lo laborioso es la calibración de qué ventanas usar en cripto 24/7).

### 1.6 Optimal Trade Entry (OTE) — retroceso Fibonacci 61.8-78.6%

- **Explicación llana:** tras un cambio de estructura (BOS/CHoCH), se espera un retroceso a la zona 61.8%-78.6% del último swing antes de que continúe el movimiento, y se entra ahí.
- **Definición operativa:** identificar swing leg (punto A a punto B), calcular niveles Fibonacci del retroceso, entrar cuando el precio toca la banda 61.8-78.6% con confirmación de reacción.
- **Evidencia:** StatOasis: edge -0.028%, t-stat -0.17 sobre 206 eventos — el peor de las 4 familias ICT testeadas, y "nunca batió a entradas aleatorias en SPY ni una sola vez" entre sus variantes. Es, con datos, el concepto ICT con **peor evidencia** de los cuatro testeados.
- **Veredicto:** **evidencia publicada negativa**.
- **Dificultad de programación:** baja (Fibonacci es aritmética directa), pero la evidencia desaconseja usarlo como señal aislada.

---

## 2. Wyckoff (acumulación/distribución)

Richard Wyckoff (años 1930) es el origen intelectual de buena parte del vocabulario "smart money" moderno (de hecho ICT toma prestados varios conceptos de Wyckoff sin siempre citarlo). La premisa es que los grandes operadores acumulan posiciones en rango antes de una tendencia y distribuyen antes de la caída, dejando huellas en precio y volumen.

### 2.1 Estructura general: rango de acumulación/distribución (Fases A-E)

- **Explicación llana:** el mercado no pasa de tendencia a tendencia directamente; primero "descansa" en un rango donde los grandes compran (acumulación) o venden (distribución) sin mover mucho el precio. Wyckoff divide ese rango en fases: A (para la tendencia previa: preliminary support/supply + clímax de venta/compra), B (construcción del rango, tests múltiples), C (prueba final — spring o upthrust), D (movimiento dentro del rango hacia el lado opuesto, rompiendo la línea del canal), E (salida del rango, tendencia visible).
- **Definición operativa:** requiere detectar (1) un rango lateral con soportes/resistencias relativamente estables durante N barras, (2) un evento de clímax (vela de rango/volumen muy superior a la media) en el extremo del rango, (3) una fase C con penetración del extremo (spring/upthrust, ver 2.2), (4) confirmación de fase D con ruptura del rango en la dirección esperada y volumen creciente.
- **Datos necesarios:** OHLCV — el volumen es imprescindible aquí, a diferencia de ICT que puede prescindir de él.
- **Evidencia:** no existe ningún backtest público con metodología transparente de "Wyckoff completo" (las 5 fases) que hayamos podido encontrar. El propio material técnico (LuxAlgo, TradingWyckoff de Rubén Villahermosa) reconoce que "el método Wyckoff a menudo sufre de claridad retrospectiva: muchos patrones solo se vuelven evidentes en retrospectiva, después de que el mercado ya ha hecho un movimiento decisivo" — es decir, la propia comunidad admite el sesgo de mirar hacia atrás. Los recursos recomiendan registrar manualmente fase llamada, eventos observados e invalidación para "convertir el marco subjetivo en algo medible", lo que confirma que **no hay evidencia cuantitativa publicada**, solo un método para empezar a generarla uno mismo.
- **Veredicto:** **plausible pero sin evidencia publicada**. La estructura de "rango antes de tendencia" es real y observable, pero el esquema completo de 5 fases es demasiado ambiguo para backtest directo sin una capa de reglas propia muy estricta (alto riesgo de overfitting/curve-fitting al definir "fase C" a posteriori).
- **Dificultad de programación:** alta (requiere detección robusta de rango, clasificación de clímax, y secuenciación temporal de eventos — mucho más subjetivo que ICT).

### 2.2 Spring y Upthrust (el componente más programable de Wyckoff)

- **Explicación llana:** el Spring es una falsa ruptura a la baja del soporte de un rango (sacude a los que tienen stop-loss ahí) seguida de una recuperación rápida con poco volumen vendedor — señal de que "no había papel para vender" y el suelo es sólido. El Upthrust es el espejo al alza.
- **Definición operativa (con volumen, la más precisa encontrada en esta investigación):**
  1. Definir rango previo con soporte S (mínimo estable durante ≥N velas).
  2. Detectar penetración: `low[i] < S`, con profundidad de penetración clasificable (tipo 2: 1-3% bajo soporte con volumen moderado; tipo 1/"terminal shakeout": >3% de penetración con volumen muy expandido).
  3. Exigir que el volumen de la vela de penetración **no** sea extremo respecto al de rupturas reales (paradójicamente, un volumen bajo-moderado en la ruptura es la señal de fortaleza, no de debilidad).
  4. Exigir un "test" posterior: nueva aproximación al mínimo del spring con volumen aún más bajo (reducción del 40-60% respecto al volumen de la penetración, o <50% del volumen del shakeout en el caso tipo 1).
  5. Regla de invalidación explícita: si el test se hace con volumen alto (>80% del volumen del spring), con expansión de rango, o si el precio vuelve a perforar el mínimo del spring con cierre por debajo, la probabilidad de fallo sube de 20-25% a 55-70% (cifras de guías educativas de Wyckoff, no de un paper académico independiente — tratar como heurística de la comunidad, no como estadística verificada).
  6. Entrada: en la confirmación del test (vela con reacción alcista y volumen menor), stop bajo el mínimo del spring.
- **Datos necesarios:** OHLCV — imprescindible tener volumen real y fiable (en cripto, el volumen del exchange usado, con los problemas conocidos de wash trading en algunos exchanges de futuros perpetuos — usar preferiblemente volumen de spot de exchanges líquidos tipo Binance/Coinbase).
- **Evidencia:** el propio material (LuxAlgo) reconoce que "no ofrece validación estadística" y que "un spring es evidencia de que la oferta era débil en ese momento, no una garantía de subida" — es honesto sobre su naturaleza probabilística no cuantificada. Las cifras de "20-25% vs 55-70% de fallo" no tienen fuente académica identificada, son heurísticas de comunidad. No hemos encontrado ningún backtest independiente de Spring/Upthrust con código y muestra pública.
- **Veredicto:** **plausible con lógica de mercado sólida (barrido de liquidez + confirmación de volumen) pero sin evidencia cuantitativa publicada e independiente**. Es, de todo Wyckoff, el concepto más operacionalizable porque tiene condiciones de precio Y volumen relativamente objetivas.
- **Dificultad de programación:** media (spring básico sin clasificación por tipos) a alta (con clasificación de tipos y test de volumen relativo).

### 2.3 Relación Wyckoff ↔ ICT

Vale la pena señalar que el Spring de Wyckoff y el Liquidity Sweep de ICT (sección 1.4) son esencialmente el mismo fenómeno de mercado descrito con vocabulario distinto: ambos son "ruptura falsa de un nivel + reversión". Esto es relevante para la programación: en vez de tratar "ICT" y "Wyckoff" como sistemas separados, tiene sentido programar **un solo detector de barrido de liquidez con confirmación de volumen decreciente**, que capture el mecanismo común a ambas escuelas. Esto también reduce el riesgo de estar re-descubriendo la misma idea con dos nombres y contándola como "dos hipótesis" cuando es una.

---

## 3. Price action clásico

### 3.1 Soportes/resistencias y retesteo de rotura

- **Explicación llana:** un nivel donde el precio ha rebotado varias veces se convierte en una referencia; cuando se rompe, se espera que el precio vuelva a tocarlo desde el otro lado (retest) antes de continuar, y ese retest es el punto de entrada de menor riesgo.
- **Definición operativa:** (1) identificar niveles con ≥2 toques previos (pivotes locales dentro de una tolerancia en %); (2) ruptura = cierre más allá del nivel por un margen mínimo (evita rupturas de mecha); (3) retest = el precio vuelve a la zona del nivel roto (± tolerancia) dentro de M velas tras la ruptura; (4) confirmación = vela de rechazo en el retest (mecha en dirección contraria al retest, o cierre que respeta el nivel).
- **Datos necesarios:** solo OHLC.
- **Evidencia:** esta es, honestamente, la categoría con **peor respaldo cuantitativo verificable** de todas las investigadas, pese a ser la más enseñada. Rayner Teo (canal "Trading with Rayner", uno de los educadores de price action más seguidos en YouTube, cientos de miles de suscriptores) admite explícitamente en su propio blog: *"es muy difícil hacer un backtest de esto porque, seamos honestos, el soporte y la resistencia son subjetivos"* ([Trading with Rayner](https://www.tradingwithrayner.com/the-truth-about-support-and-resistance/)) — no aporta ninguna cifra de backtest, solo observaciones anecdóticas (niveles testeados repetidamente se debilitan, los niveles "dormidos" mucho tiempo ganan importancia, ruptura de soporte se convierte en resistencia). Es una confesión honesta y poco común en el gremio: el propio gurú del price action dice que su concepto central no es backtesteable tal cual se enseña.
  - Un artículo de Quora (fuente no académica pero ilustrativa) de un trader que sí backtesteó soporte/resistencia con ruptura reporta **40% de win rate con ratio riesgo/beneficio 1:1.5** — rentable si se sostiene esa relación, pero muy lejos de la "alta probabilidad" que promete el marketing de price action.
  - Existe literatura académica antigua (Murphy 1999, Edwards & Magee 2001) que establece las bases teóricas pero sin backtests estadísticos modernos rigurosos con control de curve-fitting; hay papers más recientes (p. ej. en jesd-online.com sobre mercados internacionales) pero no pudimos verificar su contenido completo por restricciones de acceso al PDF en esta sesión.
- **Veredicto:** **folclore con un núcleo plausible**. El fenómeno de "nivel + retest" tiene lógica de comportamiento (memoria de precio, órdenes residuales, breakeven-seekers) pero la variante "clásica" tal como se enseña en YouTube no tiene evidencia cuantitativa pública sólida — ni siquiera sus principales divulgadores la reclaman. Es exactamente el tipo de concepto que "confirma tarde" (hay que esperar ruptura + retest + confirmación, 3 eventos secuenciales) y coincide con el motivo de fallo que el usuario ya identificó en sus pruebas previas.
- **Dificultad de programación:** media (detección de niveles y toques es directa; la parte subjetiva — "zona" vs "línea", tolerancias — introduce muchos grados de libertad que facilitan el overfitting).

### 3.2 Dobles suelos/techos y extremos de rango

- **Explicación llana:** el precio toca dos veces (aprox.) el mismo nivel sin lograr superarlo/perforarlo, formando una "M" (doble techo) o una "W" (doble suelo); se interpreta como agotamiento de la tendencia.
- **Definición operativa:** dos máximos (o mínimos) locales dentro de una tolerancia en % entre sí, separados por un mínimo (o máximo) intermedio que retrocede al menos X% desde el primer pico, en una ventana de N velas; entrada en ruptura del mínimo/máximo intermedio ("neckline") con cierre.
- **Evidencia (VERIFICADO 8-sept-2026, vía WebSearch):** Lo, Mamaysky & Wang (2000, "Foundations of Technical Analysis", NBER/Journal of Finance) sí encontraron contenido informativo estadístico en patrones chartistas clásicos (incl. dobles techos/suelos, hombro-cabeza-hombro) sobre acciones de EE.UU. 1962-1996, usando reconocimiento no paramétrico. **Pero el estudio de seguimiento con la misma metodología** (Savin et al., *Journal of Financial Econometrics*, "Predictive Power of Head-and-Shoulders Price Patterns") aplicado a S&P 500/Russell 2000 1990-1999 encontró **"poco o ningún apoyo a la rentabilidad de una estrategia independiente"** — la señal estadística no se traduce en ventaja operable. Un estudio de fallos sobre ~14.000 patrones (1991-2008) encontró que la tasa de fallo **subió con el tiempo** (26% en los 90 → 49% en 2003-2007), consistente con un patrón que se desgasta según se vuelve más conocido. Búsqueda adicional sobre cripto (8-sept-2026): un estudio sobre datos tempranos de Bitcoin (Mt.Gox) encontró asociación entre uso de chart patterns y retornos, pero otro estudio más reciente encontró que **estrategias técnicas rentables antes de dic-2021 generalmente dejaron de funcionar después, especialmente ajustando por data snooping** — mismo mecanismo de desgaste.
- **Confirmado con datos propios (corvus4, 8-sept-2026):** hombro-cabeza-hombro invertido, probado en BTC 2020-2024 con detección causal por pivotes, descartado tras barrido de 25 configuraciones + prueba de baseline (mejor combo p=0,417) — con decaimiento por año que reproduce exactamente el patrón de "tasa de fallo creciente" de la literatura. Doble suelo y doble techo, en cambio, SÍ mostraron ventaja robusta en BTC solo (ver `docs/reverificacion.md` §2b y §2a-bis.2) — la diferencia parece estar en la confirmación adicional (volumen para suelo, filtro de tendencia bajista estricta para techo), no en el patrón geométrico puro.
- **Veredicto:** confirmado — el patrón geométrico puro (sin confirmación adicional) no tiene ventaja operable fiable, ni en la literatura de acciones ni en BTC. Con confirmación adicional (volumen, régimen), sí puede funcionar (ver doble suelo/techo).
- **Dificultad de programación:** media (similar a S/R, con parámetros de tolerancia que invitan a overfitting).

### 3.2-bis Triángulo ascendente y taza con asa (VERIFICADO 8-sept-2026)

Búsqueda específica de evidencia rigurosa para estos dos patrones (siguientes en la cola del catálogo de corvus2, `docs/catalogo_patrones.md`, marcados "alta/media prioridad" sin verificar en su momento). **No se encontró ningún estudio académico o backtest con metodología pública transparente para ninguno de los dos** — solo contenido de blogs de indicadores comerciales (LuxAlgo) y posts individuales de traders (Medium, "mi patrón con mejor win-rate de 16 patrones que detecto"), sin código ni muestra verificable. Mismo patrón que soporte/resistencia y order blocks: mucho marketing, cero evidencia independiente. **No se recomienda darles prioridad alta hasta que aparezca mejor indicio** — degradados a la misma categoría que S/R.

### 3.3 Stop hunt y reversión (fuera del vocabulario ICT)

Ver sección 1.4 (Liquidity Sweep) — es el mismo mecanismo. La diferencia es que en price action clásico se enseña sin el aparato conceptual de "smart money" y se ancla más a niveles obvios (máximo/mínimo del día anterior, máximo/mínimo semanal, redondos psicológicos tipo 100,000 en BTC) en lugar de "pools de liquidez" abstractos. Programáticamente es idéntico: detectar mecha que perfora un nivel de referencia + cierre de vuelta dentro. La única diferencia real está en qué nivel de referencia se usa — y eso sí es testeable comparando distintos niveles de referencia (ver sección 5, PDH/PDL).

### 3.4 Gap del fin de semana / CME gap (cripto)

- **Explicación llana:** el futuro de Bitcoin en CME (regulado, EE.UU.) cierra los fines de semana mientras el spot de cripto sigue cotizando 24/7. Si el precio se mueve el fin de semana, el CME "abre" el lunes con un hueco en su gráfico frente al cierre del viernes. La creencia es que ese hueco tiende a "rellenarse".
- **Definición operativa:** `gap = open_CME_lunes - close_CME_viernes`; señal = sesgo hacia el precio de cierre del viernes hasta que el precio de spot lo toque ("gap filled"). Es aplicable indirectamente al spot de BTC usando el nivel de precio del cierre del viernes en CME como imán.
- **Evidencia:** cifras dispersas y contradictorias según la fuente: ~77% de los gaps de CME en BTC acaban rellenándose según una fuente, 70-90%+ según otras, ~95-98% según otras más agresivas ([TradingView News](https://www.tradingview.com/news/cointelegraph:9d1ce1efd094b:0-what-bitcoin-cme-gaps-are-and-how-they-influence-price-movements/), [Phemex](https://phemex.com/academy/cme-futures-gap), [Whaleportal](https://whaleportal.com/blog/bitcoin-cme-gaps-and-cme-trading-strategy-explained/)). Ninguna de estas fuentes es un backtest con metodología pública citable (código, muestra exacta, período exacto) — son artículos de blogs de exchanges/educadores citándose unos a otros sin fuente primaria clara. La dispersión tan amplia (77% a 98%) es en sí misma una señal de alarma: sugiere que nadie ha hecho la medición con una definición operativa fija y reproducible, cada uno mide "relleno" de forma distinta (¿toca el nivel exacto? ¿en cuánto tiempo? ¿se cuenta el gap si el precio ya iba en esa dirección de todas formas?).
  - Un caso real reciente: en julio de 2025 un gap de $1,770 tardó más de 16 horas en rellenarse, descrito como "raro" — lo que sugiere que en la mayoría de los casos el relleno es rápido (horas), pero no hay cifra fiable de "cuánto tiempo tarda en media" ni de qué % del movimiento post-apertura es explicado por el gap vs. por tendencia general del mercado ese día.
  - Comparado 1 septiembre 2025 en adelante: la nota "Bitcoin's First CME Gap-Free Monday Puts a Popular Trading Signal to the Test" ([Yahoo Finance](https://finance.yahoo.com/markets/crypto/articles/bitcoin-first-cme-gap-free-174649486.html)) sugiere que la propia prensa financiera trata la señal con escepticismo cuando no hay gap que rellenar, sin que eso cambie la narrativa alcista/bajista de fondo.
- **Veredicto:** **plausible pero con evidencia poco rigurosa/inconsistente entre fuentes** — el fenómeno de "el precio tiende a volver a niveles de referencia tras un movimiento de baja liquidez (fin de semana)" es económicamente razonable (el fin de semana en cripto tiene menos profundidad de book y más manipulabilidad), pero las cifras concretas de "% de relleno" que circulan no son fiables ni reproducibles con la información disponible. Es fácilmente testeable con datos propios: se recomienda backtestear directamente en vez de fiarse de cifras de blogs.
- **Dificultad de programación:** baja (el gap es un simple cálculo de diferencia de precios entre cierre de viernes y apertura de lunes; requiere datos de CME BTC futures además del spot, o aproximarlo con el propio spot si no se tiene acceso a CME).

---

## 4. Volumen y flujo

Nota importante: el usuario ya descartó VWAP simple (de sesión, sin anclar) y Volume Profile POC aislado. Esta sección se centra en las variantes que NO se han probado todavía: VWAP anclado a un evento, VAH/VAL/HVN/LVN (en vez de solo el POC), y el flujo de órdenes (delta/CVD/absorción), que son conceptualmente distintos de lo ya descartado.

### 4.1 VWAP anclado (Anchored VWAP)

- **Explicación llana:** el VWAP normal se calcula desde la apertura de sesión/día y se reinicia cada día — eso ya lo probó el usuario y falló. El VWAP **anclado** en cambio se calcula desde un evento significativo específico (un máximo/mínimo importante, el inicio de una tendencia, una noticia, el listado de un activo) y NO se reinicia — se mantiene corriendo desde ese punto de anclaje indefinidamente. La idea es que representa el "precio medio pagado por todo el que entró desde ese evento", y actúa como referencia de si los que compraron/vendieron desde ese punto están en ganancia o pérdida agregada.
- **Definición operativa:** `AVWAP[t] = Σ(precio_tipico[i] × volumen[i]) / Σ(volumen[i])` para `i` desde el índice de anclaje hasta `t`. El punto de anclaje se elige por regla objetiva (no discrecional) para que sea programable: ej. "el mínimo/máximo del último swing mayor de N velas", "la vela de mayor volumen de los últimos M días", "el inicio de la semana/mes/trimestre". Señal: reacción del precio al tocar el AVWAP (rechazo = continuación de tendencia; cruce con cierre = posible cambio de régimen).
- **Datos necesarios:** OHLCV.
- **Evidencia:** el AVWAP es la herramienta insignia de Brian Shannon (@AlphaTrends, autor de "Technical Analysis Using Multiple Timeframes"), uno de los pocos divulgadores de price action con metodología pública consistente y sin vender señales — pero no publica backtests estadísticos formales de su AVWAP, solo casos de estudio ilustrativos en su blog/libro. No se ha encontrado ningún backtest académico o cuantitativo independiente de AVWAP anclado a swings en esta sesión (búsqueda limitada por el tope de WebSearch alcanzado; se intentó vía WebFetch sin éxito por bloqueo de Investopedia).
  - Diferencia clave frente al VWAP de sesión que ya falló: el VWAP de sesión se reinicia cada día y en timeframes intradía de cripto (mercado 24/7 sin apertura real) pierde bastante sentido conceptual — no hay "apertura institucional" que ancle nada. El AVWAP anclado a eventos reales de precio (swing high/low, vela de volumen extremo) sí tiene una justificación económica distinta: mide el coste medio real de los participantes desde un punto de inflexión conocido, independientemente de convenciones horarias arbitrarias. Esto lo hace conceptualmente diferente de lo ya descartado, aunque comparte la fórmula base.
- **Veredicto:** **plausible pero sin evidencia publicada independiente** — mecanismo económico razonable (nivel de coste medio agregado), popularizado por un practicante serio y no vendedor de señales, pero sin backtest público verificable encontrado.
- **Dificultad de programación:** baja-media (la fórmula es simple; lo no trivial es la regla objetiva de selección del ancla, que debe fijarse de antemano para evitar look-ahead/curve-fitting al elegir el punto "bonito" a posteriori).

### 4.2 Volume Profile: VAH/VAL y HVN/LVN (más allá del POC)

- **Explicación llana:** en vez de mirar solo el precio con más volumen negociado (POC, ya descartado), se mira la "zona" donde se concentró el 70% del volumen (Value Area, entre VAH y VAL) y los huecos de bajo volumen (LVN) frente a las zonas de alto volumen (HVN). La intuición operativa es distinta a la del POC aislado: los LVN son zonas que el precio "atravesó rápido" (poco consenso, poca fricción) y por tanto se esperan movimientos rápidos cuando el precio vuelve a cruzarlos; los HVN son zonas de "aceptación" donde el precio tiende a pararse o rotar.
- **Definición operativa:** construir el perfil de volumen por niveles de precio (agrupando el rango en N bins) sobre una ventana de referencia (sesión, semana, o "desde el último evento estructural"); VAH/VAL = límites del rango de precio que contiene el 70% del volumen total, calculado añadiendo iterativamente los bins de mayor volumen alrededor del POC hasta alcanzar el umbral; LVN = bins con volumen por debajo de un percentil bajo (ej. percentil 20) dentro del perfil; HVN = bins por encima de un percentil alto (ej. percentil 80). Señal: rechazo en VAH/VAL (reversión a la media dentro del área de valor) vs. aceleración al cruzar un LVN (menor fricción = movimiento más rápido y con menos reversión).
- **Datos necesarios:** OHLCV con volumen fiable; idealmente volumen intradía granular (velas de 1-15 min) para construir el perfil con resolución suficiente incluso si la señal final se opera en un timeframe mayor.
- **Evidencia:** la propia fuente consultada (LuxAlgo, que documenta el concepto de forma neutral) es explícita: "el perfil describe el pasado, no predice la reacción" y advierte que "muchos POCs 'desnudos' (no revisitados) se quedan sin tocar durante meses o para siempre" — es decir, la propia comunidad que promueve la herramienta reconoce su naturaleza puramente descriptiva, no predictiva, y desmiente la creencia popular de que "todo POC se rellena". No se ha encontrado ningún backtest cuantitativo independiente de VAH/VAL/HVN/LVN con metodología pública.
- **Veredicto:** **plausible pero sin evidencia publicada**, y con una advertencia explícita de la propia comunidad de que la lectura ingenua ("el precio siempre vuelve al POC/value area") es falsa. El concepto de LVN como "zona de aceleración" es el único sub-componente con lógica de mercado razonablemente distinta de lo ya probado (POC como imán), y merece testeo propio aislado del POC.
- **Dificultad de programación:** media (construir el perfil correctamente, con bins y umbral de 70%, es más laborioso que un simple POC).

### 4.3 Delta / CVD (Cumulative Volume Delta) y absorción

- **Explicación llana:** en vez de mirar solo cuánto volumen se negoció, se intenta estimar **quién agredió el precio**: volumen ejecutado al "ask" (comprador agresivo, sube el precio) vs. al "bid" (vendedor agresivo, baja el precio). El Delta es la diferencia bar a bar; el CVD es la suma acumulada de esos deltas desde un punto de anclaje. La "absorción" es cuando hay mucha presión vendedora agresiva (delta muy negativo) pero el precio NO baja — interpretado como que hay un comprador pasivo grande "absorbiendo" toda esa venta, señal de posible reversión al alza.
- **Definición operativa:**
  - Sin datos de trades/order book reales: se aproxima el delta por vela usando la posición del cierre dentro del rango de la vela (`delta_aprox = volumen × (2×(close-low)/(high-low) - 1)`) — es una aproximación burda, no el delta real de microestructura.
  - Con datos de trades (tick data) o velas de menor timeframe (ej. reconstruir delta de 1h a partir de velas de 1 min): delta real = Σ volumen de trades ejecutados al ask − Σ volumen de trades ejecutados al bid, dentro de la vela.
  - CVD(t) = CVD(t-1) + delta(t), con reseteo opcional en anclas (día, semana, evento).
  - Señal de absorción: delta fuertemente negativo (percentil bajo) en una vela cuyo rango de precio es estrecho y/o cuyo cierre no hace nuevo mínimo → posible absorción compradora (y viceversa para absorción vendedora).
  - Señal de divergencia: precio hace nuevo máximo/mínimo pero el CVD no lo confirma (no hace nuevo máximo/mínimo en paralelo) → advertencia de posible agotamiento, "necesita confirmación de precio, no es señal autónoma" (cita textual de la fuente consultada).
- **Datos necesarios:** esto es la limitación clave — el CVD/delta **real** requiere datos de trades individuales (tick data) con dirección agresora, o al menos velas de un timeframe mucho menor que el operado para reconstruirlo con aproximación razonable. Con solo velas OHLCV del timeframe objetivo, solo se puede usar la aproximación burda basada en la posición del cierre, que es mucho menos fiable. Para BTC esto es viable (hay APIs de exchanges como Binance que dan trades históricos o al menos velas de 1s/1m durante varios años), pero es un salto de complejidad de datos frente a todo lo demás en este documento.
- **Evidencia:** la fuente consultada (LuxAlgo) es explícita: "el documento no contiene datos estadísticos, backtests ni evidencia empírica que respalde la fiabilidad predictiva del CVD. Presenta marcos de aplicación sin métricas de rendimiento cuantificadas." No se ha encontrado ningún backtest público e independiente de CVD/delta/absorción con metodología transparente.
- **Veredicto:** **plausible (mecanismo de mercado real: order flow SÍ mueve el precio) pero sin evidencia publicada**, y con el añadido de que requiere una capa de datos (tick/trades) que no todos los pipelines de backtest tienen montada. Es de los conceptos con **mejor fundamento microestructural teórico** de todo el documento (a diferencia de FVG/OTE que son patrones geométricos sin mecanismo económico claro, el delta SÍ mide flujo de órdenes real), pero también el más caro de implementar correctamente.
- **Dificultad de programación:** alta si se quiere el delta real (pipeline de datos de trades); media si se acepta la aproximación burda por posición del cierre (pero entonces la señal es más ruidosa y se parece más a un oscilador de volumen normal que a "order flow" de verdad).

### 4.4 Resumen de la sección: qué es testeable y qué no

| Concepto | ¿Necesita datos más allá de OHLCV de velas? | Fundamento económico | Evidencia |
|---|---|---|---|
| VWAP de sesión (ya descartado) | No | Débil en cripto 24/7 | — |
| Volume Profile POC (ya descartado) | Volumen por precio | Débil-descriptivo | — |
| AVWAP anclado a evento | No (solo volumen de vela) | Medio (coste medio agregado) | Sin evidencia publicada, sin vendedor de señales detrás |
| VAH/VAL/HVN/LVN | Volumen por precio (perfil) | Medio-descriptivo | Sin evidencia; comunidad admite que es descriptivo, no predictivo |
| Delta/CVD aproximado (por cierre) | No | Débil (aproximación burda) | Sin evidencia |
| Delta/CVD real | Sí, trades/tick data | Fuerte (order flow real) | Sin evidencia publicada encontrada, pero mecanismo más creíble |

---

## 5. Estructura temporal

Esta sección es distinta de las anteriores en un sentido importante: no describe un patrón de precio, sino un **filtro de contexto** (cuándo operar / cuándo no) que puede combinarse con cualquiera de los patrones de las secciones 1-4. Es plausible que sea más valioso como filtro que como señal por sí solo.

### 5.1 Sesiones: Asia / Londres / Nueva York

- **Explicación llana:** aunque BTC cotiza 24/7, el volumen y la volatilidad no se reparten uniformemente durante el día. La actividad institucional (fondos, mesas de trading, desks de exchanges regulados) se concentra en horario de oficina de Asia, Europa y EE.UU., y el solapamiento Londres-NY suele ser la ventana de mayor volumen y rango.
- **Definición operativa (convención habitual, en UTC):** Asia ≈ 00:00-08:00 UTC (Tokio/Singapur/Hong Kong), Londres ≈ 07:00-16:00 UTC, Nueva York ≈ 13:00-22:00 UTC. Solapamiento Londres-NY ≈ 13:00-16:00 UTC. Se puede medir directamente sobre datos propios: ATR o rango medio por hora del día, volumen medio por hora del día, y comparar. Esto es 100% verificable con los propios datos históricos de BTC del usuario sin depender de ninguna fuente externa.
- **Datos necesarios:** OHLCV con timestamp fiable en UTC; no requiere nada más.
- **Evidencia:** este es un fenómeno bien documentado de forma consistente entre múltiples fuentes de mercado (exchanges, mesas de trading) para cripto, aunque en esta sesión no se pudo completar una búsqueda específica con estadísticas exactas por el límite de WebSearch alcanzado. Es, sin embargo, el tipo de afirmación que el propio proyecto puede verificar directamente y de forma barata con los datos OHLCV que ya tiene descargados (agrupar por hora UTC y calcular ATR/volumen medio) — se recomienda **verificarlo empíricamente con los propios datos antes de asumirlo**, en vez de fiarse de ninguna fuente externa.
- **Veredicto:** **plausible, con mecanismo económico razonable (actividad humana/institucional real), pero pendiente de verificación directa con datos propios** — no se marca como "evidencia publicada" porque no se pudo re-verificar una fuente concreta en esta sesión, pero es la hipótesis más barata de testear de todo el documento (no requiere backtest de estrategia, solo estadística descriptiva).
- **Dificultad de programación:** muy baja (agrupar por hora del día es una línea de pandas).

### 5.2 Primera hora de sesión / apertura

- **Explicación llana:** el primer tramo tras la apertura de una sesión importante (Londres, NY) suele concentrar volumen y, según varias escuelas (ICT con el "Judas Swing", pero también price action clásico independiente de ICT), un movimiento inicial "falso" que se revierte antes del movimiento real del día.
- **Definición operativa:** definir rango de los primeros K minutos/velas tras la apertura de la sesión; señal = ruptura de ese rango inicial seguida de reversión (ver 1.5 y 3.3, mismo mecanismo de barrido aplicado a un rango más corto y específico).
- **Evidencia:** el concepto de "opening range breakout" (ORB) es clásico de futuros y acciones (con décadas de literatura, incluyendo su uso por Toby Crabel en los años 90 sobre futuros) — pero de nuevo no se pudo verificar con una búsqueda específica de cripto en esta sesión. Es plausible que en cripto, sin campana de apertura real, el efecto sea más débil que en acciones/futuros regulados donde sí hay un cierre nocturno real que genera acumulación de órdenes.
- **Veredicto:** **plausible pero no verificado en esta sesión; con antecedente histórico fuera de cripto (ORB en futuros/acciones)**.
- **Dificultad de programación:** baja.

### 5.3 Cierre diario / semanal y fin de semana en cripto

- **Explicación llana:** el cierre de vela diaria (00:00 UTC convención habitual) y semanal (domingo/lunes 00:00 UTC) se usan como niveles de referencia (máximo/mínimo del día o semana anterior). El fin de semana en cripto es distinto de otros mercados porque no hay cierre real, pero sí una caída de liquidez notable (los desks institucionales y muchos fondos reducen actividad, dejando el mercado más en manos de retail y bots), lo que históricamente se asocia a mechas más largas y movimientos más erráticos.
- **Definición operativa:** PDH/PDL (previous day high/low) y PWH/PWL (previous week high/low) como niveles de referencia para barridos de liquidez (ver 3.3); "efecto fin de semana" medible directamente comparando volatilidad/rango realizado sábado-domingo vs. resto de la semana en los propios datos.
- **Evidencia:** no se pudo completar la búsqueda específica de "PDH/PDL backtest" por el límite de WebSearch alcanzado a mitad de esta sección de la investigación. Es, igual que 5.1, una hipótesis barata de verificar directamente con los datos propios (comparar ATR/rango de sáb-dom vs. resto de la semana) antes de construir ninguna estrategia sobre ella.
- **Veredicto:** **plausible, pendiente de verificación directa con datos propios**.
- **Dificultad de programación:** muy baja (cálculo de niveles de día/semana anterior es trivial con OHLCV diario/semanal agregado desde velas menores).

### 5.4 Vencimiento de opciones Deribit (viernes 08:00 UTC) y vencimiento CME

- **Explicación llana:** Deribit concentra la mayoría del interés abierto en opciones de BTC/ETH, con vencimiento semanal los viernes a las 08:00 UTC (y vencimientos mensuales/trimestrales más grandes el último viernes de mes/trimestre). La teoría del "efecto pin" o "max pain" dice que los creadores de mercado, al cubrir (hedgear) su exposición delta cerca del vencimiento, empujan el precio hacia el strike donde más opciones expiran sin valor, reduciendo la volatilidad justo antes del vencimiento.
- **Definición operativa:** requiere datos de open interest por strike de Deribit (API pública de Deribit lo ofrece) para calcular el "max pain point" (strike que minimiza el valor total de las opciones in-the-money al vencimiento); señal = sesgo de reversión a la media / menor volatilidad en las horas previas a las 08:00 UTC del viernes, con posible expansión de volatilidad justo después del vencimiento.
- **Datos necesarios:** open interest por strike de Deribit — dato adicional que no está en OHLCV normal, requiere API específica.
- **Evidencia:** la cobertura de mercado reciente es escéptica: *"los vencimientos recientes no han mostrado el efecto esperado de 'anclaje' (pinning) del precio, lo que refuerza el escepticismo entre los expertos en opciones"*, y *"a pesar de ser una narrativa convincente, los vencimientos de opciones recientes no han anclado mecánicamente los precios de la forma en que la gente espera que lo hagan"* ([CoinDesk, sobre el vencimiento de $10.000M de junio 2026](https://www.coindesk.com/markets/2026/06/25/forget-max-pain-bitcoin-is-well-below-the-usd72-000-magnet-ahead-of-usd10-billion-options-expiry)). Deribit mismo, en un comunicado citado, dijo que un vencimiento trimestral de $12.000M era "improbable que causara una reacción de mercado importante" ([Yahoo Finance](https://finance.yahoo.com/news/bitcoins-12b-quarterly-options-expiry-131620451.html)).
- **Veredicto:** **evidencia publicada, y es negativa/escéptica** — a diferencia de otros conceptos de esta investigación donde "no hay evidencia", aquí SÍ hay cobertura periodística explícita de que el efecto pin, cuando se contrasta contra la realidad, falla más de lo que la narrativa sugiere. No se recomienda como hipótesis de trading basada en pinning; el propio mercado de opciones institucional (Deribit) desmiente la narrativa popular.
- **Dificultad de programación:** alta (requiere pipeline de datos de opciones/open interest, no solo OHLCV) para un beneficio dudoso según la evidencia — **prioridad baja**.

### 5.5 Vencimiento CME (futuros)

- **Explicación llana:** los futuros de CME sobre BTC vencen mensualmente (el último viernes de cada mes, aprox.) y trimestralmente. Se especula que el rollover de posiciones y el cierre de contratos genera actividad anómala cerca del vencimiento.
- **Evidencia:** no se ha encontrado ninguna fuente específica en esta sesión sobre el vencimiento de futuros CME (distinto del "CME gap" de fin de semana, cubierto en 3.4). Se marca como **no investigado / pendiente**.
- **Veredicto:** sin datos suficientes para veredicto en esta sesión.

---

## 6. Gestión de riesgo de traders reales

**Aviso metodológico:** el presupuesto de búsquedas web de esta sesión se agotó durante la investigación de esta sección (el sistema reporta "200 de 200 WebSearch calls" usadas), y los intentos posteriores de acceder directamente a papers y artículos concretos sobre stops/trailing/salidas parciales fallaron (404/403). Lo que sigue es **conocimiento general de la literatura de trading y gestión de riesgo**, no verificado con una fuente específica dentro de esta sesión — se marca explícitamente así en cada punto, y se recomienda contrastarlo con un backtest propio antes de confiar en ello, exactamente el mismo estándar que se ha aplicado al resto del documento.

### 6.1 Dónde ponen el stop los traders discrecionales

- **Mínimo/máximo del swing:** el stop se coloca justo debajo del mínimo (o encima del máximo) que definió la estructura que motivó la entrada — p. ej., debajo del mínimo del spring/sweep que dio la señal. Ventaja: invalidación lógica ligada a la tesis de la operación. Desventaja: en cripto, con mechas frecuentes por liquidaciones en cascada de futuros perpetuos, es fácil que un mínimo de swing se perfore por una mecha y el stop salte por muy poco antes de que el precio continúe en la dirección esperada.
- **ATR múltiplo:** stop = entrada ± N × ATR(14) (N típico entre 1.5 y 3). Ventaja: se adapta a la volatilidad del momento (mismo % de precio en BTC en 2020 y en 2025 representa volatilidad muy distinta). Es el método más robusto para backtest sistemático porque no depende de la definición subjetiva de "swing".
- **Invalidación estructural:** el stop se coloca donde la tesis del patrón deja de ser cierta (p. ej., si la señal es un order block, el stop va donde un cierre más allá del OB demuestra que "no era smart money", sino ruptura real). Es conceptualmente el más "correcto" pero el más difícil de traducir a una regla objetiva sin ambigüedad.
- **Evidencia:** conocimiento general no verificado en esta sesión. La preferencia de la literatura cuantitativa de gestión de riesgo (no específica de esta sesión) suele favorecer el stop basado en ATR frente al stop fijo en % porque es invariante a régimen de volatilidad, pero eso no implica que sea superior al stop de invalidación estructural en sistemas discrecionales-programados — son cosas distintas (uno es "cuánto puedo perder", el otro es "cuándo mi tesis es falsa") y lo ideal suele ser combinar ambos (usar el más ajustado de los dos, o el estructural con un tope máximo en ATR para evitar stops absurdamente amplios).

### 6.2 Ratios objetivo/riesgo (R:R)

- **Explicación llana:** cuánto se espera ganar por cada unidad de riesgo asumida. Un R:R de 1:2 significa arriesgar 1 para buscar 2.
- **Relación con win rate:** la aritmética es inevitable: con R:R 1:1 se necesita >50% de aciertos para ser rentable (antes de comisiones); con R:R 1:2 basta con >33.3%; con R:R 1:3 basta con >25%. El error de marketing más común en contenido de trading discrecional es prometer "80% de win rate" sin decir el R:R —un 80% de aciertos con R:R 1:5 en contra (ganar poco, perder mucho cuando falla) puede ser ruinoso, y es exactamente el patrón de muchos sistemas de "toma de beneficio rápida, stop lejano" que parecen geniales hasta que llega la racha perdedora.
- **Evidencia:** esto es aritmética pura, no requiere "evidencia" externa — es una identidad matemática (`winrate × R:R > 1` para expectativa positiva antes de costes). Lo que sí requiere evidencia es qué R:R es realista lograr con cada patrón concreto (secciones 1-4), y ahí la falta de backtests rigurosos de la mayoría de conceptos discrecionales es precisamente el problema central de este documento.

### 6.3 Salidas parciales (scaling out) y break-even

- **Explicación llana:** en vez de cerrar toda la posición en un único objetivo, cerrar una parte en un primer objetivo (asegurando beneficio) y dejar correr el resto, a menudo moviendo el stop de esa parte restante a break-even (precio de entrada) para "operación sin riesgo".
- **El debate central en la literatura de trading (no verificado en esta sesión con fuente específica, pero es un debate bien conocido y recurrente en la comunidad de trend-following, ej. Ed Seykota, Van Tharp, Michael Covel):**
  - **A favor de salidas parciales:** reduce la varianza de resultados, mejora la tolerancia psicológica (menos operaciones que van de ganadoras a perdedoras), y es coherente con el sesgo cognitivo real del operador (más fácil seguir un sistema que asegura beneficio pronto).
  - **En contra (el argumento clásico de "cut losses short, let profits run"):** en sistemas cuya rentabilidad depende de una cola gorda de pocas operaciones muy ganadoras (típico de sistemas de tendencia/ruptura), cerrar parcialmente pronto **reduce sistemáticamente la expectativa matemática total**, porque recorta precisamente la parte de la distribución de retornos que sostiene el sistema. Esto es un resultado ampliamente citado en la literatura de trend-following (sin fuente académica puntual verificada en esta sesión) pero es coherente con la lógica: si el 70% de las ganancias vienen del 10% de las operaciones (patrón habitual en sistemas de tendencia), cualquier regla que limite el recorrido de esas operaciones "estrella" daña la expectativa total, aunque mejore el ratio de aciertos y la "sensación" de consistencia.
  - **Mover el stop a break-even** tiene el mismo problema en menor escala: en mercados con ruido normal (retrocesos que no invalidan la tendencia), mover el stop a breakeven demasiado pronto provoca ser expulsado ("shaken out") de operaciones que habrían sido ganadoras si se hubiese dejado el stop original más amplio.
- **Conclusión honesta para este proyecto:** la evidencia (general, no verificada puntualmente en esta sesión) apunta a que las salidas parciales y el break-even temprano **mejoran métricas de consistencia/drawdown pero probablemente empeoran la expectativa total** en sistemas cuyo edge depende de capturar movimientos grandes — que es exactamente el tipo de sistema que se busca aquí (entrar antes de la confirmación de tendencia). Esto es **testeable directamente con los propios datos**: comparar la misma señal de entrada con (a) salida única en TP fijo, (b) salida parcial + trailing del resto, (c) sin salida parcial y trailing puro desde el principio. Se recomienda que esta comparación forme parte del propio proceso de backtest del proyecto en vez de asumir una respuesta de la literatura general.
- **Veredicto:** **plausible pero contradictorio en la literatura, y altamente dependiente del tipo de sistema** — no hay un "correcto" universal; es una de las pocas preguntas de esta investigación donde el propio backtest del proyecto puede zanjar la duda mejor que ninguna fuente externa, porque depende de la distribución de retornos específica del sistema final.

### 6.4 Trailing stop

- **Explicación llana:** el stop se mueve a favor del precio a medida que la operación gana, nunca en contra, para proteger beneficio no realizado sin fijar un objetivo de salida rígido.
- **Evidencia (general, no verificada puntualmente en esta sesión):** el trailing stop tiende a favorecer sistemas de tendencia/momentum (deja correr ganancias en movimientos largos) y a perjudicar sistemas de rango/reversión a la media (sale demasiado tarde en giros, da de vuelta gran parte del beneficio en el "último tramo" antes del giro real). El método de trailing importa mucho: un trailing basado en ATR (ej. Chandelier Exit: máximo reciente − N×ATR) suele comportarse mejor que un trailing en % fijo porque se adapta a la volatilidad, igual que en el caso del stop de entrada (6.1).
- **Veredicto:** **plausible, dependiente del régimen (tendencia vs rango), no verificado con fuente puntual en esta sesión**. Recomendación: testear trailing basado en ATR/estructura (bajo el último swing confirmado) en vez de trailing en % fijo, y comparar contra salida en TP fijo con los propios datos.

---

## 7. Psicología convertida en regla

Esta sección es distinta de las anteriores en naturaleza: no busca generar señal/alpha, sino **limitar el daño** que causaría un ser humano operando con sesgos emocionales — y un bot, precisamente por no tener emociones, puede aplicar estas reglas de forma perfecta y consistente, algo que ningún trader discrecional humano logra al 100%. Es, en cierto sentido, la ventaja estructural más clara que tiene un bot sobre un trader humano, y probablemente aporte más valor esperado que cualquier patrón de las secciones 1-4 con evidencia débil.

| Sesgo/error humano | Regla programable equivalente | Notas de implementación |
|---|---|---|
| **Sobreoperar** (abrir operaciones sin setup real, "porque sí", por aburrimiento) | Límite duro de operaciones por día/semana; el bot solo actúa si TODAS las condiciones de una señal válida se cumplen, nunca "a medias" | Es la regla más fácil de aplicar bien en un bot — de hecho un bot bien diseñado no puede "aburrirse", así que este riesgo casi desaparece si el código no tiene una vía de entrada discrecional/manual |
| **Revenge trading** (aumentar tamaño o frecuencia tras una pérdida para "recuperarla ya") | Position sizing fijo por señal (no dependiente del resultado de la operación anterior); enfriamiento obligatorio (cooldown) de X horas/velas tras N pérdidas consecutivas antes de permitir nueva entrada | El cooldown es clave: no solo "no aumentar tamaño", sino literalmente bloquear nuevas entradas una ventana de tiempo tras rachas negativas, para evitar que el propio sistema entre en un régimen de mercado adverso repetidamente |
| **Límite diario de pérdidas** (dejar de operar el día si se supera un umbral) | `if pérdida_acumulada_día ≥ X% del capital: no abrir nuevas operaciones hasta el día siguiente (o hasta reset semanal)` | Fácil de implementar; requiere decidir si las operaciones ya abiertas se cierran o se dejan correr hasta su TP/SL natural al alcanzar el límite (recomendable: dejarlas correr, solo bloquear nuevas entradas) |
| **Máximo de operaciones simultáneas / al día** | `if operaciones_abiertas ≥ N: no abrir más` y/o `if operaciones_hoy ≥ M: no abrir más` | Limita tanto el sobreapalancamiento por correlación (todas las señales de BTC tienden a correlacionar entre sí) como el sobreoperar |
| **Mover el stop en contra por esperanza ("ya volverá")** | Prohibición estructural: el bot nunca puede ampliar un stop-loss ya fijado, solo puede moverlo a favor (trailing) o dejarlo fijo | Trivial de garantizar en código — es una ventaja categórica del bot: el stop-loss "sagrado" que todo libro de trading recomienda y que casi ningún humano cumple al 100% |
| **Sesgo de confirmación / ver señales donde no las hay tras una racha ganadora (overconfidence)** | Los parámetros de la estrategia no cambian por el resultado reciente; cualquier cambio de parámetros pasa por un proceso de backtest y validación offline, nunca por ajuste "en caliente" tras ver resultados en vivo | Relevante también para el propio proceso de desarrollo del proyecto, no solo para el bot en producción: es la misma disciplina que se le pide al bot, aplicada al desarrollador |
| **Miedo a perder ganancias no realizadas (cerrar demasiado pronto)** | Reglas de salida (TP/SL/trailing) fijadas ANTES de la entrada, ejecutadas mecánicamente sin posibilidad de intervención manual selectiva | Coherente con 6.3/6.4 — la política de salida se decide en el backtest, no en caliente |
| **Operar tras noticias/euforia sin plan (FOMO)** | Filtro de volatilidad extrema: si el rango de la vela o el ATR excede un múltiplo del ATR medio reciente, pausar nuevas entradas un número de velas (evita entrar en el pico de un movimiento de pánico/euforia) | Esto conecta con el propio historial del proyecto: el commit reciente `is_volatile_session usa zoneinfo para corregir DST` sugiere que el bot ya tiene algo de lógica de sesión volátil — coherente con esta idea |

**Evidencia:** estas reglas no son "hipótesis de alpha" que requieran backtest de rentabilidad — son limitadores de riesgo de cola y de comportamiento errático cuyo valor es principalmente defensivo (reducir varianza y evitar rupturas catastróficas de la disciplina del sistema), no generar retorno. No se ha buscado "evidencia" de que "no hacer revenge trading" funcione, porque es axiomático dentro de cualquier marco de gestión de riesgo — el valor de esta sección es la traducción a reglas de código verificables, no la validación estadística.

---

*(Sección en progreso — siguiente: Traders y canales concretos)*

---

## 8. Traders y canales con metodología pública

*(Sección completada por el agente principal el 8-sept-2026, tras interrumpirse la investigación delegada.)*

Se buscó explícitamente lo que pedía el encargo: traders de cripto con **metodología
pública y concreta** y resultados verificables. **El resultado de la búsqueda es, en sí
mismo, el hallazgo**: el espacio está dominado por contenido comercial —comparativas de
"mejores proveedores de señales 2026", academias de trading, firmas de fondeo— redactado
para posicionar en buscadores, no para explicar un método. Las propias guías del sector
admiten el problema: un historial que no está publicado en un verificador independiente
debe tratarse con escepticismo profundo, y las señales de alarma habituales son
instructores anónimos y "track records" construidos solo con capturas de operaciones
ganadoras ([altfins](https://altfins.com/crypto-news/article/5-most-transparent-crypto-prop-firms-of-2026-verified-payouts),
[TargetHit](https://targethit.com/blog/best-crypto-signal-provider-2026)).

**Conclusión honesta: para este proyecto, los "traders de YouTube" no son una fuente
utilizable de ventaja.** No porque no sepan operar —algunos sabrán—, sino porque su
método no llega en una forma que se pueda verificar ni programar: sin reglas cerradas,
sin registro completo de operaciones perdedoras, y sin la distinción entre "esto funcionó"
y "esto funcionó porque el mercado subía".

Lo que **sí** es una fuente utilizable, y de donde viene todo lo defendible de este
documento:

| Fuente | Por qué es utilizable |
|---|---|
| **Rob Carver** (`pysystemtrade`, libros) | Publica el **código completo** del sistema, incluidos los tramos que no funcionan. Método verificable línea a línea. |
| **Brian Shannon** (AVWAP anclado) | Divulga el concepto con mecanismo económico explícito (coste medio agregado desde un evento) y no vende señales. Sin backtest público, pero honesto sobre ello. |
| **Larry Connors** (RSI-2), **Toby Crabel** (opening range) | Reglas cerradas y publicadas hace décadas, replicables y ya testeadas por terceros. |
| **QuantPedia / Quantified Strategies** | Publican reglas, periodo y resultados; y —lo importante— también publican las revisiones donde una estrategia deja de funcionar. |
| **Papers (SSRN, arXiv)** | Metodología expuesta y criticable. Con la advertencia de que casi ninguno modela costes realistas. |
| **Repos abiertos** (Freqtrade, NFI) | Se puede leer el código exacto. |

El criterio que separa unos de otros no es la fama: es si **publican también lo que no
funcionó**. Todo lo demás es marketing con gráfico.

---

## 9. Qué dice la comunidad algo que funciona (y qué está muerto)

Búsquedas hechas el 8-sept-2026. Aviso: Reddit no es accesible para búsqueda automatizada,
así que esta sección se apoya en agregadores y en la lectura directa de repos.

**Consensos razonablemente sólidos (coinciden múltiples fuentes independientes):**

1. **El scalping y el arbitraje puro están muertos para un particular.** Requieren
   colocación física junto al exchange y ejecución de microsegundos; sin eso, se pierde
   por costes de forma estructural, no por mala suerte.
2. **La reversión a la media sigue siendo la familia más citada como "lo que funciona"
   en cripto** — pero es exactamente la pata que la evidencia académica muestra
   degradándose desde 2022 (ver anexo 02, §1.4). Que la comunidad la cite mucho y la
   evidencia la desmienta a la vez es información: probablemente refleja el sesgo de
   supervivencia de quien publicó en 2019-2021 y sigue repitiéndolo.
3. **Los "bots de IA" son el producto dominante de 2026 en marketing** y no hay un solo
   resultado verificable detrás de las afirmaciones de rendimiento.

**El dato duro de la comunidad, medido directamente en su código:** la estrategia
comunitaria más usada del ecosistema Freqtrade, `NostalgiaForInfinity` X7, tiene **79.038
líneas, 109 condiciones de entrada y 16.937 umbrales numéricos escritos a mano** (medido
sobre el repo descargado el 8-sept-2026). Sigue viva y con commits diarios. Eso dice dos
cosas a la vez, y las dos importan:
- funciona lo suficiente como para que cientos de personas la mantengan y la usen;
- y es **estadísticamente inauditable**: con ese número de umbrales ajustados, el Sharpe
  desinflado no se puede ni calcular. Nadie sabe —ni su autor— cuánto de su resultado es
  ventaja y cuánto es ajuste al pasado.

**Lo que la comunidad da por muerto y coincide con la evidencia:** grid puro en mercados
con tendencia, gap del CME (muerto estructuralmente desde el 29-mayo-2026 con los futuros
24/7), y el "max pain" de opciones.

---

## 10. Las 15 hipótesis más prometedoras y programables de este anexo

Ordenadas por (evidencia × mecanismo económico creíble × facilidad de programar). Las
cuatro primeras son las únicas que yo defendería gastar intentos del presupuesto.

| # | Hipótesis | Definición operativa | Evidencia | Coste |
|---|---|---|---|---|
| 1 | **Perfil horario de volatilidad y volumen de BTC** | Agrupar el histórico por hora UTC; medir ATR% y volumen medio. No es una estrategia: es el mapa sobre el que se decide *cuándo* se permite operar | Mecanismo real (actividad institucional); verificable con datos propios | Trivial |
| 2 | **Efecto fin de semana** | Rango realizado sáb-dom vs. entre semana | Ya confirmado por el usuario en `filtros/sesion.py` | Trivial |
| 3 | **Delta / CVD y absorción** | Volumen agresivo comprador − vendedor, acumulado; divergencia precio-delta | Sin evidencia publicada, pero **el mejor mecanismo microestructural del documento**: mide flujo de órdenes real, no geometría. Freqtrade ya lo soporta | Medio-alto (datos de trades) |
| 4 | **AVWAP anclado a un evento** | VWAP desde un suelo/techo/noticia concreta como nivel de coste medio agregado | Plausible, mecanismo económico claro, divulgador no comercial | Baja |
| 5 | **Barrido de liquidez + reversión** | Mecha que supera PDH/PDL o el extremo del rango y cierra dentro, en ≤N velas | La menos mala de ICT: señal pequeña y consistente frente al azar, sin significancia formal | Baja |
| 6 | **Niveles PDH/PDL, PWH/PWL** | Máximo/mínimo del día y de la semana anterior como referencia | Plausible; barato de medir | Trivial |
| 7 | **Opening Range Breakout adaptado** | Rango de los primeros K minutos tras apertura de Londres/NY; rotura y reversión | Antecedente clásico fuera de cripto (Crabel); efecto probablemente más débil sin campana real | Baja |
| 8 | **Trailing por ATR vs. objetivo fijo** | Comparar la MISMA entrada con salida fija, trailing ATR (Chandelier) y parcial+trailing | La literatura se contradice; **el propio backtest zanja mejor que cualquier fuente** | Baja |
| 9 | **Spring de Wyckoff** | Rotura del mínimo de un rango lateral establecido + recuperación rápida al interior | Plausible; es el subcomponente programable de Wyckoff | Media |
| 10 | **LVN como zona de aceleración** | Zonas de bajo volumen del perfil como tramos de movimiento rápido (no como imán) | Plausible; distinto del POC ya descartado por el usuario | Media |
| 11 | **Límite diario de pérdidas y de operaciones** | Regla dura de parada | Defensivo, no genera alpha, pero es la ventaja estructural del bot sobre el humano | Trivial |
| 12 | **Stop por invalidación estructural vs. ATR vs. %** | Comparar los tres sobre la misma entrada | Sin evidencia externa; propio backtest | Baja |
| 13 | **Vencimiento de opciones de Deribit (viernes 08:00 UTC)** | Comportamiento en las horas previas/posteriores | **Evidencia publicada escéptica** sobre el efecto pin: probar solo como filtro de contexto | Baja |
| 14 | **Order Blocks** | Última vela contraria antes del impulso | Evidencia débil; incluir solo si sobra presupuesto de intentos | Media |
| 15 | **Fair Value Gap** | Hueco de 3 velas sin solapamiento | **Evidencia publicada NEGATIVA** — se lista para dejar constancia de que se miró, no para probarlo | Baja |

**Lo que este anexo recomienda NO probar:** FVG, OTE/Fibonacci, Judas Swing/Silver
Bullet, retesteo clásico de rotura (mismo mecanismo de "confirmar tarde" que el usuario
ya descartó con datos), y el gap del CME (muerto por cambio estructural del mercado).
