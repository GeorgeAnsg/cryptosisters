# Investigación de estrategias públicas y concretas para BTC (con evidencia)

**Fecha de la investigación:** 8 de septiembre de 2026
**Objetivo:** documentar estrategias sistemáticas *específicas* y *públicas* sobre Bitcoin, con reglas programables, resultados reportados, periodo de backtest y críticas conocidas — separando siempre "evidencia decente" de "afirmación sin respaldo" (marketing).

**Cómo leer este documento:** cada estrategia lleva una ficha con seis campos:
- **(a) Reglas exactas** — lo que habría que programar, sin ambigüedad
- **(b) Timeframe y activo** — en qué mercado y con qué velas se probó
- **(c) Resultados reportados** — números concretos y quién los publicó, con URL
- **(d) Periodo del backtest** — fechas exactas si se conocen
- **(e) Críticas / por qué puede estar sobreajustada** — el motivo por el que hay que desconfiar
- **(f) Cómo la testearías honestamente** — el test que tú (con tus propios datos, sin comisión pero con spread de Quantfury) deberías hacer antes de creerte el resultado

Al final hay un **ranking de las 15-20 hipótesis más prometedoras** para probar primero.

---

## 0. Contexto y advertencia metodológica general

Antes de entrar estrategia por estrategia, tres cosas que aplican a *todo* lo que sigue:

1. **El sesgo de publicación es brutal en cripto.** Casi todos los blogs de "backtest de Bitcoin" (QuantifiedStrategies, Coinquant, blogs de brokers) muestran el resultado que vende, no el proceso completo de prueba de 50 variantes hasta encontrar una que funcione (data snooping / p-hacking). Cuando la fuente es un fondo académico revisado por pares (SSRN, arXiv, ScienceDirect, journals) el rigor es mayor, pero incluso ahí muchos papers de momentum en cripto **ignoran costes de transacción y turnover real** — un paper de 2023 (Han, Kang & Ryu, ver sección 1) es explícito en que gran parte de la literatura de momentum cripto "no sobrevive" cuando se aplican supuestos realistas.
2. **"Backtest bonito" no es lo mismo que "edge real".** Muchas cifras de este documento (ej. "50% CAGR", "1500% en 9 años") vienen de una única pasada de optimización sobre datos históricos sin partición in-sample/out-of-sample. Deben tratarse como **hipótesis a validar**, no como hechos.
3. **Definición del enemigo a batir.** Tal como me confirmaste, ya sabes por experiencia propia que (a) los indicadores de "confirmación de tendencia" (EMA, ADX, Supertrend, roturas de máximos, MACD) fallaron con tus datos, y (b) un screening a horizonte fijo solo sirve para descartar, no para generar señal. Esto es coherente con la evidencia: casi todos los papers de trend-following de gama alta usan **filtros de volatilidad, salidas dinámicas (trailing stop en ATR) o combinación con mean reversion**, no un cruce de medias puro. Lo señalo explícitamente en cada sección donde aplica.

---

## 1. Trend following / momentum en BTC diario

### 1.1 Cruces de medias móviles (MA crossover)

**(a) Reglas exactas:** posición larga cuando MA_rápida > MA_lenta; plana o corta cuando MA_rápida < MA_lenta. Variantes más citadas: 20/100, 50/200 ("golden cross"), 10/30.

**(b) Timeframe y activo:** BTC diario, desde 2012-2013 hasta hoy en la mayoría de backtests.

**(c) Resultados reportados:**
- Backtest de cruce 20/100 días desde 2012: **116% anualizado, Sharpe 1.7**, vs. buy-and-hold **110% anualizado, Sharpe 1.3** — fuente: Medium/ChainSlayer, ["Finding the Best Moving Average Crossover Strategy for Bitcoin"](https://medium.com/chainslayer/finding-the-best-moving-average-crossover-strategy-for-bitcoin-f0a959b846c7). Sin control de costes de transacción declarado.
- Cruce 50/200 ("golden cross") en 2018-2023: solo ~8 señales en 5 años (es una estrategia de muy baja frecuencia), resultado mixto — capturó tendencias grandes pero generó falsas señales en mercados laterales — fuente: [The Trading Muse](https://thetradingmuse.com/simple-moving-average-crossover-strategy-backtest-for-bitcoin/).

**(d) Periodo:** 2012-2023 según la fuente (no hay periodo estándar; cada blog usa el suyo).

**(e) Críticas:** (1) resultados muy sensibles a qué años se incluyen — casi todo backtest de MA-crossover en BTC debe su rendimiento a 2 o 3 tramos de tendencia fuerte (2013, 2017, 2020-21); si se excluyen esos tramos el edge desaparece. (2) El mismo estudio admite que "los resultados varían significativamente según el periodo de lookback elegido", lo que es la definición de riesgo de sobreajuste de parámetros. (3) Esto coincide exactamente con lo que ya observaste: estas señales de "confirmación de tendencia" fallaron con tus datos propios — es coherente con que su edge histórico dependa de pocos episodios idiosincráticos del BTC 2013-2021 que pueden no repetirse.

**(f) Cómo testearlo honestamente:** walk-forward con al menos 3 particiones (in-sample para elegir el par de medias, out-of-sample para medir), incluyendo obligatoriamente 2014-15, 2018 y 2022 (los tres grandes mercados bajistas), y comparando contra buy-and-hold con el mismo periodo exacto. Si el edge solo aparece cuando se incluyen 2017 o 2020-21, es sospecha de sobreajuste al ciclo, no de edge estructural.

### 1.2 Donchian Channel breakout (estilo Turtle)

**(a) Reglas exactas:** largo cuando el precio de cierre rompe el máximo de N días (típico N=20 o 55); salida/corto cuando rompe el mínimo de N días (a menudo con N de salida distinto y más corto, ej. 10). Turtle clásico: entrada en rotura de 20 días (sistema 1) o 55 días (sistema 2), salida en rotura de 10 días en contra.

**(b) Timeframe y activo:** BTC diario, 2017-2023 en el backtest citado; también hay variantes intradía (30 min).

**(c) Resultados reportados:**
- Sistema 20/55 estilo Turtle en BTC diario desde 2017: positivo en los 5 regímenes de mercado probados (bull 2017, bear 2018, bull 2020-21, bear 2022, recuperación 2023), win rate 30-40%, ganadores medios 3-5x el tamaño de las pérdidas medias — fuente: [Coinquant, "Donchian Channel Breakout on Crypto"](https://www.coinquant.ai/blog/donchian-channel-breakout-on-crypto-backtest-vs-keltner).
- Otro backtest de 4.5 años en BTC diario: **+36.5% de retorno total** desde $10,000, 25 operaciones, 36% de acierto, **drawdown máximo de 38.5%** — fuente: [Coinquant, BTC Donchian 30m backtest](https://www.coinquant.ai/strategies/btc-donchian-30m-backtest) (nota: la referencia exacta a 30 min vs diario varía según la página de Coinquant, verificar el timeframe exacto antes de replicar).
- Estudio académico riguroso sobre Donchian + filtro de régimen de volatilidad ATR en BTC diario: mejora significativa sobre buy-and-hold pero "altamente sensible a costes de transacción, parámetros y condiciones de mercado" — Nitish Poluri, SSRN, ["Evaluating the Performance of a Donchian Channel Breakout Strategy with ATR-Based Risk Management"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6272239).

**(e) Críticas:** win rate bajo (30-40%) significa que la estrategia depende completamente de dejar correr pocas operaciones ganadoras grandes; en la práctica esto es psicológicamente muy difícil de ejecutar manualmente vía Telegram (vas a tener rachas largas de pérdidas pequeñas seguidas). El drawdown de 38.5% en un solo backtest de 4.5 años es alto para 5 posiciones simultáneas máx. Además "wide channels in crypto" significa que el sistema tarda mucho en confirmar — no es apto para 15m/1h salvo con mucho ruido.

**(f) Cómo testearlo honestamente:** dado tu histórico de que "roturas de máximos" ya fallaron, prueba primero si el fallo fue de la regla de entrada (rotura) o de la regla de salida (sin trailing ATR). Backtest walk-forward comparando Donchian con salida fija a horizonte vs. Donchian con salida por ATR trailing — esto aislaría si el problema real era la salida, no la entrada.

### 1.3 Time-series momentum (TSMOM) académico

**(a) Reglas exactas:** posición proporcional al signo (o volumen-ponderado) del retorno de los últimos k días/meses del propio activo (no cruces de medias, sino retorno bruto pasado).

**(b) Timeframe y activo:** diario, universo amplio de criptomonedas (no solo BTC) en la mayoría de papers académicos.

**(c) Resultados reportados:**
- **Cryptocurrency Volume-Weighted Time Series Momentum**, Huang, Sangiorgi & Urquhart (SSRN, dic. 2024): TSMOM ponderado por volumen genera **0.94% de retorno diario, Sharpe anualizado de 2.17**, sobre 3,192 criptomonedas 2014-2023, rebalanceo diario. Dato crítico: la misma señal con pesos iguales (no ponderados por volumen) **pierde 1.19% al día** — el volumen es la clave, no solo la dirección. URL: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4825389
- **Time-Series and Cross-Sectional Momentum... under Realistic Assumptions**, Han, Kang & Ryu (SSRN, dic. 2023): al incorporar costes de transacción y fluctuaciones intradía realistas, **muchas carteras de momentum se liquidan (dan margin call) y las que sobreviven con retornos "estadísticamente significativos" ganan beneficios económicamente insignificantes**. TSMOM es fuerte; cross-sectional momentum es débil. URL: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565
- **A Decade of Evidence of Trend Following Investing in Cryptocurrencies** (arXiv 2009.12155): evidencia de una década a favor de TSMOM en cripto. URL: https://arxiv.org/pdf/2009.12155

**(d) Periodo:** 2014-2023 (Huang et al.), datasets con universo de miles de altcoins de baja liquidez — importante porque tú operarías solo BTC y quizá ETH.

**(e) Críticas — muy importantes:**
1. La cifra de Sharpe 2.17 viene de un universo de **3,192 criptomonedas**, la mayoría microcap ilíquidas donde el "volumen" reportado en exchanges pequeños está contaminado por wash trading (aunque el paper dice que controla por esto). El resultado **no es replicable en un portfolio real de BTC/ETH manual vía Telegram** — el edge viene en gran parte del long-short cross-sectional sobre altcoins basura, no de operar BTC solo.
2. El paper de Han et al. es la crítica más honesta que vas a encontrar: dice textualmente que la literatura de momentum cripto en general **ignora "consideraciones del mundo real"** y que al corregirlas el edge colapsa. Esto debería ser tu prior por defecto para cualquier cifra de este documento que no mencione explícitamente costes.
3. TSMOM puro en BTC (sin ponderar por volumen ni cross-sectional) es esencialmente lo mismo que un cruce de medias con lookback largo — mismo problema que 1.1.

**(f) Cómo testearlo honestamente:** replica el TSMOM solo con BTC (no el universo de 3000 monedas), con retornos de 7/30/90 días como señal de dirección, aplicando spread realista de Quantfury en cada entrada/salida, y compara el Sharpe resultante con el 2.17 reportado — la caída esperada es grande.

### 1.4 ¿Se ha degradado el trend-following desde 2022?

**Evidencia concreta:** Beluská & Vojtko, ["Revisiting Trend-following and Mean-Reversion Strategies in Bitcoin"](https://quantpedia.com/revisiting-trend-following-and-mean-reversion-strategies-in-bitcoin/?a=6080) (QuantPedia, actualización del paper original de 2022 hasta agosto 2024):
- **Estrategia MAX (trend-following):** comprar cuando BTC toca el máximo de los últimos 10-50 días. In-sample: oct-2015 a ago-2024. Out-of-sample real: **feb-2022 a ago-2024** (incluye toda la caída de 2022, quiebra de FTX, etc.) — la estrategia MAX **"sigue viva y funcionando"** en el out-of-sample, aunque "el rendimiento de ambas estrategias es ligeramente menos efectivo comparado con la investigación original".
- **Estrategia MIN (mean-reversion):** comprar en el mínimo de los últimos 10-50 días. En el out-of-sample 2022-2024 **"no ha funcionado bien"** — es la pata que más se ha degradado.
- **Combinada MIN+MAX:** se mantiene cerca de máximos históricos de la curva de capital.
- Conclusión explícita del paper: **no encontraron estacionalidad diaria significativa** en ninguna de las dos estrategias.

**Respuesta corta a tu pregunta:** sí hay evidencia de que la pata de *mean reversion* (comprar mínimos) se ha degradado claramente desde 2022, mientras que la pata de *momentum puro sobre máximos* se mantiene, aunque algo más débil que en el estudio original. Esto es coherente con la narrativa de mercado: 2022-2024 tuvo entrada de ETFs, mayor participación institucional y menos "pánico retail" que rebotara con fuerza desde mínimos — pero la muestra post-2022 sigue siendo corta (2.5 años) para afirmar una ruptura estructural definitiva.

---

## 2. Buy-and-hold con filtro de tendencia (MA200)

**(a) Reglas exactas:** mantener BTC largo mientras precio > MA200 (diaria o semanal); pasar a cash/stable cuando precio < MA200. Variante de Kraken/analistas: comprar cuando el precio cotiza *por debajo* de la MA200 semanal (como señal de "descuento", no de salida).

**(b) Timeframe y activo:** BTC, MA200 diaria o MA200 semanal (~4 años de datos).

**(c) Resultados reportados:**
- Analogía con el S&P 500 2000-2016: la regla MA200 devolvió **317% vs. 125% de buy-and-hold, con menor drawdown** — pero esto es en acciones, no en BTC (fuente citada de forma genérica, sin URL específica de BTC).
- Cruce 50/200 en BTC 2018-2023: ~8 señales en 5 años, "capturó las tendencias alcistas grandes pero también generó falsas señales en mercados laterales" — [The Trading Muse](https://thetradingmuse.com/simple-moving-average-crossover-strategy-backtest-for-bitcoin/).
- Comprar BTC cuando cotiza con descuento respecto a la MA200 **semanal**: retorno mediano histórico de **+113% a 12 meses y +313% a 24 meses** según un analista de Kraken — citado en [CoinDesk, "Michael Saylor's Strategy is tracking Bitcoin's 200-week moving average"](https://www.coindesk.com/markets/2026/08/03/michael-saylor-s-strategy-is-now-tracking-bitcoin-s-200-week-moving-average). **Ojo:** esto es "comprar barato y sujetar durante años", no una estrategia de trading activo, y la muestra son solo 2-3 ciclos de halving (n muy bajo, ver sección 6.3).
- Comparativa multi-estrategia (fuente agregada, sin desglose metodológico claro): Buy & Hold 42.51%, MACD+ADX 35.45%, EMA 26.07%, LSTM (ML) 65.23% — en un periodo no especificado con claridad; tratar como referencia débil.

**(d) Periodo:** variable; el dato de MA200 semanal cubre ciclos completos desde 2013-2015.

**(e) Críticas:** el "MA200 filter" para reducir drawdown es, en esencia, lo mismo que 1.1 con un lookback muy largo — mismo problema de que gran parte del beneficio proviene de evitar *un* gran drawdown histórico (2018 o 2022), y una vez fuera de mercado, la regla puede tardar meses en re-entrar y perderse el inicio del rally (el "whipsaw" clásico de las medias móviles en mercados que hacen suelo en V, como marzo 2020). La cifra de "+313% a 24 meses" tiene un tamaño de muestra de solo 2-3 eventos de "descuento vs MA200 semanal" en toda la historia de BTC — estadísticamente es casi anecdótico, no un backtest robusto.

**(f) Cómo testearlo honestamente:** medir no solo CAGR y drawdown máximo, sino el **número de señales reales** (probablemente <10 en todo el histórico de BTC) y el comportamiento específico en las dos veces que BTC hizo suelo en V (marzo 2020, y el rebote tras FTX en 2023) — si el filtro MA200 te saca justo antes del rebote en V, el "menor drawdown" se paga con "menor retorno total", que es exactamente el trade-off que hay que cuantificar, no asumir.

---

## 3. Mean reversion (RSI extremo, Bollinger, VWAP, buy-the-dip)

### 3.1 RSI(2) estilo Larry Connors

**(a) Reglas exactas (versión clásica de Connors, adaptada por Coinquant):** entrada larga cuando RSI(2) < 10 (sobreventa extrema); salida cuando RSI(2) > 70 (o cierre > SMA(5) en la versión original de acciones).

**(b) Timeframe y activo:** probado en BTC/USDT y ETH/USDT en 15m, 1h, 4h y 1d.

**(c) Resultados reportados:**
- Backtest genérico de RSI(2) en varios mercados (no específico de BTC): 75-79% win rate a 10+ años — [toptradingstrategy.com](https://toptradingstrategy.com/strategy/rsi-2-mean-reversion).
- Backtest específico BTC 2015-2021: profit factor 1.95, win rate 57.69% — [QuantifiedStrategies](https://www.quantifiedstrategies.com/bitcoin-rsi-trading-strategy/). El mismo artículo admite: **"RSI como indicador contrarian es básicamente inútil en Bitcoin"** en otras configuraciones probadas.
- **Estudio de 78 backtests de Coinquant** (BTC/USDT y ETH/USDT, 15m/1h/4h/1d, tres regímenes: alcista oct.2023-mar.2024, lateral abr.2023-oct.2023, bajista todo 2022): resultado agregado — **bull +16.3% de media, lateral -2.2%, bajista -40.6%**. Por timeframe: 15m -14.4%, 1h -8.1%, 4h -9.5%, 1d -4.0% (todos negativos de media, dominado por el arrastre del régimen bajista). Hallazgo clave citado literalmente: **"14 de los 78 backtests ganaron el 65% o más de sus operaciones y aun así perdieron dinero"** — el win rate alto no implica rentabilidad si las pocas pérdidas son mucho mayores que las ganancias. Mejor configuración encontrada: distancia a la media en mercado alcista, Sharpe 2.5-2.6 y hasta +30%, pero **se hunde a -45% en régimen bajista**. Fuente: https://www.coinquant.ai/blog/building-a-mean-reversion-strategy-in-cryptocurrency-markets-evidence-from-78-backtests

**(e) Críticas — esta es la sección más importante del documento para ti, porque confirma exactamente lo que ya sospechas:** el propio estudio de Coinquant lo resume así: *"la mean reversion desnuda no tiene sentido de dirección"*. En una tendencia bajista, cada toque de la banda inferior parece una ganga pero es un escalón más hacia abajo — la estrategia sigue comprando un mercado que cae, acumulando pérdidas hasta que el stop se dispara muy por debajo de la entrada. La forma de la curva de resultados de mean reversion es: **gana a menudo pero poco (rebotes modestos), pierde raramente pero mucho** (cuando la "reversión" en realidad era el inicio de una tendencia). Esto es asimetría de cola negativa — psicológicamente parece que "funciona siempre" hasta el día que te destruye la cuenta.

**(f) Cómo testearlo honestamente:** nunca reportar solo el win rate; exigir siempre profit factor y, sobre todo, **desglose por régimen de mercado** (alcista/lateral/bajista) por separado, no agregado. Si vas a probar mean reversion, hazlo **solo como filtro dentro de una tendencia alcista mayor confirmada** (ej. solo comprar RSI extremo si precio > MA200), nunca en aislado.

### 3.2 Bollinger Bands mean reversion

**(a) Reglas exactas:** entrada larga en cierre por debajo de banda inferior (SMA20 ± 2 o 2.5 desviaciones típicas); salida en cierre por encima de banda media (SMA20).

**(b) Timeframe y activo:** BTC/ETH, 15m/1h/4h/1d.

**(c) Resultados reportados:**
- QuantifiedStrategies (2026): el modelo captura "casi 50% CAGR estando en mercado solo el 34% del tiempo"; simulación de $100k a más de $6.2M para 2026 con menor exposición que buy-and-hold — https://www.quantifiedstrategies.com/bitcoin-bollinger-bands-trading-strategy-performance-backtest/. **Cifra sin desglose de régimen ni de costes — tratar con máxima cautela**, es exactamente el tipo de titular optimizado a posteriori que este documento te pide separar de la evidencia decente.
- Estudio académico SSRN sobre Bollinger en distintos regímenes BTC/USDT (Efe Arda): en fase bajista 2018, las estrategias de *ruptura* (breakout) superaron a las de *reversión*, que fallaron en la caída sostenida; en fase de acumulación 2018-2020, la reversión recuperó algo de rentabilidad limitada. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5775962
- Backtest de régimen por ADX en BTC/USDT 4h 2023-2025: profit factor 1.62 cuando ADX < 20 (mercado lateral) vs. profit factor -0.74 cuando ADX > 30 (mercado en tendencia) — [Coinquant](https://www.coinquant.ai/blog/building-a-mean-reversion-strategy-in-cryptocurrency-markets-evidence-from-78-backtests). Un filtro ATR evitó el 72% de las peores pérdidas en un backtest de 3 años.

**(e) Críticas:** exactamente igual que RSI(2) — Bollinger reversion depende completamente del régimen (ADX). Sin ese filtro de régimen la estrategia es una ruleta rusa direccional. La cifra de "50% CAGR" de QuantifiedStrategies muy probablemente está optimizada sobre el mismo periodo que reporta.

**(f) Cómo testearlo honestamente:** exigir SIEMPRE el filtro de régimen (ADX, o pendiente de MA200) como precondición, y medir el resultado con y sin filtro para cuantificar cuánto del "edge" viene realmente del filtro y no del Bollinger en sí.

### 3.3 Buy-the-dip por porcentaje de caída

**(a) Reglas exactas:** comprar cuando el precio cae X% en una ventana de tiempo Y (ej. -2% en 30 min, o "compra escalonada" en varios niveles de caída).

**(b) Timeframe y activo:** BTC/ETH, intradía a diario.

**(c) Resultados reportados:**
- Backtest 2021-2026 BTC/ETH: entrada **escalonada (laddered)** logró 68% win rate vs. 42% de compra "todo de golpe" en el dip, con drawdowns 25% menores — sin URL específica desglosada, referencia agregada de búsqueda.
- Análisis "The Best Interest": buy-the-dip en BTC es "sub-óptimo" comparado con simplemente holdear, salvo que se excluyan los periodos de tendencia bajista sostenida — https://bestinterest.blog/buy-the-dip-for-bitcoin/

**(e) Críticas:** es la versión más simple (y más vendida en redes) de mean reversion, con exactamente el mismo problema estructural de la sección 3.1: en tendencia bajista sostenida, "comprar la caída" es comprar sistemáticamente un activo que sigue cayendo. Todo backtest que "funciona" excluyendo 2022 está haciendo trampa (selección de periodo).

**(f) Cómo testearlo honestamente:** define el "dip" en términos relativos a volatilidad reciente (ej. caída > 2x ATR14) en vez de un % fijo, y exige que el backtest incluya completo el ciclo 2021-2023 (techo, caída del 75%, suelo) sin cortar la muestra.

### 3.4 VWAP deviation

No se encontró evidencia académica ni de blogs quant seria específica sobre "desviación de VWAP" como estrategia standalone en BTC diario/15m/1h (es un concepto mucho más usado en trading intradía de acciones institucional, donde el VWAP se resetea diariamente con fines de ejecución, no de señal direccional). Lo que sí existe son variantes de "distancia porcentual a una media móvil" (ver 3.1-3.2), que son conceptualmente equivalentes y con mejor evidencia. **Clasificación: afirmación sin respaldo específico para BTC** — no hay backtest público serio que aísle el VWAP de una SMA/EMA estándar.

---

## 4. Efectos de calendario en cripto

### 4.1 Día de la semana

**Evidencia académica (mixta y decreciente en el tiempo):**
- Estudio 2013-2018 (ScienceDirect): volatilidad significativamente alta lunes y jueves; retorno medio alto en lunes como respuesta a la mayor volatilidad. https://www.sciencedirect.com/science/article/abs/pii/S0275531918307827
- Estudio GARCH 2013-2019: **no** encuentra efecto día-de-la-semana clásico en retornos, pero sí menor riesgo en fin de semana y mayor volatilidad a principio de semana.
- Estudio de época COVID: BTC y Solana empezaron a mostrar efectos día-de-la-semana durante la pandemia; Cardano y Dogecoin no.
- Crítica metodológica clave (Oeconomia Copernicana 2022, ["A new perspective... evidence from an event study hourly approach"](https://oeconomia.pl/index.php/oc/article/view/2091)): estudios anteriores pueden estar sesgados porque BTC cotiza 24/7 sin cierre diario — lo que parece "efecto día de la semana" puede ser un artefacto de en qué huso horario se corta el "día".

**Conclusión honesta:** la evidencia es inconsistente entre estudios y **se ha ido debilitando con el tiempo** (coherente con que más participación institucional arbitra estos patrones). No hay una regla "compra lunes, vende jueves" que sobreviva de forma robusta entre papers.

### 4.2 Efecto fin de semana

- Efecto cruzado documentado y con más solidez que el día-de-la-semana puro: **retornos negativos de BTC/ETH en fin de semana predicen sistemáticamente caídas en el S&P 500 el lunes siguiente**, mientras que retornos positivos en fin de semana no tienen efecto simétrico — ScienceDirect, ["A crypto-stock weekend effect"](https://www.sciencedirect.com/science/article/pii/S1544612325019154). Esto es más útil como señal de contexto macro que como estrategia BTC-only.
- Bitcoin's Weekend Effect: Returns, Volatility, and Volume (2014-2024), ResearchGate: documenta el patrón pero con matices por fase de mercado (fases alcistas favorecen entre semana, fases bajistas favorecen fin de semana) — https://www.researchgate.net/publication/396418897

**(e) Crítica:** metodológicamente frágil — "returns are not consistently higher or lower" es la propia conclusión de varios estudios. Útil como *filtro de contexto* (ej. no abrir posiciones nuevas agresivas en fin de semana de baja liquidez), no como señal de entrada aislada.

### 4.3 Hora del día / sesiones (Asia, Londres, NY)

**(a) Regla concreta con mejor evidencia encontrada — Padyšák & Vojtko 2022:** comprar BTC a las 21:00 UTC y vender a las 23:00 UTC (hold de 2 horas), ventana que coincide con el cierre de todos los grandes mercados de acciones globales.

**(b) Timeframe:** datos horarios de Gemini, oct-2015 a feb-2022.

**(c) Resultados:** **~33% anualizado**, con volatilidad y drawdowns "dramáticamente" menores que buy-and-hold, según extracción del paper vía [paperswithbacktest.com](https://blog.paperswithbacktest.com/p/bitcoin-never-sleeps-exploiting-seasonality). Paper original: Padyšák & Vojtko, "Seasonality, Trend-following, and Mean reversion in Bitcoin", SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4081000
- QuantPedia cita de forma independiente **22:00 UTC como la hora más rentable**, con retorno medio ~0.07% en esa única ventana horaria — consistente en dirección (última hora del día de trading tradicional) aunque con horario ligeramente distinto al de arriba (posible diferencia de definición de ventana o de dataset).
- Contexto de sesiones generales: solapamiento Londres-NY domina el descubrimiento de precio y volumen; "rangos favorecen Asia, rupturas favorecen Londres, momentum favorece Nueva York" (afirmación cualitativa, sin backtest cuantitativo encontrado que la respalde con números).

**(d) Periodo:** oct-2015 a feb-2022 (paper original); la revisión de Beluská & Vojtko lo extiende hasta ago-2024 y **no encuentra estacionalidad diaria significativa** en esa muestra extendida — contradicción directa que hay que resaltar: **el efecto horario de 2022 podría no sobrevivir en el periodo 2022-2024**.

**(e) Críticas:** (1) el hallazgo de "estacionalidad significativa" del paper original de 2022 **no se replica** en la revisión de los mismos autores hasta 2024 — es el ejemplo perfecto de un patrón que puede haber sido ruido del periodo de muestra original, y los propios autores lo reconocen. (2) 2 horas de ventana es una señal de muy alta frecuencia, sensible al spread — en Quantfury (con spread, sin comisión pero ejecución manual vía Telegram) probablemente el coste de spread + la imposibilidad de ejecutar al segundo exacto destruya buena parte del edge de 2 horas.

**(f) Cómo testearlo honestamente:** replica exactamente la ventana 21:00-23:00 UTC (y también 22:00-23:00) con tus propios datos horarios de BTC desde 2015 hasta hoy, partiendo la muestra en pre-2022 y post-2022 por separado — si el efecto solo existe pre-2022, es un patrón muerto, no una fuente de señal para tu bot.

### 4.4 Fin de mes

No se encontró un estudio específico y cuantificado de "efecto fin de mes" en BTC (a diferencia de acciones, donde sí está bien documentado por flujos de rebalanceo de fondos). Lo más cercano es la estacionalidad mensual/trimestral (ver 4.6). **Clasificación: sin evidencia específica encontrada** — no incluir como hipótesis de alta prioridad.

### 4.5 Gap del CME

**(a) Regla exacta:** cuando CME cierra en fin de semana y el spot sigue moviéndose, se genera un "gap" en el gráfico de futuros CME; la estrategia apuesta a que el precio "rellenará" ese hueco.

**(b)/(c) Resultados reportados:** ~77% de los gaps CME se rellenan eventualmente (dato agregado 2018-2026); gaps menores a $500 se rellenan en 1-2 semanas; gaps menores a $700 se rellenan con 92% de probabilidad dentro de 30 días de trading (dato 2020-2025) — fuente agregada de blogs de brokers (CoinMarketCap Academy, Whaleportal, Phemex), sin paper académico identificado que lo confirme de forma independiente.

**(d) Cambio estructural importante:** **CME lanzó futuros de Bitcoin 24/7 en mayo de 2026**, lo que elimina la generación de nuevos gaps de fin de semana — [CoinDesk](https://www.coindesk.com/markets/2026/05/28/bitcoin-s-famous-cme-gaps-are-about-to-disappear-though-three-remain-unresolved). **Esta estrategia está estructuralmente muerta a partir de mayo de 2026** — solo quedan 3 gaps históricos sin rellenar, y no se generarán más. Es la estrategia de calendario más claramente "no vigente" de todo este documento.

**(e) Críticas:** incluso antes del cambio, la cifra de "77% de relleno" es engañosa porque casi cualquier serie de precios con reversión a la media rellenaría un hueco pequeño el 77%+ de las veces por pura aleatoriedad — no hay control estadístico riguroso publicado. Y funciona "en mercados laterales", pero "pierde su ventaja en mercados en tendencia", según las propias fuentes de brokers.

**(f)** No recomendable seguir investigando: descartar de la lista de hipótesis a probar dado el cambio estructural de mayo 2026.

### 4.6 Vencimiento de opciones (Deribit, max pain)

**(a) Regla exacta (teoría "max pain"):** el precio de BTC gravita hacia el strike donde el mayor open interest de opciones expira sin valor (mínimo pago para los vendedores) en la fecha de vencimiento (semanal/mensual/trimestral en Deribit).

**(c) Resultados/evidencia:** evidencia académica reciente **refuta** la teoría — Filippou, Garcia-Ares & Zapatero encuentran que la aparente predictibilidad del "max pain" se explica en realidad por efectos de reversión de precio y actividad de trading relacionada con el vencimiento, no por un "imán" real de precio. Ejemplos recientes citados: en junio 2026 el mercado cotizó ~$11,000 por debajo del nivel de max pain que se esperaba como imán — [Investing.com / Techtimes, "Bitcoin Options Expiry Debunks Max Pain Theory"](https://www.techtimes.com/articles/319043/20260625/bitcoin-options-expiry-debunks-max-pain-theory-etf-outflows-rewrite-playbook.htm).

**(e) Críticas:** clasificación clara: **afirmación de marketing sin respaldo académico robusto** — la evidencia académica disponible apunta en contra del efecto "max pain" como estrategia de precio, y los ejemplos recientes de mercado lo confirman empíricamente. No priorizar.

### 4.7 Estacionalidad mensual/trimestral ("sell in May")

**(c) Resultados reportados:** evidencia contradictoria incluso dentro de la misma búsqueda: mayo tiene retorno medio histórico de +22.1% desde 2011 (top 6 en retorno medio, top 3 en retorno mediano), pero **junio-septiembre muestran retornos consistentemente por debajo de la media ("summer lull")**. Por trimestre: **Q4 es la temporada más fuerte (+85.4% media, +52.3% mediana)**; Q3 tiende a ser flojo o negativo — fuente agregada (CoinDesk/Yahoo Finance sobre paper de estacionalidad cripto, sin URL de paper original encontrada con detalle metodológico completo).

**(e) Críticas:** el titular "sell in May" es literalmente contradicho por el dato de que mayo es uno de los mejores meses en media — es un ejemplo de cómo el periodismo financiero reusa un cliché de acciones sin verificar si aplica a cripto. La pauta trimestral (Q4 fuerte, Q3 débil) tiene más solidez narrativa (coincide con ciclos de halving y con el "Uptober" que se menciona cada año), pero la muestra sigue siendo de solo ~12-13 años de datos de BTC, es decir, muy pocos Q4/Q3 independientes para significancia estadística real.

**(f)** Testear la estacionalidad Q4 vs Q3 con tus propios datos desde 2013, y verificar si el efecto es robusto excluyendo el año de cada halving (para descartar que "Q4 fuerte" sea solo "el trimestre post-halving es fuerte", que es una historia distinta).

---

## 5. Estrategias con derivados

### 5.1 Funding rate contrarian / carry

**(a) Reglas exactas:**
- *Contrarian direccional:* funding rate anualizado extremadamente positivo (>0.05-0.1% cada 8h) = mercado sobre-apalancado en largos → señal de venta/corto por riesgo de cascada de liquidaciones. Funding muy negativo = señal de pánico vendedor → posible oportunidad de largo contrarian (caso histórico: marzo 2020, funding entre -0.05% y -0.15% cada 8h).
- *Carry neutral (delta-neutral):* comprar spot BTC + vender futuro perpetuo simultáneamente cuando el funding es positivo, cobrando el funding periódicamente sin exposición direccional.

**(b) Timeframe:** funding se paga cada 8h en la mayoría de exchanges (Binance, etc.); la señal se evalúa en esa frecuencia.

**(c) Resultados reportados:** un funding de 0.1% cada 8h equivale a **~10.95% anualizado** en la variante carry — cifra de cálculo directo (matemática del propio mecanismo, no un backtest con drawdowns). La variante de arbitraje delta-neutral muestra **baja correlación con buy-and-hold** (beneficio de diversificación), según fuentes agregadas de la industria (Kraken Learn, Bitget Academy) sin backtest académico con Sharpe/drawdown identificado específicamente.

**(e) Críticas:** (1) la variante *carry* (delta-neutral) es la más sólida conceptualmente porque no depende de acertar dirección — pero **no es ejecutable manualmente vía señales de Telegram en Quantfury**, porque requiere posición simultánea en spot y en perpetuo en dos venues distintos con reajuste continuo; es una estrategia de infraestructura, no de "señal + click". (2) La variante *contrarian direccional* (funding extremo → operar en contra) es más ejecutable manualmente, pero la evidencia es en gran parte anecdótica (el ejemplo de marzo 2020 es un solo evento extremo, no un backtest sistemático con muchas repeticiones).

**(f) Cómo testearlo honestamente:** para la variante contrarian, define umbrales de funding extremo con datos históricos de Binance/Bybit (gratuitos vía API), backtest sistemático de "funding > percentil 95 histórico → señal corta a N días" y "funding < percentil 5 → señal larga a N días", con salida a tiempo fijo, y compáralo con simplemente holdear. Dado que tú operas en Quantfury (no en el exchange de derivados), el funding rate sería una *señal externa* de otro mercado (ej. Binance perpetual) para decidir una operación spot en Quantfury — factible y merece prioridad alta.

### 5.2 Cash-and-carry basis trade

**(a) Reglas exactas:** comprar BTC spot + vender futuro CME/perpetuo cuando el futuro cotiza en contango con prima suficiente sobre el spot; mantener hasta vencimiento (o rolar) capturando la convergencia precio futuro→spot.

**(c) Resultados reportados:** versión institucional apunta a **8-15% anualizado con drawdown mínimo** en condiciones normales de contango. En momentos de euforia extrema (abril 2021) la prima anualizada llegó a **44-48%** en varios exchanges simultáneamente — cifra histórica puntual, no sostenida. Costes de rolo trimestral en CME consumen **0.1-0.3% del nocional por rollo**, restando 1-2 puntos porcentuales anuales al rendimiento neto. Fuentes agregadas sin backtest académico único identificado; ver [crypto.news](https://crypto.news/what-is-basis-trading-cash-and-carry-arbitrage-explained/) y [CME Group OpenMarkets sobre ETFs y basis trading](https://www.cmegroup.com/openmarkets/equity-index/2025/Spot-ETFs-Give-Rise-to-Crypto-Basis-Trading.html).

**Dato reciente relevante (septiembre 2026):** la base anualizada de futuros CME de BTC ha caído a **-2.35%, la backwardation más profunda desde el colapso de FTX en 2022** — [CoinDesk](https://www.coindesk.com/markets/2025/12/03/bitcoin-futures-return-to-deepest-backwardation-since-ftx-collapse). Esto significa que, a día de hoy, el cash-and-carry clásico (comprar spot, vender futuro) **no es rentable** — de hecho el trade inverso (reverse cash-and-carry) sería el que pagaría, si fuera operable.

**(e) Críticas:** es una estrategia de infraestructura para institucionales con acceso a CME/futuros regulados y financiación barata — **no aplicable a tu setup de Quantfury/Telegram manual**. La incluyo por completitud y porque el signo actual de la base (negativa) es información de contexto útil: un mercado en backwardation profunda suele reflejar estrés de financiación o sentimiento muy bajista de corto plazo entre traders apalancados, lo cual sí podría usarse como *señal de contexto* (no como trade en sí) para tu bot.

**(f)** No priorizar como estrategia ejecutable; sí considerar el signo y magnitud de la base CME como *feature* de contexto de mercado si tienes acceso a ese dato.

### 5.3 Open interest + precio

**(a) Reglas exactas (heurística de mercado, no backtest formal encontrado):** precio sube + OI sube + volumen alto = convicción fuerte (continuación). Precio sube + OI plano/baja = posible techo de manos débiles/pocos participantes controlando el movimiento (reversión). Precio plano + OI sube rápido = posible ruptura inminente.

**(c) Resultados reportados:** **no se encontró ningún backtest cuantitativo público con números de retorno/Sharpe/drawdown** para "divergencia OI-precio" en BTC — todo lo encontrado es descripción cualitativa de blogs de exchanges (CryptoQuant, Bitsgap, CoinDCX) sin verificación estadística independiente.

**(e) Críticas:** clasificación clara: **hipótesis intuitiva sin evidencia cuantitativa pública**. Es plausible como *feature* dentro de un modelo más amplio (ej. tu clasificador de v13), pero no como regla aislada.

**(f)** Si quieres testearla, la forma honesta es: define divergencia OI-precio como (variación % de OI) - (variación % de precio) en una ventana de N horas, y backtest sistemático de si esa divergencia predice el retorno de las siguientes N horas — dataset necesario: OI histórico de Binance/Bybit (disponible vía API gratuita).

### 5.4 Cascadas de liquidación

**(a) Reglas exactas (conceptual):** identificar clusters de liquidación estimados (heatmap) cerca del precio actual; operar a favor de la cascada cuando se rompe un cluster grande (el movimiento se acelera por el cierre forzoso de posiciones apalancadas).

**(c) Resultados reportados:** **ningún backtest cuantitativo público encontrado** — todo el material es descriptivo/educativo de proveedores de heatmaps (Mudrex, Coinperps, BitcoinCounterFlow, Zipmex), que son también quienes venden el dato, con conflicto de interés evidente.

**(e) Críticas:** clasificación clara: **producto comercial con narrativa plausible pero sin evidencia académica ni backtest independiente**. Los heatmaps de liquidación son estimaciones (no datos reales, ya que los exchanges no publican niveles de liquidación de otros usuarios), calculados con supuestos de apalancamiento medio que pueden estar equivocados.

**(f)** Si se quiere explorar, la vía honesta es usar datos de liquidaciones *reales* ya ocurridas (no estimadas) — varios exchanges (Binance, Bybit) publican feed de liquidaciones ejecutadas — y backtestear si un volumen anómalo de liquidaciones en una ventana corta predice reversión a corto plazo (mean reversion post-cascada), que es la hipótesis más razonable y testable con datos reales en vez de estimaciones de heatmap.

---

## 6. Estrategias on-chain

### 6.1 MVRV (Market Value to Realized Value)

**(a) Reglas exactas:** MVRV = capitalización de mercado / capitalización realizada (coste base agregado de todos los holders). MVRV > 3.5 → señal de fase tardía de ciclo alcista / riesgo de distribución. MVRV < 1.0 → gran parte del supply en pérdida → señal histórica de capitalización/suelo de mercado.

**(c) Resultados reportados:**
- Regla combinada MVRV<1.0 Y SOPR<1.0 (capitulación doble) ha precedido, según Glassnode, **todos los grandes suelos de BTC desde 2015**; ejemplo concreto: noviembre 2022, MVRV=0.84 y SOPR=0.92, BTC tocó fondo en $15,500 y subió 240% en 18 meses — fuente: Glassnode research (citado agregadamente, ["theledgermind.com"](https://theledgermind.com/bitcoin-mvrv-ratio-analysis/) y estudios de Glassnode Studio).
- **Paper académico riguroso (Klaus Grobys, "Using on-chain data to predict Bitcoin cycles", ScienceDirect 2026):** el uso de MVRV Z-score mejora el Sharpe ratio de **0.45 (buy-and-hold) a 1.28**, superando también estrategias de entrada aleatoria — https://www.sciencedirect.com/science/article/pii/S0275531926002138 y versión preprint en https://osuva.uwasa.fi/server/api/core/bitstreams/6575b90c-6140-44e7-a798-011a1793d134/content

**(d) Periodo:** el paper de Grobys cubre múltiples ciclos de mercado de BTC (no se especificó el rango exacto en el extracto disponible, pero el propio título indica que evalúa "a través de los principales ciclos de mercado").

**(e) Críticas:** (1) el problema de fondo (n bajo) — solo ha habido 3-4 ciclos completos de MVRV extremo en la historia de BTC, por lo que "ha predicho todos los suelos desde 2015" es una afirmación técnicamente cierta pero con un tamaño de muestra de apenas 3-4 eventos, no suficiente para inferencia estadística robusta. (2) Es una señal de **muy baja frecuencia** (útil para "acumular en zona de valor" a horizonte de meses/años, no para trading activo de 15m/1h/4h/1d con 5 posiciones simultáneas). (3) El paper académico sí es la evidencia más sólida de toda esta sección — clasificar como "evidencia decente", a diferencia de las cifras de blogs de MVRV que son "afirmación con respaldo débil" (n bajo, sin paper revisado por pares).

**(f) Cómo testearlo honestamente:** dado que es señal de ciclo largo, no encaja directamente en tu operativa de 15m-1d con 5 posiciones — pero sí podría usarse como **filtro macro de "modo mercado"** (ej. reducir tamaño de posición o desactivar estrategias de compra cuando MVRV > 3.5). Testear con datos históricos de Glassnode (API gratuita limitada disponible) el Sharpe real de un filtro binario simple antes de complicarlo.

### 6.2 SOPR (Spent Output Profit Ratio)

**(a) Reglas exactas:** SOPR = valor fiat al gastar / valor fiat al recibir, agregado de todas las UTXOs movidas. SOPR > 1 = ganancias netas realizadas; SOPR < 1 = pérdidas netas realizadas. Usado sobre todo combinado con MVRV (ver 6.1) para señales de capitulación.

**(c) Resultados reportados:** no se encontró un backtest cuantitativo independiente de SOPR *aislado* con cifras de Sharpe/retorno — solo el uso combinado con MVRV citado arriba, y descripciones metodológicas de Glassnode sobre cómo backtestear ("Backtesting in Workbench", https://insights.glassnode.com/backtesting-in-workbench/) sin resultados numéricos publicados de forma abierta.

**(e) Críticas:** clasificación: **métrica plausible pero sin evidencia cuantitativa aislada pública** — solo tiene valor evidenciado en combinación con MVRV, no por sí sola.

### 6.3 Exchange netflow / reservas

**(c) Resultados reportados:** **no se encontró evidencia académica cuantitativa** de una estrategia de netflow de exchanges con resultados de backtest verificables. La literatura académica disponible es más bien escéptica en general: un survey de arXiv sobre predictibilidad de BTC concluye que **"a horizontes corto-medio plazo, ningún estudio revisado por pares ha mostrado superioridad robusta sobre el baseline ingenuo (naive) a través de múltiples regímenes de mercado"**, y que "la predictibilidad diaria es real pero no se extiende a horizontes horarios o mensuales, y puede no sobrevivir a los costes de transacción".

**(e) Críticas:** clasificación clara: **afirmación de marketing sin respaldo cuantitativo público verificado**. El netflow de exchanges es intuitivamente razonable (salida de exchanges = intención de holdear = presión de venta futura menor) pero cada vez más contaminado por el auge de custodia institucional, ETFs y cold storage de exchanges que no reflejan sentimiento retail.

**(f)** Si se quiere testear, usar datos de netflow gratuitos (CryptoQuant tiene tier gratuito limitado) y backtestear sistemáticamente contra retorno futuro a 24h/7d/30d, controlando por tendencia de precio previa (para evitar confundir "netflow negativo" con "la gente ya estaba en modo hodl porque el precio subía").

### 6.4 Evaluación académica general de indicadores on-chain

**Hallazgo importante (arXiv, "From On-chain to Macro"):** ciertas métricas de oferta/balance (realized value, unrealized value) tienen "especialmente alto poder predictivo para la dirección del precio al día siguiente"; las variables on-chain "mejoran repetidamente el rendimiento predictivo respecto a modelos de referencia" tanto para detección de fase de mercado como para timing de ciclo — https://arxiv.org/html/2506.21246

**Conclusión honesta de la sección on-chain:** hay más evidencia académica real detrás de MVRV/SOPR que detrás de netflow o de las narrativas de "ballenas acumulando" que circulan en Twitter/X. Pero incluso la mejor evidencia (Grobys, Sharpe 1.28) es de **frecuencia baja (ciclo de mercado)**, no aplicable directamente a tus timeframes de 15m-1d con holding corto.

---

## 7. Volatilidad

### 7.1 Compresión de rango / squeeze (Bollinger dentro de Keltner)

**(a) Reglas exactas:** squeeze "activado" cuando las Bollinger Bands (SMA20 ± 2σ) quedan completamente dentro del Keltner Channel (EMA20 ± 1.5·ATR); squeeze "dispara" cuando BB vuelve a salir del KC — se opera en la dirección de la ruptura, confirmada con momentum/volumen.

**(c) Resultados reportados:** solo descripciones cualitativas de mecánica de la estrategia (TrendSpider, Medium/PyQuantLab, TradingView) — **no se encontró backtest público con cifras de Sharpe/retorno/drawdown específicas para BTC**. Es una de las estrategias técnicas más citadas en foros y redes, pero con la evidencia cuantitativa más débil de todo el documento en proporción a su popularidad.

**(e) Críticas:** clasificación: **popular pero sin respaldo cuantitativo público verificado para BTC**. Es plausible (la compresión de volatilidad precede estadísticamente a la expansión, esto es casi tautológico por cómo se define volatilidad), pero la dirección de la ruptura es lo difícil de predecir, y ningún backtest público cuantifica el win rate real de "operar la dirección del squeeze".

**(f)** Testeable con tus propios datos: define el squeeze exactamente como arriba, mide cuántas veces por año ocurre en BTC 1h/4h, y el resultado direccional de operar la ruptura vs. simplemente esperar y no operar el squeeze (control).

### 7.2 Régimen de volatilidad / percentil de ATR

**(a) Reglas exactas:** calcular ATR(14), rankearlo en percentil sobre los últimos 100 periodos; evitar operar por debajo del percentil 20 (mercado "dormido", señales poco fiables) o por encima del percentil 90 (volatilidad errática/impredecible).

**(c) Resultados reportados:** estudio académico SSRN (Poluri) combinando Donchian breakout + filtro de régimen ATR: **"mejora significativa sobre buy-and-hold"** pero **"altamente sensible a costes de transacción, ajuste de parámetros y condiciones de mercado"** — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6272239. Backtest de breakout + trailing ATR en 8h: retorno total 1404.9%, pero **drawdown máximo de 81.3%** y solo 5 operaciones en todo el periodo — [Coinquant](https://www.coinquant.ai/blog/how-to-use-atr-in-a-crypto-trading-strategy-with-backtest). El drawdown del 81% hace esta configuración concreta inviable para gestión de riesgo real, a pesar del retorno total espectacular (ejemplo perfecto de por qué "retorno total" sin drawdown es una métrica incompleta y engañosa).

**(e) Críticas:** el filtro de régimen ATR es conceptualmente sólido (evitar operar en extremos de volatilidad), pero **los umbrales fijos (percentil 20/90) se calibran sobre datos históricos y pueden dejar de ser válidos si el régimen de volatilidad estructural de BTC cambia** (ej. BTC 2026 con ETFs institucionales tiene, en general, menor volatilidad realizada que BTC 2017-2018).

**(f)** Recalibrar el percentil de forma rodante (rolling), no fija, y verificar que el filtro se sigue ajustando razonablemente en 2024-2026 vs. 2017-2020.

### 7.3 Volatility targeting

**(a) Reglas exactas:** ajustar el tamaño de posición de forma inversamente proporcional a la volatilidad reciente realizada, para mantener un riesgo objetivo constante (ej. 15% de volatilidad anualizada objetivo en la cartera).

**(c) Resultados reportados:** simulaciones genéricas (no específicas de BTC) muestran mejora de Sharpe de 1.62 a 1.79 (+10% en términos relativos) al aplicar volatility targeting — fuente agregada (Medium/Jirong Huang), sin backtest específico de BTC con cifras propias. Mención de Alpha Architect: "las metodologías de volatility-targeting son efectivas para controlar el riesgo" y "las estrategias trend-following han funcionado bien" en cripto, en términos generales sin backtest desglosado.

**(e) Críticas:** el concepto de volatility targeting es una técnica de **gestión de riesgo/tamaño de posición**, no una señal de entrada/salida en sí misma — no genera alpha nuevo, redistribuye el riesgo a lo largo del tiempo. Es más relevante para tu money management (cuánto arriesgar por señal dado tu límite de 5 posiciones simultáneas) que como fuente de señal.

**(f)** Aplicar como capa de gestión de riesgo sobre cualquier estrategia de señal que elijas, no como estrategia independiente — reducir tamaño cuando ATR/volatilidad realizada esté en el percentil alto, aumentar cuando esté en el percentil bajo.

---

## 8. Relative value (BTC vs ETH, dominancia, momentum transversal)

### 8.1 Pairs trading BTC-ETH

**(a) Reglas exactas:** cointegración/z-score del ratio ETH/BTC; entrar largo en el activo relativamente barato y corto en el relativamente caro cuando el z-score del spread supera un umbral (ej. ±2), cerrar en reversión a la media del spread.

**(c) Resultados reportados:**
- Tesis académica (Erasmus University Rotterdam), "Pairs Trading in the Cryptocurrency Market": excess return medio de **13.9% por par**, retorno mensual de cartera del 12%, Sharpe anualizado de **3.00** — https://thesis.eur.nl/pub/67552/Thesis-Pairs-trading-.pdf (verificar universo y periodo exactos leyendo la tesis completa antes de confiar en la cifra).
- Estrategias ML/LSTM de alta frecuencia (5 min) reportan hasta **205.9% anualizado y Sharpe 3.77** — cifras extraordinariamente altas que requieren escrutinio: a esa frecuencia el coste de spread y ejecución en Quantfury manual sería prohibitivo, y probablemente estas cifras no sobrevivirían fuera del entorno de backtest de alta frecuencia con ejecución asumida perfecta.

**(e) Críticas:** (1) las cifras de Sharpe 3+ en cripto casi siempre indican una de dos cosas: o el backtest no incluye costes de transacción/spread realistas, o el periodo de muestra es corto/favorable. (2) Pairs trading BTC-ETH requiere posiciones simultáneas largo+corto — **operativamente difícil o imposible en Quantfury vía señales manuales de Telegram** si no tienes forma sencilla de ir corto en ETH mientras vas largo en BTC con el timing exacto necesario. (3) La cointegración BTC-ETH no es estable — ambos activos han mostrado periodos de correlación >0.9 donde el "spread" apenas tiene reversión que capturar.

**(f)** Si tu bróker permite carteras largo/corto simultáneas, testear con datos propios el z-score del ratio ETH/BTC diario desde 2018, con costes de spread realistas en ambas patas, antes de creer las cifras del paper.

### 8.2 Dominancia de BTC / rotación a altcoins

**(a) Reglas exactas (heurística, no backtest formal encontrado):** cuando BTC.D (dominancia) cae por debajo de umbrales (50%, luego 40%), confirmado con TOTAL2/TOTAL3 (capitalización total ex-BTC) y el ratio ETH/BTC, rotar capital de BTC hacia altcoins.

**(c) Resultados reportados:** **no se encontró backtest cuantitativo público** con cifras de retorno/Sharpe — solo descripciones narrativas de blogs de exchanges/educación cripto. Dato honesto encontrado: *"el drift del índice y las inconsistencias de ticker dificultan backtestear correctamente"* la dominancia — cita explícita que reconoce el problema de calidad de datos para este tipo de estrategia. Duración histórica de "altcoin seasons": 8-16 semanas de media (dato descriptivo, no un backtest de estrategia).

**(e) Críticas:** clasificación clara: **narrativa de mercado ampliamente repetida sin backtest cuantitativo público verificado**. Esto no significa que sea falsa, sino que no hay evidencia dura disponible — y dado que tu objetivo declarado es centrarte en BTC (con extensión futura a ETH y otras), esta estrategia es de menor prioridad y mayor complejidad operativa (requiere trackear TOTAL2/TOTAL3, mucho más ruido).

### 8.3 Momentum cross-sectional entre monedas

Ver sección 1.3 — evidencia de que el momentum cross-sectional es "débil" comparado con el time-series momentum (Han, Kang & Ryu, SSRN). Nota adicional: paper de Alpha Architect/académico sobre 3-factor model cripto (mercado, tamaño, momentum) encuentra que 10 características cripto forman estrategias long-short "con retornos en exceso considerables y estadísticamente significativos", explicadas por ese modelo de 3 factores — pero de nuevo, esto es sobre una cesta amplia de criptomonedas, no aplicable directamente a "solo BTC".

**Dato de comportamiento retail interesante (Alpha Architect):** los traders retail son contrarian en acciones y oro, pero momentum en cripto — hipótesis: los cambios de precio en cripto afectan la expectativa de adopción futura, reforzando la dirección del movimiento. Es una explicación de por qué el momentum *podría* funcionar estructuralmente en cripto (mecanismo de creencias reflexivo), más que una estrategia en sí.

---

## 9. DCA inteligente y grid trading — por qué suelen romperse

### 9.1 DCA (Dollar Cost Averaging) vs. lump sum

**(c) Resultados reportados:**
- Lump-sum superó a DCA en **66% de las simulaciones** (igual que en mercados tradicionales), pero con brechas de rendimiento mucho mayores en cripto por la volatilidad alcista explosiva de BTC.
- En BTC específicamente, DCA quedó por debajo del lump-sum en un **341% de media a 24 meses** en el periodo de subidas fuertes analizado — cifra dramática que depende enteramente de qué ventana de 24 meses se elige (obviamente si el lump-sum se hace justo antes de un rally, gana por mucho).
- Sin embargo, DCA **reduce consistentemente el drawdown máximo** en carteras 100% BTC, manteniendo rendimiento similar en algunos escenarios — el trade-off real es "menor riesgo de timing" a cambio de "menor retorno esperado en mercados estructuralmente alcistas".

**(e) Críticas:** DCA no es una "estrategia" en el sentido de generar alpha — es una técnica de **gestión del riesgo de timing de entrada**. Su comparación contra lump-sum solo tiene sentido si asumes que no tienes ninguna capacidad de timing; para un bot con señales activas, la pregunta relevante no es "DCA vs lump sum" sino "¿mi señal de timing es mejor que promediar ciegamente?" — y esa es literalmente la pregunta que ya te hace tu proyecto entero.

### 9.2 Por qué el grid trading se rompe

**(a) Mecánica:** el grid coloca órdenes de compra/venta escalonadas dentro de un rango de precio predefinido, comprando en cada bajada de un escalón y vendiendo en cada subida, capturando el "ruido" dentro del rango.

**(c)/(e) Evidencia y crítica (ambas fusionadas porque es la misma fuente):** **el grid trading está diseñado explícitamente para mercados laterales y falla estructuralmente en mercados con tendencia fuerte.** Ejemplo citado: cuando BTC subió 15% en un solo día, el bot de grid "siguió vendiendo su posición en la subida, quedándose en stablecoins mientras el mercado volaba" — es decir, el grid **vende los ganadores demasiado pronto y mantiene los perdedores demasiado tiempo** en mercados de tendencia, lo opuesto exacto de lo que quieres. Si BTC rompe por encima del techo del grid y sigue subiendo, el bot deja de operar y te pierdes toda la tendencia (no tiene mecanismo para "perseguir" el precio fuera de rango a menos que se reconfigure manualmente). Fuente: [Finextra, "Why Most Grid Bots Fail"](https://www.finextra.com/blogposting/30160/why-most-grid-bots-fail-and-how-you-can-build-a-better-one); mecánica confirmada también en Bitsgap, Coinquant, Wundertrading.

**Conclusión estructural:** el grid trading no es una estrategia con un "problema de parámetros" que se pueda arreglar optimizando — es una estrategia que **apuesta implícitamente a que el mercado es lateral**, lo cual es una apuesta direccional disfrazada de neutralidad. En un activo como BTC con episodios de tendencia fuerte y prolongada, el grid necesita reconfiguración activa y frecuente del rango, lo que en la práctica lo convierte en un trabajo manual constante, no en un sistema "configura y olvida" como se suele vender.

---

## 10. Estrategias con evidencia académica publicada (síntesis transversal)

Esta sección reúne los papers académicos más citados a lo largo del documento, para que tengas la lista de referencia consolidada:

| Paper | Foco | Hallazgo clave | URL |
|---|---|---|---|
| Padyšák & Vojtko (2022) | Estacionalidad + trend + mean reversion BTC | Ventana horaria 21-23h UTC ~33% anualizado; MAX (momentum en máximos) > MIN (mínimos) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4081000 |
| Beluská & Vojtko (2024) | Revisión out-of-sample 2022-2024 | MAX sigue vivo; MIN se degrada; sin estacionalidad diaria significativa en la muestra extendida | https://quantpedia.com/revisiting-trend-following-and-mean-reversion-strategies-in-bitcoin/?a=6080 |
| Huang, Sangiorgi & Urquhart (2024) | TSMOM ponderado por volumen, 3192 cryptos | 0.94%/día, Sharpe 2.17; con pesos iguales pierde -1.19%/día | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4825389 |
| Han, Kang & Ryu (2023) | TSMOM y cross-sectional momentum con supuestos realistas | Muchas carteras "significativas" se liquidan o ganan poco tras costes reales; TSMOM fuerte, cross-sectional débil | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565 |
| Grobys (2026) | On-chain (MVRV Z-score) para timing de ciclo | Sharpe 0.45 (buy&hold) → 1.28 con MVRV Z-score | https://www.sciencedirect.com/science/article/pii/S0275531926002138 |
| Poluri (SSRN) | Donchian + filtro ATR régimen | Mejora vs. pasivo, pero muy sensible a costes/parámetros | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6272239 |
| Efe Arda (SSRN) | Bollinger breakout vs. reversión por régimen | Breakout gana en bajista 2018; reversión recupera algo en acumulación 2018-2020 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5775962 |
| Filippou, Garcia-Ares & Zapatero | Teoría "max pain" en opciones | Refutada: la predictibilidad se explica por reversión de precio, no por imán de max pain | (referenciado vía Techtimes) |
| arXiv 2606.00060 (2026) | ML (XGBoost/LSTM/iTransformer) BTC horario con costes | Señal naive falla con 10bps de coste; filtro de ejecución "cost-aware" recupera rentabilidad; mejor config: +65% anualizado, Sharpe >1 | https://arxiv.org/abs/2606.00060 |
| arXiv 2009.12155 | Década de evidencia trend-following en cripto | Evidencia de una década a favor del TSMOM | https://arxiv.org/pdf/2009.12155 |
| Erasmus Univ. (tesis) | Pairs trading cripto | Excess return 13.9%/par, Sharpe 3.00 (verificar metodología completa) | https://thesis.eur.nl/pub/67552/Thesis-Pairs-trading-.pdf |

**Patrón transversal más importante de toda la revisión académica:** el mensaje que se repite en los papers más rigurosos (Han et al., el survey de predictibilidad citado en la sección 6.3, y el paper de ML con costes de transacción) es siempre el mismo: **el edge que aparece en el backtest bruto se reduce sustancialmente —a veces hasta desaparecer— cuando se incorporan costes de transacción y ejecución realistas.** Esto debe ser tu filtro por defecto para cualquier cifra "bonita" de este documento.

---

## 11. Repositorios de GitHub (ordenados por credibilidad)

Todos verificados por descripción/README; **no se ha ejecutado ningún código**, solo se documenta qué son y qué reportan sus propios autores/comunidad.

### Nivel alto de credibilidad (proyectos maduros, muchas estrellas, mantenimiento activo)

1. **freqtrade/freqtrade** — https://github.com/freqtrade/freqtrade — bot de trading cripto open-source más usado, ~11,000+ estrellas, con motor de backtesting integrado, optimización de hiperparámetros (hyperopt) y soporte multi-exchange. Es infraestructura, no una estrategia concreta — pero es el estándar de facto para *validar* cualquier estrategia con datos históricos reales antes de asumir que funciona.
2. **iterativv/NostalgiaForInfinity** — https://github.com/iterativv/NostalgiaForInfinity — la estrategia comunitaria de Freqtrade más popular y longeva, ~3,400 estrellas, ~750 forks, ~26,600 commits, comunidad activa en Discord con actualizaciones constantes. Optimizada para pares USDT/USDC (no BTC/ETH como base), timeframe de 5 min, cartera de 6-12 posiciones simultáneas sobre 40-80 pares — es decir, una filosofía de "muchas apuestas pequeñas diversificadas", bastante distinta a tu enfoque de máximo 5 posiciones en BTC. Útil como referencia de ingeniería de estrategia (gestión de riesgo, múltiples condiciones de entrada/salida en capas) más que como estrategia a copiar literalmente.
3. **freqtrade/freqtrade-strategies** — https://github.com/freqtrade/freqtrade-strategies — repositorio oficial de ejemplos, ~5,400 estrellas. Los propios mantenedores avisan de que son "puntos de partida", no estrategias listas para producción.

### Nivel medio (útiles como referencia de código/backtesting, no como fuente de edge)

4. **polakowo/vectorbt** — motor de backtesting vectorizado en Python, muy usado en la comunidad quant para prototipar rápido miles de combinaciones de parámetros (también el que más facilita el sobreajuste si no se usa con disciplina de walk-forward).
5. **kernc/backtesting.py** — librería de backtesting simple y popular, buena para prototipos rápidos de las reglas descritas en este documento.
6. **robcarver17/pysystemtrade** — framework completo de trading sistemático de Robert Carver (autor de referencia en trend-following institucional para futuros), aplicable conceptualmente a cripto aunque diseñado originalmente para futuros tradicionales — su libro y código son la referencia más seria de la industria para "cómo dimensionar posiciones y combinar señales de trend-following con disciplina de riesgo".
7. **nautechsystems/nautilus_trader** — motor de trading de alto rendimiento, más orientado a ejecución institucional/HFT que a tu caso de uso.

### Nivel bajo / experimental (tratar con escepticismo, verificar antes de usar cualquier cifra)

8. **paulcpk/freqtrade-strategies-that-work** — https://github.com/paulcpk/freqtrade-strategies-that-work — 329 estrellas, 5 estrategias simples (cruces EMA/MACD/RSI con filtro de tendencia), backtest propio 2018-2020 en 8 pares a 1h, mejor resultado 122.5% en 2 años — el propio autor las etiqueta como "altamente experimentales, solo para fines educativos". Útil como ejemplo de código simple, no como fuente de edge verificado.
9. **davidzr/freqtrade-strategies** — colección comunitaria adicional, sin verificación de resultados encontrada.
10. Estrategias sueltas de TradingView (Pine Script) mencionadas en las búsquedas ("Trend Daddy Bitcoin Strategy", "BTC Algo Strategy", etc.) — **credibilidad muy baja**: son scripts de autores anónimos/pseudónimos, con backtests que casi nunca declaran slippage/comisiones reales, y en muchos casos código cerrado ("protected source") que impide verificar la lógica real. No recomendable como fuente de estrategias, solo como inspiración de nomenclatura de indicadores.

### Listas curadas (meta-repositorios, no estrategias en sí)

- **botcrypto-io/awesome-crypto-trading-bots** — https://github.com/botcrypto-io/awesome-crypto-trading-bots
- **wangzhe3224/awesome-systematic-trading** — https://github.com/wangzhe3224/awesome-systematic-trading
- **SpiralDevelopment/Awesome-Crypto-Trading** — https://github.com/SpiralDevelopment/Awesome-Crypto-Trading

---

## 12. Cómo testear honestamente cualquier estrategia de este documento (checklist transversal)

1. **Nunca un solo backtest sobre todo el histórico.** Partir en al menos 3 tramos: entrenamiento/calibración, validación out-of-sample, y un tercer tramo "hold-out" que no se toca hasta el final.
2. **Incluir obligatoriamente los tres regímenes:** un mercado alcista fuerte (2020-21), un mercado bajista prolongado (2022) y un mercado lateral (2019, o gran parte de 2023). Si la estrategia solo funciona en uno de los tres, no es un sistema, es una apuesta direccional camuflada.
3. **Coste de transacción realista para TU caso concreto:** en Quantfury no pagas comisión pero sí spread — modela el spread real que observas en tus operaciones (no asumas cero fricción). La sección 10 muestra que esto es, con diferencia, lo que más infla los backtests optimistas de este documento.
4. **Reportar siempre drawdown máximo y profit factor, nunca solo win rate ni solo retorno total.** La sección 3.1 (78 backtests) demuestra que el win rate alto puede coexistir con pérdida neta.
5. **Contar el número de señales/operaciones reales.** Una estrategia con 8 señales en 5 años (ej. golden cross) no se puede evaluar con las mismas herramientas estadísticas que una con 500 operaciones — el margen de error de la primera es enorme.
6. **Desconfiar de cualquier Sharpe > 2.5 en un backtest de cripto** salvo que el paper declare explícitamente costes de transacción, slippage y un universo líquido (BTC/ETH, no altcoins ilíquidas) — es prácticamente el patrón que se repite en cada cifra "demasiado buena" de este documento.
7. **Verificar si el "edge" sobrevive excluyendo el mejor trimestre/año del backtest.** Si quitar el mejor Q4 o el mejor rally hace que la estrategia pierda frente a buy-and-hold, el edge es frágil, no estructural.

---

## 13. RANKING FINAL — Las 15-20 hipótesis más prometedoras para probar primero

Ordenadas por (evidencia disponible × viabilidad de ejecución manual en Quantfury/Telegram × relevancia para tus timeframes 15m-1d en BTC). Se penaliza fuerte todo lo que requiera posiciones simultáneas largo+corto o infraestructura de derivados que no tienes.

1. **Time-series momentum puro en BTC (sin cross-sectional), con salida por trailing ATR en vez de horizonte fijo.** Es la hipótesis con más papers académicos de acuerdo (Han et al., Huang et al., arXiv 2009.12155) y es la que más se diferencia de lo que ya probaste (cruces de medias con salida fija) — el cambio clave a testear es la *salida dinámica*, no solo la entrada.
2. **Filtro de régimen ATR (percentil de volatilidad rodante) como capa previa a cualquier señal**, no como estrategia en sí — evidencia académica sólida (Poluri) de que mejora breakout systems, y encaja con tu conclusión de que el screening a horizonte fijo "solo sirve para descartar": esto es exactamente ese tipo de filtro, bien evidenciado.
3. **Estacionalidad horaria 21:00-23:00 UTC, retesteada por separado en pre-2022 y post-2022** con tus propios datos — evidencia académica concreta (Padyšák & Vojtko) pero con la seria advertencia de que la revisión de los mismos autores no la replica hasta 2024; alta prioridad precisamente porque es barata de testear y daría una respuesta rápida de sí/no.
4. **Mean reversion (RSI2 o distancia a MA) SOLO como filtro dentro de tendencia alcista confirmada (precio > MA200), nunca aislado.** La evidencia de Coinquant (78 backtests) es muy clara sobre por qué falla en aislado y por qué depende del régimen — esto convierte una estrategia "rota" en una potencialmente útil si se combina bien.
5. **Funding rate extremo (percentiles históricos) como señal contrarian direccional en BTC spot**, usando funding de Binance/Bybit como señal externa para decidir entradas/salidas en Quantfury — dato gratuito, mecanismo con lógica de mercado clara (apalancamiento excesivo = riesgo de cascada), ejecutable manualmente.
6. **MVRV Z-score como filtro macro de "modo mercado" (reducir exposición o desactivar compras en zona de euforia extrema, aumentar en capitulación)**, no como señal de trading activo — evidencia académica real (Grobys, Sharpe 0.45→1.28) pero de frecuencia muy baja, así que su rol es de "interruptor macro", no de señal de entrada frecuente.
7. **Filtro de fin de semana / baja liquidez como reductor de tamaño de posición**, no como señal direccional — la evidencia de "retornos no consistentes" en fin de semana descarta usarlo para dirección, pero el patrón de menor liquidez/mayor riesgo de gap está bien documentado y es coherente con gestión de riesgo prudente.
8. **Donchian breakout con salida por ATR trailing (no por rotura contraria fija), backtest walk-forward completo 2017-2026 incluyendo los tres regímenes.** Buena evidencia de robustez multi-régimen (Coinquant, Poluri), y aísla si tu fallo anterior con "roturas de máximos" fue de entrada o de salida.
9. **Estacionalidad trimestral Q4 vs Q3, retesteada excluyendo el año de cada halving** para separar "efecto calendario" de "efecto halving" — barato de testear, ayuda a decidir si conviene sesgar el tamaño de posición por trimestre.
10. **Divergencia SOPR+MVRV combinada (capitulación doble) como señal de "zona de acumulación agresiva"**, de nuevo como interruptor macro de baja frecuencia, no señal frecuente — mecanismo con narrativa histórica consistente aunque n bajo.
11. **Combinación MIN+MAX de Padyšák/Vojtko/Beluská** (comprar en rotura de máximo de 10 días O en mínimo de 10 días) — es la única estrategia de la sección de trend/mean-reversion con evidencia de que se mantiene cerca de máximos históricos incluso en el out-of-sample 2022-2024; mejor candidato "combinado" ya validado por dos papers independientes de los mismos autores.
12. **Bollinger/Keltner squeeze como filtro de "no operar" (evitar entradas en compresión extrema) en vez de señal de ruptura direccional** — dado que no hay backtest público fiable de la dirección de ruptura, usarlo solo como filtro de "esperar" reduce el riesgo de operar en falso.
13. **Volatility targeting como capa de money management sobre cualquier señal elegida** — no genera alpha nuevo pero mejora el Sharpe de forma consistente en la literatura general; barato de implementar y bajo riesgo de sobreajuste porque no es una señal, es dimensionamiento.
14. **DCA condicionado por régimen de tendencia (DCA "inteligente": comprar más si precio > MA200 y menos/nada si precio < MA200)** en vez de DCA ciego o grid — combina lo mejor de la sección 9 (reduce riesgo de timing) sin la fragilidad estructural del grid puro.
15. **OI-precio como feature adicional (no señal aislada) dentro de un modelo más amplio tipo tu clasificador v13** — sin backtest público fiable en solitario, pero con lógica de mercado razonable; encaja mejor como una columna más de features que como regla propia.
16. **Backtest específico de "compra la caída" definida en unidades de ATR (no % fijo), incluyendo el ciclo completo 2021-2023 sin recortar la muestra** — para zanjar de una vez si el "buy the dip" clásico sobrevive fuera de los periodos favorables seleccionados a posteriori.
17. **Verificación explícita de si el edge de cualquier estrategia de la lista anterior sobrevive sin el mejor trimestre del backtest** — no es una estrategia nueva, es un requisito de validación que debería aplicarse a las 16 anteriores antes de poner dinero real.

**Descartadas explícitamente por falta de evidencia o por estar estructuralmente muertas:** gap del CME (estrategia con caducidad estructural desde mayo 2026 por el lanzamiento de futuros 24/7), max pain de opciones (evidencia académica en contra), cascadas de liquidación vía heatmap (sin backtest independiente, conflicto de interés del proveedor de datos), grid trading puro (fallo estructural documentado en mercados de tendencia), cash-and-carry / pairs trading largo-corto (no ejecutables en tu setup operativo actual de Quantfury manual vía Telegram con solo posiciones largas).
