# Investigación: Noticias, Sentimiento, Flujo de Órdenes y Anticipación en BTC

> Documento en construcción — escritura incremental. Cada sección se añade en cuanto se completa su investigación.
>
> Fecha de la investigación: septiembre 2026.
> Objetivo: responder con rigor a "¿cómo podemos anticiparnos a lo que va a hacer bitcoin?" cubriendo noticias, sentimiento social, flujo de órdenes/microestructura, flujos institucionales, eventos macro programados, y un balance honesto de qué NO funciona.
> Regla aplicada en todo el documento: contar cuántos **eventos independientes** hay detrás de cada afirmación estadística, porque con pocos eventos (como el Fear & Greed con 7-11 episodios extremos en 5 años) cualquier backtest es ruido con apariencia de señal.

## Índice

1. [Noticias: APIs y fuentes](#1-noticias-apis-y-fuentes)
2. [Puntuación de noticias con LLM y la trampa del lookahead](#2-puntuación-de-noticias-con-llm-y-la-trampa-del-lookahead)
3. [Sentimiento social (X/Twitter, Reddit, Google Trends, LunarCrush, Santiment)](#3-sentimiento-social)
4. [Flujo de órdenes y microestructura](#4-flujo-de-órdenes-y-microestructura)
5. [Flujos y posicionamiento (ETF, CME COT, stablecoins)](#5-flujos-y-posicionamiento)
6. [Eventos programados (FOMC, CPI, NFP, opciones, halving, regulación)](#6-eventos-programados)
7. [Lo que NO funciona (o no es viable para un particular)](#7-lo-que-no-funciona)
8. [Tabla resumen final](#8-tabla-resumen-final)

---

## 1. Noticias: APIs y fuentes

**El problema de fondo, dicho claro:** para poder *backtestear* una estrategia que reacciona a noticias, cada noticia necesita un timestamp con precisión de minuto (idealmente de segundo) que refleje el momento en que la noticia estuvo **públicamente disponible**, no la fecha en que se archivó o se scrapeó. Si el dato de noticias que ya tienes en `data/news_btc_1y.json` y `data/news_bull_2023_2024.json` solo trae fecha (día), es imposible saber si una vela de 15 minutos se movió *antes* o *después* de la noticia, y cualquier "backtest" con eso sería en realidad una fuga de información del futuro (ves el titular del día pero tu vela ya incluye la reacción). Esta sección evalúa, fuente por fuente, si resuelve ese problema.

### 1.1 CryptoPanic

- **Qué da:** agregador de noticias/titulares cripto con voto de la comunidad (bullish/bearish) y metadatos de "importancia". Es la fuente más citada en proyectos hobby de trading-bot.
- **API oficial:** [cryptopanic.com/developers/api](https://cryptopanic.com/developers/api/about) — devuelve el feed *actual* paginado por cursor (`next`). **No expone filtro por rango de fechas ni parámetro de timestamp para pedir histórico** en la API pública estándar. Es decir, sirve para *ir capturando en vivo* hacia adelante, no para reconstruir el pasado.
- **Histórico ya empaquetado:** existen datasets de terceros como [soheilrahsaz/cryptoNewsDataset](https://github.com/soheilrahsaz/cryptoNewsDataset) (248k noticias de CryptoPanic, CSV/MySQL) y otro con 662.047 artículos desde septiembre de 2017 enriquecidos con entidades, sentimiento y el precio BTC/ETH y el Fear & Greed *en el momento de captura*. Esto es relevante: si el timestamp es "momento de captura por el scraper de un tercero" y no "momento de publicación real", puede llevar minutos u horas de retraso — hay que auditar cada dataset antes de confiar en él para backtesting de 15m.
- **Veredicto sobre timestamp al minuto:** dudoso para la API en vivo (no hay endpoint histórico), y **hay que verificar caso por caso** en los dumps de terceros si el campo de fecha es el de publicación original o el de scraping.
- Fuentes: [CryptoPanic API docs](https://cryptopanic.com/developers/api/about), [dataset 248k noticias](https://github.com/soheilrahsaz/cryptoNewsDataset), [GitHub cryptocurrency.cv](https://github.com/nirholas/cryptocurrency.cv).

### 1.2 GDELT (Global Database of Events, Language and Tone)

- **Qué da:** proyecto académico que monitoriza medios de todo el mundo y extrae eventos, tono y entidades. Es gratuito y masivo.
- **Granularidad temporal:** GDELT 2.0 publica volcados **cada 15 minutos** desde febrero de 2015 — esto es, en teoría, la fuente con el timestamp más fino y más fiable de todas las de esta lista, porque la cadencia de publicación del propio dataset es de 15 minutos.
- **Cripto específico:** hay datasets curados como *CryptoGDelt2022* (243.000 eventos cripto entre marzo 2021 y abril 2022) y proyectos de investigación como *CrypTone* que predicen fluctuaciones de BTC con datos de GDELT.
- **Matiz importante:** aunque el pipeline es de 15 minutos, la mayoría de estudios que usan GDELT para cripto (incluido el de predicción de precio) **agregan a nivel diario** el tono promedio, perdiendo la granularidad fina que sí existe en el dato crudo. Si se quiere explotar la resolución de 15 minutos hay que trabajar con el dato crudo (`SQLDATE`/campo de fecha-hora del evento), no con los agregados diarios que usan casi todos los papers.
- **Veredicto:** es probablemente la mejor opción *gratuita* para timestamp fino, pero requiere trabajo de ingeniería propio (nadie te lo da ya filtrado y agregado a 15m para BTC).
- Fuentes: [GDELT project](https://www.gdeltproject.org/), [Cryptocurrency Curated News Event Database From GDELT (ResearchGate)](https://www.researchgate.net/publication/364581962_Cryptocurrency_Curated_News_Event_Database_From_GDELT), [CrypTone AIM](https://asite.aim.edu/data_science/cryptone-predicting-bitcoin-currency-fluctuationsusing-gdelt-news-data/).

### 1.3 NewsAPI.org

- **Qué da:** agregador generalista (150.000+ fuentes, no especializado en cripto) con búsqueda por keyword.
- **Precio:** el plan de pago arranca en 449 $/mes; el plan "Corporate" son 1.299,99 $/mes con 1.000.000 créditos/mes y 5 años de histórico. El plan gratuito está restringido a "development/testing" (CORS solo desde localhost) — **no se puede usar en producción ni para research serio sin pagar**.
- **Timestamp:** de fecha de publicación indicado por la fuente original, sin garantía adicional de precisión al minuto verificada de forma independiente.
- **Veredicto:** caro para lo que aporta específicamente en cripto (es generalista, no worth it frente a alternativas cripto-nativas).
- Fuente: [NewsAPI.org](https://newsapi.org/), [comparativa de precios](https://thunderbit.com/blog/best-news-apis-compared).

### 1.4 Finnhub

- **Qué da:** API financiera con endpoint de "Market News" (incluye cripto) y endpoints de cripto propios (velas, símbolos).
- **Timestamp:** el campo `datetime` del endpoint de noticias se devuelve en **UNIX timestamp** (segundos) — es decir, sí tiene precisión fina en el formato. La pregunta abierta (no confirmada en la documentación pública) es la latencia real entre publicación y disponibilidad en el feed de Finnhub, que no se detalla.
- **Veredicto:** de las APIs generalistas, es de las más prometedoras en cuanto a formato de timestamp; falta validar en la práctica si ese timestamp reflzeja bien el momento real de publicación para fuentes cripto.
- Fuente: [Finnhub Market News API](https://finnhub.io/docs/api/market-news).

### 1.5 Marketaux

- **Qué da:** noticias financieras globales con NLP de sentimiento por entidad (acciones, forex y también cripto), 5.000+ fuentes, 200.000+ entidades.
- **Precio:** capa gratuita generosa (100 peticiones/día), planes de pago razonables (no se detalla cifra exacta en la documentación pública encontrada).
- **Sentimiento:** puntuación de -1 a 1 por entidad y por artículo.
- **Veredicto:** buena relación calidad/precio para prototipar, pero cripto es un añadido secundario a su cobertura de equities — cobertura de BTC específicamente no está garantizada en profundidad.
- Fuente: [marketaux.com](https://www.marketaux.com/), [documentación](https://www.marketaux.com/documentation).

### 1.6 Alpaca News API (con datos de Benzinga)

- **Qué da:** Alpaca (broker/bróker API) redistribuye noticias de **Benzinga** para acciones y cripto en un único endpoint.
- **Histórico:** disponible desde 2015, con foco en backtesting: la propia documentación dice explícitamente que "los traders algorítmicos de Alpaca tienen acceso a datos históricos de noticias para backtesting y análisis de sentimiento" — es de las pocas fuentes que **se posiciona explícitamente para backtesting**, no solo para consumo en vivo.
- **Volumen:** ~130+ artículos/día de media.
- **Veredicto:** de las opciones investigadas, es la que mejor encaja con el requisito de "timestamp fiable para backtest", precisamente porque Benzinga es una wire service profesional (como Reuters/Bloomberg pero para retail) cuyo negocio depende de la latencia y exactitud del timestamp. Merece una prueba piloto real: descargar un mes de histórico BTC y contrastar manualmente 20-30 timestamps contra el momento real de publicación (archive.org / redes sociales) antes de confiar en ello para todo el backtest.
- Fuentes: [Alpaca Historical News Data docs](https://docs.alpaca.markets/us/docs/historical-news-data), [anuncio Alpaca+Benzinga](https://alpaca.markets/blog/alpaca-partners-with-benzinga-to-deliver-real-time-embedded-financial-news/).

### 1.7 LunarCrush

- **Qué da:** métricas sociales (menciones, engagement, "Galaxy Score") agregadas de X, Reddit, YouTube, TikTok para 4.000+ criptoactivos, más un indicador propio de sentimiento por ML.
- **Precio:** capa "Hobby" gratuita limitada a endpoints de mercado; los endpoints sociales/sentimiento/AI están detrás de plan de pago (cifra exacta no confirmada, ver [lunarcrush.com/pricing](https://lunarcrush.com/pricing/)).
- **Veredicto:** más útil para *sentimiento social agregado* (sección 3) que como fuente de noticias individuales con timestamp. El dato es una serie temporal (probablemente horaria), no un feed de eventos discretos con hora exacta de publicación de cada noticia.
- Fuente: [LunarCrush API](https://lunarcrush.com/products/lunarcrush-api).

### 1.8 The Tie

- **Qué da:** proveedor institucional (hedge funds, market makers, OTC desks son sus clientes declarados) de datos de sentimiento social "point-in-time" desde 2017, con filtrado de manipulación/bots mediante tecnología patentada.
- **Punto fuerte declarado:** *point-in-time, out-of-sample* — es decir, se venden explícitamente como aptos para backtesting riguroso sin lookahead, algo que casi ninguna otra fuente afirma de forma tan directa.
- **Precio:** no público, orientado a cliente institucional (no hay tier self-service barato visible).
- **Veredicto:** probablemente la mejor calidad de la lista para sentimiento social point-in-time, pero fuera de presupuesto para un trader particular salvo que tengan un plan de entrada más económico no anunciado.
- Fuente: [The Tie Sentiment API](https://www.thetie.io/solutions/sentiment-api/).

### 1.9 Kaiko

- **Qué da:** no es una fuente de noticias sino de **datos de mercado crudos**: trades tick-a-tick, snapshots de order book (L1/L2), tasas de referencia. Se incluye aquí porque es la referencia institucional de "verdad fiable" en microestructura (ver sección 4).
- **Precio confirmado:** niveles de servicio entre **1.000 $/mes** (agregados L1) y **2.500 $/mes** (tick-level L2) — claramente fuera del alcance de un trader particular para uso continuo, aunque puede valer la pena para una compra puntual de un dataset histórico acotado si el análisis de microestructura lo justifica.
- **Histórico:** snapshots de order book desde 2015 (según exchange), al menos 1 snapshot/minuto.
- Fuente: [Kaiko L1/L2 Data](https://www.kaiko.com/products/l1-l2-data).

### 1.10 RSS de CoinDesk / Cointelegraph

- **Qué da:** feeds RSS estándar, gratuitos, de los dos medios cripto más grandes.
- **Timestamp:** el RSS estándar incluye `pubDate`, pero **no se encontró documentación técnica específica** sobre la exactitud de ese campo frente al momento real de publicación (podría haber redondeos, corrección de artículos que actualiza la fecha, etc.). Es la opción más barata (gratis) pero la que menos garantías da sobre precisión de minuto sin validación manual propia.
- **Recomendación práctica:** si se usa RSS, hay que registrar tú mismo el timestamp de *ingesta* (cuándo tu propio scraper vio la entrada por primera vez) además del `pubDate` declarado, y usar el máximo de los dos como cota conservadora de "cuándo pudo actuar un bot".
- Fuentes: [Cointelegraph RSS feeds](https://newsloth.com/popular-rss-feeds/cointelegraph-rss-feeds), [CoinDesk RSS feeds](https://newsloth.com/popular-rss-feeds/coindesk-rss-feeds).

### 1.11 Tabla comparativa rápida — Sección 1

| Fuente | Timestamp fiable al minuto | Histórico para backtest | Coste | Nota |
|---|---|---|---|---|
| CryptoPanic (API oficial) | No confirmado (sin endpoint histórico) | No (solo feed en vivo) | Gratis/bajo | Usar solo dumps de terceros auditados |
| GDELT | Sí (pipeline de 15 min), pero requiere trabajo propio | Sí, desde 2015 | Gratis | Mejor opción gratuita si se procesa el dato crudo |
| NewsAPI.org | No verificado | Sí (plan caro) | 449-1.300 $/mes | Generalista, cripto no es el foco |
| Finnhub | Formato sí (UNIX ts), latencia no confirmada | Sí | Freemium/bajo | Validar en piloto |
| Marketaux | No verificado | Limitado en tier gratis | Gratis/bajo | Cripto secundario |
| Alpaca (Benzinga) | Probablemente sí (wire service profesional) | Sí, desde 2015 | Gratis con cuenta Alpaca | **Candidato principal a validar** |
| LunarCrush | Es serie agregada, no evento discreto | Sí | Freemium/medio | Mejor para sentimiento social (sección 3) |
| The Tie | Sí, point-in-time declarado | Sí, desde 2017 | Alto (institucional) | Mejor calidad, precio prohibitivo |
| Kaiko | N/A (no es noticias) | Sí, desde 2015 | 1.000-2.500 $/mes | Para microestructura, no noticias |
| RSS CoinDesk/Cointelegraph | No garantizado sin validación propia | Depende de si archivas tú mismo | Gratis | Registrar timestamp de ingesta propio |

---

## 2. Puntuación de noticias con LLM y la trampa del lookahead

### 2.1 Cómo se hace en 2025-2026

El enfoque estándar (consolidado desde 2023) es: dar al LLM un titular o texto de noticia + el nombre del activo, y pedirle que lo clasifique como bueno/malo/irrelevante para el precio, produciendo una puntuación numérica (p. ej. de -1 a +1). Esa puntuación se usa como *feature* de entrada a la estrategia, sola o combinada con indicadores técnicos.

El paper fundacional de este enfoque es **Lopez-Lira y Tang (2023), "Can ChatGPT Forecast Stock Price Movements? Return Predictability and Large Language Models"** ([arXiv:2304.07619](https://arxiv.org/abs/2304.07619), también en [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4412788)):

- Metodología: pedir a ChatGPT que indique si un titular es bueno/malo/irrelevante para la acción, calcular una puntuación numérica y correlacionarla con el retorno diario posterior.
- Resultado con **titulares posteriores al corte de conocimiento del modelo** (para eliminar memorización): GPT-4 acierta la dirección de la reacción inicial del mercado en ~90% de los casos (día-cartera, no es una cifra de "un solo titular"), y su puntuación predice también el *drift* de varios días siguientes, sobre todo en small caps y noticias negativas.
- Estrategia simulada: con 10 pb de coste por operación, retorno acumulado del 350% en el periodo de muestra; con 25 pb, cae a 50% — **muy sensible al coste de transacción asumido**, lo cual es una señal de alerta típica de estrategias que "solo funcionan en el backtest".
- Dato clave para nuestro tema: **modelos más simples (GPT-1, GPT-2, BERT) no logran predecir retornos** — la capacidad parece "emergente" en modelos grandes, lo que sugiere que el LLM está haciendo algo más que sentiment analysis léxico clásico (o que está aprovechando conocimiento de mundo/memorización, ver 2.2).
- Los propios autores documentan que el retorno de la estrategia **decae según se adopta más IA en el mercado** — consistente con que, si funciona, deja de funcionar en cuanto suficiente gente lo usa (esto aplica igual o peor a cripto, mercado más pequeño y con más bots).

### 2.2 La trampa del lookahead del modelo (esto es el núcleo del riesgo)

El problema que plantea el usuario es real y tiene nombre en la literatura reciente: un LLM entrenado con datos de internet hasta cierta fecha de corte **ya "sabe" qué pasó después** de una noticia si esa noticia (o su desenlace) apareció en su corpus de entrenamiento. Si le pides al LLM en 2026 que puntúe una noticia de BTC de 2021, no está haciendo sentiment analysis puro: puede estar (parcialmente) recordando cómo terminó la historia.

Dos papers concretos abordan esto de frente:

**(a) Assessing Look-Ahead Bias in Stock Return Predictions Generated By GPT Sentiment Analysis** ([arXiv:2309.17322](https://arxiv.org/pdf/2309.17322), [ar5iv](https://ar5iv.labs.arxiv.org/html/2309.17322)):
- Documenta dos mecanismos de sesgo distintos: (1) **look-ahead bias puro** — el LLM tiene conocimiento específico de qué retorno siguió a una noticia porque ese hecho concreto estaba en su entrenamiento; (2) **efecto distracción** — el conocimiento general que el LLM tiene sobre una empresa/activo (reputación, narrativa dominante) contamina la puntuación de sentimiento de una noticia puntual, aunque no haya memorizado el desenlace exacto.
- Mitigación propuesta: **anonimización de entidades** — sustituir el nombre del activo/empresa por un identificador genérico ("Empresa A", "Activo X") antes de pasar el texto al LLM, forzándolo a evaluar el sentimiento del texto en sí y no su conocimiento de mundo sobre esa entidad específica.

**(b) Detecting Lookahead Bias in LLM Forecasts** (Gao, Jiang, Yan; [arXiv:2512.23847](https://arxiv.org/html/2512.23847v2), sept-dic 2026, el más reciente y el más riguroso de los dos):
- Introduce la métrica **Lookahead Propensity (LAP)**: se le pregunta al LLM únicamente el nombre del activo y la fecha objetivo, **sin ningún titular ni contexto**, y se mide la probabilidad que asigna a "sube" vs "baja" vs "no sé". Si el LLM da una respuesta no trivial sin ninguna información contemporánea real, esa respuesta solo puede venir de haber memorizado el resultado durante el entrenamiento.
- Hallazgo cuantitativo: la señal de un LLM basada en titulares predice el retorno del día siguiente (+0,21%), pero esa capacidad predictiva **se amplifica un 32% adicional** en los casos donde LAP es alto (es decir, donde el modelo "ya sabía" el desenlace). **Tras la fecha de corte de entrenamiento del modelo (dic-2023), esa amplificación desaparece por completo** — prueba directa de que parte de la "capacidad predictiva" no es análisis genuino sino memorización.
- Conclusión incómoda para quien quiera mitigar esto con trucos simples: **el enmascaramiento de entidades no elimina el problema** cuando el modelo tiene memorización fuerte, porque el modelo puede reconstruir de qué activo/evento se trata por el contexto (fechas, cifras, redacción) aunque se le oculte el nombre literal.

### 2.3 Qué significa esto para un backtest de BTC con LLM

1. **Cualquier backtest que puntúe con un LLM noticias anteriores a la fecha de corte de entrenamiento de ese modelo está contaminado en un grado desconocido.** No se puede simplemente confiar en el resultado del backtest como si fuera "out of sample".
2. La única forma limpia de probar esto es: (a) usar solo noticias **posteriores** a la fecha de corte del modelo (paper Lopez-Lira lo hizo así deliberadamente), lo cual limita mucho la ventana de backtest disponible, o (b) aplicar el test LAP para cuantificar cuánta señal es memorización y descontarla.
3. Para BTC esto es más grave que para acciones: el precio histórico de BTC y los grandes titulares ("BTC cae por colapso de FTX", "SEC aprueba ETF spot", "China prohíbe minería") son *extremadamente* públicos y están machacados en el corpus de entrenamiento de cualquier LLM moderno — mucho más "memorizable" que el movimiento de una acción de mid-cap.
4. Para un proyecto como el tuyo, con recursos de particular, la recomendación práctica es: **usar el LLM únicamente para puntuar noticias en tiempo real, hacia adelante, no para "backtestear" contra noticias históricas ya conocidas por el modelo.** Cualquier validación histórica con LLM debe tratarse como una estimación optimista del límite superior, nunca como una cifra de retorno esperado real.

Fuentes: [Lopez-Lira & Tang, arXiv:2304.07619](https://arxiv.org/abs/2304.07619), [Assessing Look-Ahead Bias, arXiv:2309.17322](https://arxiv.org/pdf/2309.17322), [Detecting Lookahead Bias in LLM Forecasts, arXiv:2512.23847](https://arxiv.org/html/2512.23847v2).

---

## 3. Sentimiento social (X/Twitter, Reddit, Google Trends, LunarCrush, Santiment, StockTwits)

### 3.1 Twitter/X

- La evidencia más citada: el sentimiento de Twitter (con un léxico específico para cripto, no un analizador genérico) tiene poder predictivo sobre los retornos de **BTC, Bitcoin Cash y Litecoin**, actuando como **indicador adelantado robusto a un horizonte de una semana a un mes**, periodo en el que además se observan cambios notables en el volumen de trading.
- Esto es importante: el horizonte útil (según esta evidencia) es de **días a semanas**, no de minutos u horas — no sirve directamente para una señal de entrada de scalping o de 15 minutos sin adaptación.
- Otro artículo académico ("On the predictive power of tweet sentiments and attention on bitcoin", ScienceDirect) refuerza la idea de que **atención** (volumen de menciones) además de sentimiento (polaridad) aporta señal.
- **Número de eventos independientes:** aquí el problema no es "pocos eventos extremos" como con Fear & Greed, sino series continuas — el riesgo no es tamaño de muestra sino *overfitting* al periodo estudiado (2017-2020 en varios de estos papers, un régimen de mercado muy distinto al actual con mucho más volumen institucional).
- Fuente: [The predictive power of public Twitter sentiment for forecasting cryptocurrency prices (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S104244312030072X), [On the predictive power of tweet sentiments and attention on bitcoin](https://www.sciencedirect.com/science/article/abs/pii/S1059056022000375).

### 3.2 Reddit

- La evidencia aquí es **contradictoria entre estudios**, lo cual en sí mismo es una señal de alerta:
  - Un estudio (tesis CEU, Zhumagaziyev) **no encontró evidencia** de que el sentimiento de Reddit ni su variación prediga los retornos de Bitcoin, contradiciendo la creencia popular de que el sentimiento social predice cripto.
  - Otro estudio sí encontró relaciones significativas entre sentimiento de Reddit y precio/retornos/volatilidad/volumen de Bitcoin, tanto a corto como a largo plazo.
- **Lectura honesta:** cuando dos estudios académicos sobre la misma plataforma llegan a conclusiones opuestas, lo más probable es que el efecto (si existe) sea pequeño, frágil a la elección de ventana temporal/metodología, y no un patrón robusto explotable de forma directa.
- Fuente: [Can Reddit sentiment predict Bitcoin returns? (CEU thesis)](https://www.etd.ceu.edu/2023/zhumagaziyev_sh.pdf), [Reddit as a prediction tool for crypto-assets (ProQuest)](https://www.proquest.com/docview/2653591185).

### 3.3 Google Trends

- Evidencia más sólida para **volatilidad** que para dirección de precio: el modelo más simple, usando solo el volumen de búsqueda de "Bitcoin", da el pronóstico de volatilidad más preciso, superando incluso enfoques basados en variables de mercado tradicionales.
- Para dirección de precio la evidencia es más débil e indirecta: estudios de causalidad de Granger encuentran que el interés de búsqueda en "blockchain" precede movimientos de precio en activos relacionados (PayPal, Robinhood, SoFi), consistente con la hipótesis de que la atención del inversor (medida por búsquedas) precede a la acción de mercado — pero esto es sobre acciones relacionadas con cripto, no sobre BTC directamente en el estudio citado.
- **Ventaja práctica:** Google Trends es gratis, tiene histórico largo (desde 2004) y no tiene problema de timestamp al minuto porque se usa a nivel diario/semanal por diseño — pero por eso mismo tampoco sirve para señales de 15m-4h.
- Fuente: [Google Trends as a Predictor of FinTech Asset Prices (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5340057), [Can Google Trends Sentiment Be Useful for Cryptocurrency Returns? (QuantPedia)](https://quantpedia.com/can-google-trends-sentiment-be-useful-as-a-predictor-for-cryptocurrency-returns/).

### 3.4 LunarCrush y Santiment (agregadores de sentimiento social multiplataforma)

- Ambas son plataformas comerciales que combinan menciones + sentimiento (clasificado por ML) + engagement de X, Reddit, YouTube, TikTok, foros cripto, en un único índice (p. ej. "Galaxy Score" de LunarCrush).
- Santiment además cruza esto con **datos on-chain** (edad media de las monedas, actividad de red), lo cual es un plus porque combina dos fuentes de señal distintas.
- **Limitación de acceso:** en ambos casos, el free tier tiene retraso de 30 días en las métricas restringidas (Santiment) o solo cubre endpoints de mercado sin sentimiento (LunarCrush Hobby) — para tener el dato *en tiempo real* y con histórico completo hay que pagar el tier alto.
- **Sin evidencia académica independiente fuerte encontrada** de que estos índices propietarios concretos (Galaxy Score, Santiment sentiment) predigan retornos futuros de forma robusta fuera de muestra — la mayoría del material disponible es marketing propio de las plataformas, no papers peer-reviewed con backtests transparentes.
- Fuentes: [LunarCrush API](https://lunarcrush.com/products/lunarcrush-api), [Santiment academy metrics](https://academy.santiment.net/metrics/), [Santiment pricing](https://app.santiment.net/pricing).

### 3.5 StockTwits

- No se encontró evidencia académica específica y reciente sobre StockTwits aplicada a cripto en esta investigación (limitación reconocida: búsqueda no concluyente por agotamiento del presupuesto de búsquedas web de la sesión). Lo que sí es consistente con la literatura general de finance-sentiment: StockTwits tiene un sesgo estructural hacia el optimismo/bullish (la base de usuarios se autoselecciona hacia gente que ya tiene posición larga), lo que históricamente ha exigido corregir el sentimiento crudo antes de usarlo como señal en equities. Cabría esperar el mismo sesgo en los canales cripto de StockTwits, pero **esto es una extrapolación razonada, no un hallazgo verificado en esta investigación** — habría que validarlo antes de construir nada sobre ello.

### 3.6 Balance de la sección 3

- El sentimiento social tiene la evidencia académica **más consistente en Twitter/X**, con horizonte de días-semanas, no de horas.
- Reddit es contradictorio entre estudios — tratar con escepticismo.
- Google Trends predice mejor **volatilidad** que dirección, y a nivel diario/semanal.
- Los agregadores comerciales (LunarCrush, Santiment, The Tie) prometen más que lo que la literatura académica independiente confirma; son herramientas razonables para *contexto* pero no hay evidencia sólida de edge explotable neto de costes.
- **Ningún estudio de los encontrados usa datos post-2023 con el régimen actual de mercado dominado por ETFs institucionales** — toda la evidencia de "predictibilidad" es de una era (2017-2021) en la que el mercado cripto tenía mucha menos participación institucional y algorítmica; es razonable esperar que cualquier edge de sentimiento social se haya erosionado desde entonces (ver sección 7, alpha decay).

---

## 4. Flujo de órdenes y microestructura

Antes de nada, dos conceptos que hay que tener claros porque el usuario los pidió explicados con ejemplos:

- **CVD (Cumulative Volume Delta / Delta Acumulado):** en cada operación ejecutada en un mercado, alguien "cruza el spread" — compra al precio de venta (ask) o vende al precio de compra (bid). Esa parte se llama el *agresor*. El "delta" de una vela es (volumen comprado por agresores) menos (volumen vendido por agresores) en esa vela. El CVD es la suma acumulada de ese delta a lo largo del tiempo. Ejemplo: si en una vela de 15 minutos hay 100 BTC comprados "a mercado" (agresivamente) y 60 BTC vendidos "a mercado", el delta de esa vela es +40. Si se acumula vela a vela, se obtiene una línea que sube cuando dominan los compradores agresivos y baja cuando dominan los vendedores agresivos — **independientemente de que el precio suba o baje**, lo cual es la clave de su utilidad: si el precio sube pero el CVD no acompaña (o incluso baja), se interpreta como una subida "sin convicción" (divergencia).
- **Footprint (huella de volumen):** en vez de una vela normal (que solo muestra apertura/máximo/mínimo/cierre), un footprint muestra, dentro de cada vela, cuánto volumen se negoció en cada nivel de precio y cuánto de ese volumen fue comprador vs. vendedor. Es como hacer zoom dentro de la vela para ver *dónde* y *por quién* se negoció el volumen.
- **Barrido de liquidez / stop hunt:** en los niveles de máximos y mínimos recientes se acumulan órdenes stop-loss (de quien ya tiene posición) y órdenes de entrada en ruptura (de quien espera que el nivel se rompa). Un "barrido" es cuando el precio perfora brevemente ese nivel — activando/ejecutando todas esas órdenes acumuladas ("liquidez") — y luego revierte con fuerza en la dirección contraria. La idea de "stop hunt" (caza de stops) implica que alguien lo hizo *a propósito* para aprovechar esa liquidez, algo que ningún gráfico puede probar con certeza; lo verificable es el patrón de precio (mecha que perfora y revierte), no la intención.

### 4.1 ¿Predice el desequilibrio del libro de órdenes (order book imbalance) el precio a corto plazo?

- Hay evidencia académica de que sí existe una relación medible: el desequilibrio entre el volumen disponible en el lado de compra vs. el de venta en los primeros niveles del libro **influye en el siguiente movimiento de precio**, y esto se replica de forma consistente entre distintos activos cripto (patrón "universal" documentado con datos de Binance Futures a frecuencia de 1 segundo entre 2022 y 2025).
- **Pero hay un matiz decisivo:** los propios papers de microestructura señalan que, aunque el efecto es estadísticamente detectable, **no suele ser lo bastante fuerte como para sustentar arbitraje estadístico neto de costes** — es decir, comprar y vender basándose en la predicción del desequilibrio del libro, una vez descontados spread y comisiones, no supera el coste de transacción en el caso general.
- Esto encaja con la intuición: el order book imbalance es una señal de horizonte de **segundos**, terreno de quienes tienen colocation y latencia de microsegundos (ver sección 7), no de un bot retail en la nube con latencia de cientos de milisegundos.
- Fuentes: [Explainable Patterns in Cryptocurrency Microstructure (arXiv 2602.00776)](https://arxiv.org/html/2602.00776v1), [Exploring Microstructural Dynamics in Crypto LOBs (arXiv 2506.05764)](https://arxiv.org/abs/2506.05764), [Price Impact of Order Book Imbalance in Cryptocurrency Markets (Towards Data Science)](https://towardsdatascience.com/price-impact-of-order-book-imbalance-in-cryptocurrency-markets-bf39695246f6/).

### 4.2 Mapas de liquidación (Coinglass, Hyblock)

- **Qué son:** estimaciones de en qué niveles de precio se liquidarían masivamente posiciones apalancadas abiertas en exchanges de futuros perpetuos, calculadas a partir del open interest agregado y supuestos de apalancamiento típico.
- **Dato crítico que hay que entender antes de confiar en ellos:** en exchanges centralizados (Binance, Bybit, OKX) **las posiciones individuales son privadas** — Coinglass y Hyblock no ven el libro real de posiciones, lo **reconstruyen/estiman** con modelos propios. Solo en exchanges 100% on-chain como Hyperliquid es el dato de posiciones/liquidaciones verdad verificable en la blockchain ("ground truth").
- Hyblock generalmente tiene menor latencia y (según su propio marketing) mayor precisión de modelo que Coinglass, pero para el grueso del volumen de BTC (que ocurre en CEX opacos) **ambos están estimando, no midiendo**.
- **Uso práctico razonable:** como contexto de "zonas donde es probable que haya barridos de liquidez", no como predicción exacta de nivel. Es coherente con la lógica de barrido de liquidez explicada arriba, pero no es una fuente de verdad dura.
- Fuentes: [CoinGlass Liquidation Heatmap](https://www.coinglass.com/pro/futures/LiquidationHeatMap), [comparativa accuracy Hyblock vs Coinglass](https://www.bitget.com/academy/crypto-liquidation-m).

### 4.3 Barridos de liquidez ("stop hunts") — cuidado con las cifras que circulan

- Hay mucho contenido de trading retail (estilo "Smart Money Concepts"/ICT) que afirma win rates de 65-75% en barridos "validados", subiendo a 80%+ combinados con otras confluencias. **Estas cifras provienen de "backtests" informales de la propia comunidad SMC/ICT, no de estudios académicos con metodología revisada por pares** — hay que tratarlas con el mismo escepticismo que cualquier afirmación de trading sin código fuente ni datos verificables públicamente. No se encontró en esta investigación ningún paper académico que cuantifique de forma independiente la tasa de éxito de barridos de liquidez en BTC.
- Lo que sí es razonable y consistente con la microestructura: BTC cotiza 24/7 con alto apalancamiento y muchos bots, lo que estructuralmente favorece que existan barridos frecuentes alrededor de máximos/mínimos evidentes, aperturas de sesión y resets de funding — pero "frecuente" no es lo mismo que "rentable después de costes y falsos positivos".

### 4.4 Trades agresivos, CVD y footprint: ¿qué datos hacen falta y a qué coste?

- **Dato mínimo necesario:** el histórico de **trades públicos** (cada operación ejecutada, con precio, volumen, lado agresor y timestamp). Esto es más barato y accesible que el order book L2 completo.
- **Freqtrade ya lo soporta de forma nativa** ("advanced-orderflow", en beta): activando `use_public_trades` descarga los trades públicos del exchange y construye automáticamente columnas de footprint, imbalances, delta, min/max delta y "stacked imbalances" directamente en el dataframe de la estrategia. Esto es relevante para el proyecto: **no hace falta comprar datos institucionales caros para hacer CVD/footprint/imbalance a nivel de vela de 15m-4h** — con los trades públicos del propio exchange (gratis, vía su API/websocket histórico) alcanza.
- **Limitación documentada de Freqtrade:** los datos de trades son pesados y ralentizan bastante el arranque inicial (tiene que descargar y procesar trade a trade en vez de velas agregadas), y consume bastante más memoria. Es viable para 15m-4h en un solo par o unos pocos pares, pero escalar a muchos pares/timeframes exige más recursos.
- **Order book L2 (profundidad completa, no solo trades):** esto sí es caro. Kaiko cobra 1.000-2.500 $/mes por snapshots de profundidad L1/L2 con histórico desde 2015. Es el dato que hace falta para replicar order book imbalance "de verdad" (sección 4.1) con calidad institucional, y su coste **no está justificado para un particular** salvo compra puntual acotada para validar una hipótesis concreta antes de decidir si vale la pena.
- **Conclusión práctica para el proyecto:** CVD/footprint/imbalance con trades públicos vía Freqtrade **es viable y gratis** para señales de 15m-4h. Order book L2 institucional para señales de segundos **es la liga de los HFT con colocation**, no tiene sentido para este proyecto.
- Fuentes: [Freqtrade Orderflow docs](https://www.freqtrade.io/en/stable/advanced-orderflow/), [Freqtrade GitHub advanced-orderflow.md](https://github.com/freqtrade/freqtrade/blob/develop/docs%2Fadvanced-orderflow.md), [Kaiko L1/L2 Data pricing](https://www.kaiko.com/products/l1-l2-data).

### 4.5 CVD en la práctica: qué se puede leer y qué no

- El material de la industria (no académico, pero técnicamente coherente) coincide en que lo que aporta valor de CVD es la **pendiente**, la **divergencia contra el precio**, y el **comportamiento en niveles clave** — no un valor absoluto de CVD por sí solo.
- Matiz técnico importante: el CVD es **por venue** (por exchange) — el CVD de Binance no es el CVD "del mercado BTC global", porque cada exchange tiene su propio flujo de agresores. Para una lectura agregada real haría falta sumar trades de varios exchanges, lo cual vuelve a depender de si el proyecto opera en un solo exchange (más simple, más barato) o quiere una vista de mercado global (más caro, más complejo).

---

## 5. Flujos y posicionamiento (ETF spot, CME COT, stablecoins)

### 5.1 Flujos diarios de ETF spot de BTC (Farside Investors)

- **Qué da Farside:** agregación diaria y gratuita de los flujos netos (entradas/salidas en millones de USD) de los ETF spot de BTC en EE.UU. (IBIT, FBTC, GBTC, ARKB, etc.), con histórico completo desde el lanzamiento en enero de 2024. Se actualiza por la noche/madrugada hora US.
- **Evidencia de impacto en precio:** en un análisis de las 170 sesiones de 2026, un día con 100 millones $ de creación neta en los ETF spot mueve el precio de BTC aproximadamente **53,7 puntos básicos (0,537%)**, y ese impacto **no revierte** (no es un efecto temporal que se deshace al día siguiente, sino un desplazamiento persistente de precio).
- **Esto es relevante para el proyecto porque:**
  1. Es un dato **diario**, público, gratuito y con timestamp de publicación claro (no tiene el problema de precisión al minuto que sí tienen las noticias).
  2. Al ser flujo neto real de dinero institucional (no sentimiento ni opinión), es conceptualmente más cercano a "lo que la gente con más capital está haciendo" que cualquier métrica de sentimiento social.
  3. La limitación es la **frecuencia**: solo hay un dato por día hábil bursátil US, así que como mucho sirve para sesgar la dirección del día siguiente o para un filtro de régimen (p. ej. "solo operar largos mientras el flujo ETF acumulado de 5 días sea positivo"), no para timing intradía de 15m-4h.
- Fuentes: [Farside Investors — Bitcoin ETF Flow](https://farside.co.uk/btc/), [Farside — All Data](https://farside.co.uk/bitcoin-etf-flow-all-data/), análisis de impacto de 53,7 pb citado vía búsqueda (fuente de mercado, verificar la cifra exacta directamente en farside.co.uk antes de construir una estrategia sobre ella).

### 5.2 CME Commitment of Traders (COT) para futuros de Bitcoin

- **Qué da:** la CFTC publica cada viernes (con datos del martes anterior, es decir, con **3 días de retraso**) el desglose de posiciones abiertas en futuros de BTC y ETH del CME por categoría de trader (comerciales, no comerciales/especuladores grandes, pequeños especuladores).
- **Cobertura parcial importante:** el CME representa la parte **institucional regulada** del mercado de futuros de BTC — la mayoría del volumen de futuros/perpetuos de BTC ocurre en exchanges offshore (Binance, Bybit, OKX, etc.) que no reportan al COT. Es el barómetro de posicionamiento institucional más cercano que existe, pero es una fracción del mercado total.
- **Limitación de timing:** con 3 días de retraso estructural, el COT **no sirve para timing de entrada/salida** — es dato de contexto para identificar sesgos de posicionamiento a medio plazo (¿está el "dinero grande" muy largo o muy corto, cerca de un extremo histórico?), no una señal accionable de corto plazo. La propia literatura de trading lo describe como "contexto de research, no un pronóstico".
- Fuentes: [The Block — CME Bitcoin COT data](https://www.theblock.co/data/crypto-markets/cme-cots), [CFTC Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm).

### 5.3 Saldos de stablecoins (USDT, USDC) como "pólvora seca"

- **La hipótesis:** un aumento en el suministro total de stablecoins representa dólares que han entrado al ecosistema cripto y están "esperando" para comprar — de ahí la idea de que el crecimiento de stablecoins es un indicador adelantado de rallies, y su contracción precede caídas.
- **Matiz importante y reciente (2026):** análisis recientes cuestionan que esta relación siga siendo fiable, porque una parte creciente del crecimiento de stablecoins ahora viene de **pagos, remesas y tesorería corporativa** (usos que no tienen nada que ver con comprar BTC/ETH), no solo de "dinero esperando para entrar al trading". Es decir, la señal se ha diluido con el tiempo según va cambiando el caso de uso dominante de las stablecoins.
- **Concentración:** USDT (~58-60%) y USDC (~23%) concentran ~82% del mercado de stablecoins, y en 2026 se observa que USDC ha superado a USDT en volumen de transacción *ajustado* (excluyendo bots/lavado de volumen) por primera vez desde 2019 — un cambio estructural que complica usar "supply total de stablecoins" como proxy simple sin diferenciar por emisor y por uso.
- **Veredicto:** señal de contexto de régimen (macro, semanas/meses), interesante para un filtro de fondo, pero **cada vez menos limpia** como predictor directo, y no aporta nada a un horizonte de 15m-4h.
- Fuentes: [Stablecoin Supply: A Leading Market Signal? (Bitsgap, 2026)](https://bitsgap.com/blog/stablecoin-supply-a-leading-market-signal), [Adjusted Stablecoin Volume Shows USDC Outpacing USDT in 2026 (Bitcoin.com News)](https://news.bitcoin.com/adjusted-stablecoin-volume-shows-usdc-outpacing-usdt-in-2026-mizuho-raises-circle-price-target/).

### 5.4 Netflow de ballenas a exchanges (on-chain)

- **Qué es:** volumen de BTC que "ballenas" (direcciones con 1.000+ BTC agregados) depositan menos lo que retiran de los exchanges. Un netflow positivo (depositan más de lo que retiran) suele interpretarse como señal bajista (se preparan para vender), y negativo como alcista (retiran a cold storage, señal de holding).
- **Evidencia encontrada:** es más sólida para **predecir picos de volatilidad** que dirección de precio — estudios que combinan datos on-chain (CryptoQuant) con alertas de Whale Alert usando modelos de deep learning muestran mejoras al pronosticar picos de volatilidad extrema, no necesariamente la dirección del movimiento.
- **Viabilidad:** los datos on-chain de exchanges (Glassnode, CryptoQuant) tienen niveles gratuitos limitados y de pago para lo avanzado; Whale Alert publica en tiempo real vía Twitter/API. Es más accesible que el order book L2 institucional, y el timestamp on-chain (altura de bloque) es exacto por diseño — una ventaja real sobre las fuentes de noticias/sentimiento.
- Fuente: [Forecasting Bitcoin volatility spikes from whale transactions and CryptoQuant data (arXiv 2211.08281)](https://ar5iv.labs.arxiv.org/html/2211.08281).

---

## 6. Eventos programados (FOMC, CPI, NFP, vencimientos de opciones, halving, regulación)

**Aviso general para toda esta sección:** los eventos macro programados (FOMC, halvings) ocurren pocas veces al año o cada 4 años — son exactamente el tipo de fenómeno de "pocos eventos independientes" que el usuario ya identificó como problema con el Fear & Greed. Hay que contar los eventos con la misma disciplina.

### 6.1 FOMC (reuniones de tipos de interés de la Fed)

- **Patrón de "pre-FOMC drift":** existe evidencia de que BTC sube ligeramente el día antes del anuncio (~+0,96% documentado en un estudio) y cae en el día del anuncio (~-1%) — un patrón de "comprar el rumor" seguido de "vender la noticia".
- **Cifra más citada en 2025-2026:** BTC cayó tras **8 de las últimas 9** reuniones FOMC (y en otra formulación, "7 de 8" en 2025), promediando una caída del 11% en la semana posterior, con mayo de 2025 como única excepción.
- **Conteo de eventos independientes — esto es crítico:** la Fed celebra **8 reuniones FOMC al año**. "8 de las últimas 9" son **9 eventos**. Esto es un tamaño de muestra minúsculo, del mismo orden que los 7-11 episodios de Fear & Greed extremo que el usuario ya descartó por insuficientes. Un patrón de "cae en 8 de 9" con n=9 tiene una probabilidad nada despreciable de ser puro azar (con una moneda justa, sacar 8 o más caras en 9 tiraday tiene ~2% de probabilidad, así que el patrón *podría* ser real, pero el margen de error con n=9 es enorme y una sola reunión distinta cambia la estadística radicalmente).
- **Mecanismo propuesto (razonable, pero no prueba causalidad):** las expectativas de tipos ya están descontadas antes de la reunión por el mercado de futuros de tipos, así que hay poco upside "nuevo" en el anuncio en sí, y domina la toma de beneficios de quien compró la expectativa.
- **Volatilidad, no dirección, es el patrón más robusto:** la volatilidad diaria de BTC en días de FOMC corre un 50-100% por encima de lo normal — esto sí es un patrón consistente y no depende de acertar la dirección, es relevante para dimensionar el riesgo/tamaño de posición en esos días aunque no se opere direccionalmente el evento.
- Fuentes: [Bitcoin Has Fallen After 8 Of The Last 9 FOMC Decisions (Stocktwits/TradingView)](https://www.tradingview.com/news/stocktwits:8a7282b7e094b:0-bitcoin-has-fallen-after-8-of-the-last-9-fomc-decisions-will-this-time-be-different-crypto-analysts-are-split/), [Scheduled FOMC statements and intraday macro event risk in cryptocurrency markets (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S1544612326006021), [Do FOMC and macroeconomic announcements affect Bitcoin prices? (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S154461231930159X).

### 6.2 CPI (inflación)

- Esta es la evidencia macro **más sólida en términos estadísticos** de las estudiadas en esta sección, porque el CPI se publica mensualmente desde hace décadas (muchas más observaciones que FOMC/halving) y hay estudios con **6 años de muestra** (2020-2026, ~72 publicaciones mensuales, muchas más que 9 o 4 eventos).
- **Hallazgo cuantificado:** en una ventana de 6 años, la sorpresa de CPI (diferencia entre dato real y consenso) explica ~25% de la varianza del retorno de BTC en la primera hora tras la publicación; una sorpresa al alza de 1 punto porcentual se ha asociado a una caída de ~5,5% en BTC. En una ventana móvil de las últimas 12 publicaciones, ese R² sube a ~80% — sugiriendo que la sensibilidad de BTC al CPI **ha aumentado recientemente**, superando incluso el pico de 2022-2023, aunque con menor magnitud por sorpresa y concentrado en la primera hora.
- **Esto es relevante para un horizonte de 15m-4h:** a diferencia de FOMC/halving, el efecto CPI se documenta específicamamente en la **primera hora** tras la publicación — es el evento macro programado con mejor encaje potencial con el timeframe del proyecto, y con un tamaño de muestra razonable (decenas de eventos, no un puñado).
- **Cautela:** "explica el 25-80% de la varianza en la primera hora" no es lo mismo que "es rentable operar automáticamente el CPI" — la velocidad de reacción del mercado a un dato macro programado y ampliamente seguido es muy alta, y competir en velocidad de ejecución en el segundo exacto de la publicación es, de nuevo, terreno de infraestructura profesional (ver sección 7).
- Fuentes: [Is Bitcoin showing greater sensitivity to US CPI releases again? (Block Scholes)](https://www.blockscholes.com/institutional-research/is-bitcoin-showing-greater-sensitivity-to-us-cpi-releases-again), [Bitcoin's Reaction to US FOMC and CPI Announcements (tesis KSE)](https://kse.ua/wp-content/uploads/2026/05/illia-nazaruk_268722_assignsubmission_file_nazaruk_final_thesis.pdf).

### 6.3 NFP (nóminas no agrícolas)

- No se encontró en esta investigación un estudio específico y cuantificado sobre la reacción de BTC al NFP comparable en rigor al del CPI (limitación reconocida por agotamiento del presupuesto de búsqueda web de la sesión). Por analogía con CPI y por ser también un dato macro de EE.UU. con seguimiento algorítmico intenso, es razonable esperar un patrón de volatilidad elevada en el minuto de publicación, pero **esto no está verificado en esta investigación** y no debería asumirse sin comprobación propia con datos históricos de precio minuto a minuto alrededor de cada publicación de NFP.

### 6.4 Vencimientos de opciones y "max pain"

- **La teoría popular:** los creadores de mercado que vendieron opciones tendrían incentivo a mover el precio hacia el nivel de "max pain" (donde el conjunto de compradores de opciones pierde más dinero) antes del vencimiento.
- **Evidencia reciente va en contra de la teoría como señal fiable:** vencimientos grandes recientes (15.000 millones $ en junio 2025, 13.300 millones $ en diciembre) **no** mostraron el efecto de "imán" esperado — en un caso BTC se quedó cotizando ~12% por encima del nivel de max pain tras el vencimiento, en vez de converger hacia él.
- **Conclusión de la propia cobertura especializada:** el max pain sirve como **descripción** de la estructura de opciones abiertas (dónde hay más interés abierto y en qué dirección), pero no como **objetivo de precio fiable** — el patrón que pareció funcionar en 2020-2021 probablemente reflejaba otras fuerzas de mercado coincidentes, no un mecanismo causal robusto de "pinning".
- Fuente: [Forget max pain. Bitcoin is well below the $72,000 magnet (CoinDesk)](https://www.coindesk.com/markets/2026/06/25/forget-max-pain-bitcoin-is-well-below-the-usd72-000-magnet-ahead-of-usd10-billion-options-expiry), [What Is Max Pain in Bitcoin Options? (Bitzo)](https://bitzo.com/2026/08/bitcoin-options-max-pain-expiry-mechanics).

### 6.5 Halving

- **El patrón más famoso y el más frágil estadísticamente de todos los de esta sección:** los 4 halvings de Bitcoin hasta ahora han sido seguidos de subidas de precio significativas en los 12-18 meses posteriores.
- **Conteo de eventos independientes: n=4.** Esto es explícitamente reconocido por comentaristas críticos como una muestra demasiado pequeña para constituir un patrón estadístico — con 4 observaciones no se puede establecer significancia estadística de nada, por espectacular que parezca el patrón visual.
- **Factores de confusión (confounders):** cada halving coincidió con catalizadores externos distintos y no relacionados con el halving en sí (adopción institucional en un ciclo, ETFs en otro, condiciones macro de tipos de interés distintas en cada uno) — correlación no implica causalidad, y la magnitud del retorno post-halving **ha ido decreciendo cada ciclo** (del ~9.300% tras el primero a rendimientos mucho menores en el cuarto), lo cual es consistente tanto con "el efecto se diluye al madurar el activo" como con "nunca fue el halving, era otra cosa cada vez".
- **Veredicto:** el halving es el ejemplo perfecto de un patrón que "se ve" en un gráfico pero que no resiste el escrutinio de tamaño de muestra — con n=4, ni siquiera el patrón más citado de todo el espacio cripto es estadísticamente defendible.
- Fuentes: análisis de sample size citados vía búsqueda de mercado (ver secciones de FractalCycles, Spark, y crypto.news en la búsqueda), consenso resumido en la respuesta de investigación.

### 6.6 Decisiones regulatorias (aprobaciones/rechazos SEC, prohibiciones, etc.)

- No se completó investigación específica dedicada a "sell the news" en aprobaciones regulatorias (ETF spot, etc.) por agotamiento del presupuesto de búsqueda de la sesión — limitación reconocida. Es un área que merece una investigación de seguimiento específica, dado que la aprobación del ETF spot de BTC en enero de 2024 es probablemente el evento regulatorio más estudiable de la historia reciente de BTC (con datos de precio y flujo de alta calidad disponibles vía Farside, sección 5.1) y un caso de manual de "vender la noticia" muy citado informalmente en medios (comprar el rumor de aprobación, vender al confirmarse).

### 6.7 Balance de la sección 6

| Evento | Eventos independientes disponibles | Patrón encontrado | Fiabilidad |
|---|---|---|---|
| FOMC | ~9 recientes citados (8/9 años totales desde 2015 ≈ 60+, pero el patrón "8 de 9" usa solo 9) | Sell the news, drift previo | Baja-media (n pequeño en la cifra más citada) |
| CPI | Decenas (mensual desde hace años) | Reacción fuerte en 1ª hora, R² alto | Media — la más sólida del grupo, pero ejecutar en el segundo exacto es difícil |
| NFP | No verificado en esta investigación | Desconocido | No evaluable aquí |
| Vencimiento opciones / max pain | Muchos vencimientos, pero el efecto no se sostiene | Sin patrón fiable reciente | Baja (evidencia reciente contradice la teoría) |
| Halving | **n=4** | Subida post-halving, pero decreciente y confundida | Muy baja (n insuficiente, reconocido por la propia comunidad) |
| Regulación (ETF approval, etc.) | No investigado a fondo aquí | "Sell the news" anecdótico | Pendiente de investigación dedicada |

---

## 7. Lo que NO funciona (o no es viable para un particular)

Lista honesta, con la razón concreta por la que cada enfoque falla o no es viable:

1. **Fear & Greed Index como señal aislada** (ya descartado por el usuario, se confirma aquí): con 7-11 episodios extremos independientes en 5 años, cualquier "backtest" que muestre una tasa de acierto alta es indistinguible de azar con esa muestra. Confirmado indirectamente por el hallazgo de alpha decay en estrategias de sentimiento extremo (ver punto 5).

2. **Order book imbalance como señal de trading directa (no solo contexto):** la literatura académica confirma que el efecto existe y es medible, pero **no es lo bastante fuerte para superar spread + comisiones** en el caso general — es una señal real pero de magnitud sub-económica para el particular. Terreno de HFT con infraestructura de colocation.

3. **Competir en velocidad en eventos macro programados (CPI, FOMC, NFP) o en noticias virales:** la literatura de "latency arms race" es clara — hay carreras de arbitraje de latencia que duran 5-10 microsegundos y requieren colocation dentro del datacenter del exchange, FPGAs y redes de fibra/microondas dedicadas, con presupuestos mensuales de 5-6 cifras. Un bot retail en una VPS normal no es "el rápido" en esa carrera, es "el lento cuyo precio desfasado es arbitrado por otros". Cualquier estrategia que dependa de reaccionar más rápido que el mercado a un dato público programado está, por definición, fuera del alcance de un particular.

4. **Max pain / vencimiento de opciones como objetivo de precio:** la evidencia de 2025-2026 muestra vencimientos multimillonarios en los que el precio ni se acercó al nivel de max pain — la teoría popular en redes sociales no se sostiene con los datos recientes.

5. **Estrategias de sentimiento social "descubiertas" y publicadas:** un estudio de validación out-of-sample de estrategias basadas en sentimiento extremo (miedo/codicia) mostró que el retorno cayó de +2,24% a +0,88% al pasar de la muestra de entrenamiento (2024) a la de validación (2025-26) — alpha decay documentado y cuantificado. El mecanismo es intuitivo: en cuanto un patrón de sentimiento se hace popular (blogs, Twitter, este mismo tipo de investigación), el capital que persigue ese patrón compite por la misma ventaja hasta que desaparece. Cualquier señal de sentimiento social "conocida" tiene una vida media decreciente.

6. **Reddit sentiment como señal aislada:** evidencia contradictoria entre estudios académicos serios sobre el mismo tema — cuando los propios académicos no se ponen de acuerdo, es una señal de que el efecto (si existe) es débil y sensible a la metodología, no un patrón robusto.

7. **Halving como señal de timing:** n=4 es insuficiente para cualquier inferencia estadística seria, reconocido incluso por comunidades que históricamente han defendido el patrón. Útil como narrativa de fondo de "oferta decreciente", inútil como timing.

8. **Puntuación de noticias históricas con LLM como si fuera "backtest limpio":** como se detalla en la sección 2, cualquier LLM moderno puntuando noticias de BTC anteriores a su fecha de corte de entrenamiento está, en un grado no cuantificado sin el test LAP, recordando el desenlace en vez de analizando genuinamente el texto. Un backtest así sistemáticamente sobreestima el rendimiento real esperado hacia adelante.

9. **CryptoPanic API oficial para reconstruir histórico con timestamp fino:** no expone endpoint de rango de fechas — estructuralmente no sirve para backtesting riguroso sin recurrir a dumps de terceros de fiabilidad variable.

10. **Cualquier dato "on-chain o de sentimiento" comprado a precio institucional (Kaiko L2, The Tie) para un proyecto de un particular:** el coste (1.000-2.500 $/mes Kaiko, precio no público pero claramente institucional en The Tie) no se puede justificar frente al tamaño del capital gestionado en un proyecto personal — son herramientas diseñadas y tarificadas para fondos, no para retail, por mucho que la calidad del dato sea superior.

11. **Stablecoin supply como señal simple y aislada:** la relación se ha diluido en 2025-2026 porque una parte creciente del crecimiento de stablecoins viene de pagos/remesas/tesorería corporativa, no de "pólvora seca" esperando para comprar cripto — usar esta métrica sin diferenciar por caso de uso es aplicar una regla de una era de mercado distinta a la actual.

---

## 8. Tabla resumen final

| Idea de anticipación | Dato necesario | ¿Backtesteable con histórico real? | Evidencia | Veredicto |
|---|---|---|---|---|
| Puntuar titulares con LLM en tiempo real (hacia adelante) | Feed de noticias con timestamp fiable (Alpaca/Benzinga, GDELT crudo) + API LLM | Sí hacia adelante; el histórico pre-corte del modelo está contaminado por memorización | Lopez-Lira & Tang (arXiv 2304.07619): ~90% hit-rate inicial post-cutoff; decae con adopción | **Probar** (solo forward-testing real, nunca como "backtest" sobre noticias que el LLM ya "conoce") |
| Puntuar noticias históricas con LLM y backtestear contra ellas | Igual que arriba + noticias anteriores al corte del modelo | No de forma fiable — sesgo de lookahead no cuantificado sin test LAP | arXiv 2512.23847 (LAP), arXiv 2309.17322 (look-ahead + distracción) | **Descartar** tal cual; solo con test LAP explícito |
| Sentimiento Twitter/X (léxico cripto) | API de X (cara tras cambios 2023+) o agregador (LunarCrush/The Tie) | Sí, con histórico de pago | Horizonte de 1 semana a 1 mes documentado; régimen de estudio 2017-2021, posible alpha decay | **Probar con cautela** (horizonte largo, no encaja con 15m-4h sin adaptar) |
| Sentimiento Reddit | Pushshift/API Reddit + NLP propio | Sí | Evidencia contradictoria entre papers académicos | **Descartar** como señal aislada |
| Google Trends | Google Trends API (gratis) | Sí, diario/semanal | Mejor para volatilidad que dirección | **Probar** solo como filtro de régimen/volatilidad, no dirección |
| Order book imbalance (L2 completo) | Snapshots L2 institucionales (Kaiko, 1.000-2.500$/mes) | Sí, pero caro | Efecto real pero sub-económico tras costes, según literatura | **Caro** / descartar para retail |
| CVD, footprint, imbalance con trades públicos | Trades públicos vía exchange API (gratis, soportado nativo por Freqtrade "advanced-orderflow") | Sí, viable en 15m-4h | Sin paper académico que cuantifique win-rate; lógica de microestructura sólida | **Probar** (mejor relación coste/beneficio de toda la investigación) |
| Mapas de liquidación (Coinglass/Hyblock) | Suscripción a la plataforma (gratis/bajo coste) | Parcial — son estimaciones, no datos verificados en CEX | Ninguna verificación independiente en CEX; ground truth solo en DEX on-chain (Hyperliquid) | **Probar como contexto**, no como señal dura |
| Barridos de liquidez / stop hunts | Precio + volumen de alta resolución (ya disponible) | Sí | Win-rates de comunidad SMC/ICT no verificados académicamente | **Probar con escepticismo**, validar con datos propios, ignorar cifras de "gurús" |
| Flujos ETF spot BTC (Farside) | Datos diarios gratuitos de Farside | Sí, desde ene-2024 | ~53,7 pb de movimiento por cada 100M$ de flujo neto, sin reversión, sobre 170 sesiones de 2026 | **Probar** (buena relación calidad/coste/timestamp, aunque solo frecuencia diaria) |
| CME COT (posicionamiento institucional futuros) | Datos semanales gratuitos CFTC | Sí, semanal | Cobertura parcial (solo CME regulado); retraso de 3 días estructural | **Probar solo como contexto de régimen**, no timing |
| Stablecoin supply (USDT/USDC) | Datos on-chain agregados (gratis/bajo coste) | Sí | Señal diluida en 2025-2026 por usos no especulativos de stablecoins | **Descartar como señal aislada**, posible filtro de fondo débil |
| Netflow de ballenas a exchanges | Glassnode/CryptoQuant/Whale Alert (freemium) | Sí | Mejor para predecir picos de volatilidad que dirección | **Probar** para gestión de riesgo/tamaño, no para dirección |
| Drift pre-FOMC / sell-the-news FOMC | Calendario FOMC (gratis) + precio | Sí, pero n≈9 eventos citados | Patrón "8/9 cae" con muestra muy pequeña | **Descartar como señal de dirección**; usar solo para reducir tamaño de posición en la ventana |
| Reacción a sorpresas de CPI | Calendario CPI + consenso (gratis) + precio de alta resolución | Sí, decenas de eventos | R² de hasta 80% en la 1ª hora en ventana móvil reciente | **Probar** (la señal macro programada más sólida de la investigación), pero ejecución compite con velocidad institucional |
| Max pain / vencimiento de opciones | Open interest Deribit (gratis/bajo coste) | Sí | Evidencia reciente contradice el "efecto imán" | **Descartar** como objetivo de precio |
| Patrón de halving | Calendario de halving (gratis) | Técnicamente sí, pero n=4 | n=4, reconocido como insuficiente hasta por sus defensores | **Descartar** para timing; válido solo como narrativa de fondo |
| Latencia / velocidad en eventos programados | Colocation, FPGA, líneas dedicadas | N/A — no es una estrategia de datos sino de infraestructura | Arms race de microsegundos, presupuestos de 5-6 cifras/mes | **Descartar** (inviable para un particular por definición) |

---

## Resumen final (15-25 líneas)

No existe ninguna fuente de "anticipación" en este espacio que sea simultáneamente barata, fiable al minuto y con evidencia académica robusta de predictibilidad neta de costes — siempre hay que sacrificar al menos una de las tres. Para noticias, el problema de fondo del usuario (falta de timestamp al minuto) tiene una solución parcial y gratuita en GDELT (pipeline de 15 minutos, pero exige trabajo propio de procesado) y una solución de pago razonable en Alpaca+Benzinga (wire service profesional, histórico desde 2015, orientado explícitamente a backtesting) — CryptoPanic en su API oficial no sirve para reconstruir histórico. Puntuar noticias con LLM funciona hacia adelante (Lopez-Lira & Tang documentan ~90% de acierto en la reacción inicial con titulares posteriores al corte del modelo), pero cualquier "backtest" contra noticias antiguas de BTC está contaminado por memorización del modelo — dos papers de 2023 y 2026 (arXiv 2309.17322 y 2512.23847) cuantifican este sesgo y muestran que ni siquiera anonimizar las entidades lo elimina del todo. El sentimiento social tiene su mejor evidencia en Twitter/X a horizonte de semanas (no de horas), evidencia contradictoria en Reddit entre estudios serios, y mejor poder predictivo de Google Trends sobre volatilidad que sobre dirección. En microestructura, la buena noticia para el proyecto es que Freqtrade ya soporta construir CVD, footprint y desequilibrios con trades públicos gratuitos ("advanced-orderflow"), viable para 15m-4h sin pagar por datos institucionales; el order book L2 completo (Kaiko, 1.000-2.500 $/mes) sí predice a corto plazo según la literatura, pero el efecto es demasiado pequeño para superar costes de transacción salvo con infraestructura de latencia que un particular no puede tener. Los flujos diarios de ETF spot (Farside, gratis) son la señal de "dinero real" más limpia y barata encontrada, con impacto de precio medido y sin reversión, aunque solo a frecuencia diaria. Entre los eventos programados, el CPI tiene la evidencia estadística más sólida (decenas de eventos, R² alto en la primera hora); FOMC y sobre todo el halving (n=4) son patrones populares con muestras demasiado pequeñas para sostener ninguna inferencia seria, exactamente el mismo defecto que ya llevó a descartar el Fear & Greed Index. El max pain de opciones no se sostiene con datos recientes. La lista de "esto no funciona" incluye competir en velocidad en eventos macro (terreno exclusivo de HFT con colocation), confiar en estrategias de sentimiento ya publicadas y popularizadas (alpha decay documentado y cuantificado), y tratar los mapas de liquidación de Coinglass/Hyblock como datos duros cuando en realidad son estimaciones sobre exchanges opacos. La recomendación de mayor relación coste/beneficio para este proyecto es doble: (1) implementar CVD/footprint/imbalance con Freqtrade sobre trades públicos, y (2) incorporar el flujo diario de ETF de Farside como filtro de régimen — ambas cosas son gratuitas, tienen timestamp fiable, y tienen evidencia (aunque no perfecta) de predictibilidad real. Cualquier uso de LLM sobre noticias debe restringirse a producción en tiempo real, nunca a backtest histórico, hasta aplicar explícitamente un test tipo LAP.



