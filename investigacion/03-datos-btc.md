# Datos de Bitcoin: fuentes, señales no-precio y trampas — investigación profunda

> Fecha de la investigación: 8 de septiembre de 2026. Todo lo que sigue está basado en documentación oficial de APIs y en fuentes públicas verificadas por búsqueda web; cuando un dato es una estimación de terceros (no oficial) se indica explícitamente. El objetivo es que puedas decidir, sin ser programador, **qué datos merece la pena conectar al bot y cuáles son ruido, caro o directamente engañoso**.

---

## Índice

1. [Precio / OHLCV](#1-precio--ohlcv)
2. [Derivados](#2-derivados)
3. [On-chain](#3-on-chain)
4. [Macro](#4-macro)
5. [Evidencia: ¿qué predice de verdad?](#5-evidencia-qué-predice-de-verdad)
6. [Trampas de datos y cómo montar un almacén "point-in-time"](#6-trampas-de-datos-y-cómo-montar-un-almacén-point-in-time)
7. [Tabla resumen final](#7-tabla-resumen-final)

---

## 1. Precio / OHLCV

Esto es la base de cualquier bot: velas de Apertura-Máximo-Mínimo-Cierre-Volumen (OHLCV, por sus siglas en inglés). Parece lo más sencillo, pero es donde más trampas silenciosas hay.

### 1.1 Binance

- **API en vivo**: `GET /api/v3/klines` (spot) y `GET /fapi/v1/klines` (futuros perpetuos USDT-M). Documentación: [Binance Open Platform – Klines](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api).
- **Límite por petición**: máximo 1000 velas. Para pedir años de historia hay que paginar con `startTime`/`endTime` en milisegundos, avanzando ventana a ventana.
- **Intervalos soportados**: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M.
- **Profundidad de histórico**: BTCUSDT spot cotiza en Binance desde agosto de 2017; el perpetuo BTCUSDT (USDT-margined) desde septiembre de 2019.
- **Descarga masiva sin pelear con el rate limit**: [data.binance.vision](https://data.binance.vision/) (repositorio público, sin autenticación). Guarda ficheros ZIP diarios y mensuales con URL predecible, por ejemplo:
  `https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2021-05.zip`
  Existen carpetas equivalentes para `data/futures/um/` (USDT-margined) y `data/futures/cm/` (COIN-margined), y no solo klines: también `aggTrades`, `trades`, `fundingRate` y `premiumIndexKlines`. Es, con diferencia, la forma más rápida y barata de bajarte 5-8 años de velas de BTC sin gastar cuota de API. Repositorio de referencia: [binance/binance-public-data en GitHub](https://github.com/binance/binance-public-data).
- **Rate limit de la API en vivo**: basado en "weight" por IP (1200 de peso/minuto aprox.), suficiente para uso normal de un bot pero no para descargar histórico completo vela a vela — para eso usa los dumps.

### 1.2 Bybit

- **API v5**: `GET /v5/market/kline`. Documentación oficial: [bybit-exchange.github.io/docs/v5/market/kline](https://bybit-exchange.github.io/docs/v5/market/kline).
- Parámetro `category` obligatorio: `spot`, `linear` (USDT/USDC perp), `inverse` (perp con margen en cripto).
- Intervalos: 1,3,5,15,30,60,120,240,360,720 minutos, D, W, M.
- Igual que Binance, cada llamada devuelve un lote limitado (por defecto 200, hasta 1000 con `limit`); hay que paginar con `start`/`end`.
- El histórico inverso (BTCUSD) arranca en 2018; el lineal (BTCUSDT perp) es más reciente (~2020).
- Bybit también publica **ficheros históricos descargables** en `public.bybit.com` (trades y klines), similar en filosofía a data.binance.vision, útil para no golpear el límite de la API en vivo.

### 1.3 OKX

- **API v5**: `GET /api/v5/market/candles` (recientes, hasta 300 por llamada) y `GET /api/v5/market/history-candles` (histórico, **limitado a 100 velas por llamada**). Hay que paginar hacia atrás con el parámetro `after`.
- Documentación: [OKX API guide](https://www.okx.com/docs-v5/en/).
- **Trampa conocida**: varias librerías (p.ej. ccxt) han tenido bugs report ados en el cambio automático entre el endpoint de velas "recientes" y el de "histórico" — verifica siempre que no se te queden huecos al pedir rangos largos.

### 1.4 Coinbase (Exchange/Advanced Trade)

- Endpoint de velas: máximo **300 puntos por petición**, y solo unas granularidades fijas permitidas: 60, 300, 900, 3600, 21600, 86400 segundos (1m, 5m, 15m, 1h, 6h, 1d). Documentación: [Coinbase Developer Docs – Get Product Candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles).
- Si pides un rango que con esa granularidad supera 300 velas, la petición se **rechaza** (no se trunca silenciosamente, lo cual es bueno: falla de forma visible).
- BTC-USD cotiza en Coinbase desde 2015. Coinbase es spot puro (Coinbase International sí tiene perpetuos, pero es un producto/API distinto orientado a institucionales).

### 1.5 Kraken

- **API REST en vivo**: `GET /0/public/OHLC`. Documentación: [Kraken Developers – Get OHLC Data](https://docs.kraken.com/api-reference/market-data/get-ohlc-data). Solo devuelve **las últimas 720 velas del intervalo pedido** — no puedes pedir "OHLC de 2019" directamente por API, cae fuera de rango.
- **Descarga masiva histórica real**: Kraken publica CSVs OHLCVT (Open/High/Low/Close/Volume/Trades) desde el origen de cada par, en intervalos de 1, 5, 15, 30, 60, 240, 720 y 1440 minutos: [Kraken Support – Downloadable historical OHLCVT data](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data). BTC/USD (XBTUSD) tiene histórico desde 2013 — es de los más largos entre exchanges "grandes" actuales.

### 1.6 Trampas transversales en precio/OHLCV

- **Vela incompleta**: la última vela de cualquier endpoint "en vivo" está todavía abierta y se sigue actualizando; si tu bot la usa para calcular indicadores, estás usando datos que cambiarán retroactivamente dentro de la misma vela (mini lookahead). Siempre trabaja con la última vela **cerrada**.
- **Spot vs. perpetuo**: son series de precio distintas (el perpetuo lleva prima/descuento por el funding, ver sección 2). Mezclar velas de spot con reglas pensadas para perpetuo (o viceversa) descuadra backtests silenciosamente.
- **Cambios de par / delisting**: si construyes tu universo de "pares disponibles" a partir del listado actual de un exchange, los pares que fueron retirados desaparecen de tu vista — esto es *survivorship bias* clásico. Para BTC/USDT en los grandes exchanges no es grave (nadie ha deslistado BTC), pero si algún día amplías a altcoins sí importa mucho.
- **Volumen en base vs. quote**: algunos exchanges devuelven volumen en BTC, otros en USDT; si comparas volumen entre exchanges sin normalizar, las conclusiones son basura.
- **Zona horaria / cierre de vela**: la mayoría de exchanges cripto usan UTC y cierran vela diaria a las 00:00 UTC, pero comprueba siempre — no está garantizado y algunos dashboards de terceros usan el cierre a las 00:00 hora de Nueva York.
- **Discrepancias entre exchanges**: el mismo BTC/USDT en Binance y Bybit no tiene el mismo precio exacto en el mismo timestamp (liquidez y flujo de órdenes distintos). Si tu bot opera en un exchange pero calcula señales con velas de otro, hay slippage de "índice" implícito.

---

## 2. Derivados

Bitcoin se opera mayoritariamente vía derivados (los volúmenes de futuros perpetuos superan varias veces al spot). Esto genera señales que no existen en el precio puro.

### 2.1 Funding rate (tasa de financiación)

**Qué mide, en cristiano**: en un contrato perpetuo no hay fecha de vencimiento, así que el exchange usa el funding para forzar a que el precio del perpetuo no se despegue del precio spot. Si el perpetuo cotiza por encima del spot (mucha gente apalancada en largo), el funding es positivo y **los largos pagan a los cortos** cada cierto tiempo (normalmente cada 8 horas). Si el funding es muy alto y sostenido, es una señal de que el mercado está "sobre-apalancado en largo" — el combustible típico de una cascada de liquidaciones bajista (long squeeze).

- **Fórmula de Binance**: `Funding Rate = Índice de Prima Promedio + clamp(Tasa de interés − Índice de Prima, -0.05%, +0.05%)`. El índice de prima compara el precio del perpetuo contra el índice spot ponderado de varios exchanges.
- **APIs**:
  - Binance: `GET /fapi/v1/fundingRate` — [documentación](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History). Sin `startTime`/`endTime` devuelve los últimos 200 registros; con rango de fechas puedes pedir bloques de hasta 1000. Como el funding es cada 8h desde 2019, en teoría se puede reconstruir todo el histórico paginando — es gratis y factible.
  - Bybit: `GET /v5/market/funding/history` — [doc](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate). Igual de paginable, gratis.
  - OKX: `GET /api/v5/public/funding-rate-history` — **capado a los últimos 400 registros** (~1 año si el funding es cada 8h). Para histórico más largo en OKX necesitas haberlo ido guardando tú mismo o pagar a un agregador.
  - Desde 2023 varios exchanges (Binance incluido) permiten frecuencias de funding variables (1h/4h/8h según el par) para pares muy volátiles — mira siempre el campo de intervalo, no asumas 8h fijo.
- **Histórico agregado multi-exchange gratis para consultar (no para API masiva)**: [CoinGlass](https://www.coinglass.com/) muestra funding rate histórico de decenas de exchanges en su dashboard web gratuito; la API de pago (desde 29$/mes) da acceso programático.

### 2.2 Open Interest (OI, interés abierto)

**Qué mide**: el valor total de contratos de futuros/perpetuos que siguen abiertos (sin cerrar) en un momento dado. OI creciente + precio subiendo = dinero nuevo entrando en largo (tendencia con "combustible"). OI creciente + precio plano = posible acumulación de apuestas en ambas direcciones antes de un movimiento fuerte.

- **Binance**: `GET /futures/data/openInterestHist` — [doc](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics). **Trampa importante: solo devuelve el último mes de datos.** No hay forma de pedir OI histórico de 2021 directamente a la API de Binance. Si quieres histórico profundo de OI tienes dos caminos: (a) empezar a recolectarlo tú mismo desde hoy y guardarlo, o (b) pagar a un agregador (CoinGlass, Coinalyze, CryptoDataDownload) que lleve años acumulándolo.
- **Bybit**: `GET /v5/market/open-interest` — mismo patrón, ventana corta reciente.
- Igual que el funding, el **dashboard gratuito de CoinGlass** permite ver gráficos de OI histórico agregado, pero descargarlo en bruto vía API es de pago.

### 2.3 Basis / prima (perpetuo vs. spot, y futuros CME vs. spot)

- **Perp vs. spot**: la relación directa con el funding rate — cuando el funding es persistentemente positivo, el perpetuo cotiza con prima sobre spot (contango). Se puede leer directo del `premiumIndexKlines` de Binance (gratis, incluido en data.binance.vision).
- **Futuros CME (institucional) vs. spot**: el CME lista futuros de Bitcoin desde diciembre de 2017. La "basis" CME (precio futuro − precio spot de referencia) es seguida de cerca porque refleja el apetito institucional regulado (fondos, ETFs delta-neutral, arbitraje de carry).
  - **CME DataMine** es la plataforma oficial de históricos de CME, pero **es de pago** ([cmegroup.com/datamine](https://www.cmegroup.com/datamine.html)).
  - El **CME CF Bitcoin Reference Rate (BRR)** y el **Real-Time Index (RTI)**, calculados por CF Benchmarks a partir de Bitstamp, Coinbase, Gemini, Kraken, LMAX Digital, Bullish y Crypto.com, son el precio spot de referencia "oficial" institucional — se pueden consultar gratis puntualmente en la web de CME, pero el histórico bulk es de pago.
  - Alternativas de pago más baratas que CME DataMine: Databento, Firstrate Data, Barchart.
  - No hay una fuente gratuita fiable de histórico bulk de la basis CME; si te interesa, la aproximación gratuita razonable es comparar el precio de cierre diario de CME (publicado gratis con retraso en su web, sin API) contra el spot del mismo instante.

### 2.4 Long/Short Ratio

- Binance ofrece dos variantes gratis vía API:
  - `GET /futures/data/topLongShortAccountRatio` (solo "top traders")
  - `GET /futures/data/globalLongShortAccountRatio` (todas las cuentas)
- **Misma trampa que el OI: solo el último mes de histórico vía API.**
- **Ojo con la interpretación**: es un ratio de **número de cuentas**, no de tamaño de posición — 1000 cuentas pequeñas en largo y 10 balleneras en corto pueden dar un ratio "muy largo" que no refleja el riesgo real de mercado. Se usa sobre todo como indicador contrarian de sentimiento extremo (ratio muy desequilibrado = posible squeeze en la dirección contraria).

### 2.5 Liquidaciones

**Qué mide**: cuando una posición apalancada no puede cubrir el margen, el exchange la cierra forzosamente ("liquida"). Rachas de liquidaciones en cascada amplifican los movimientos de precio (cada liquidación de largo vende, empujando el precio más abajo y liquidando al siguiente largo apalancado).

- **No hay una fuente única y "oficial" fiable con histórico largo y gratuito.** Los exchanges publican liquidaciones individuales en streams de WebSocket en tiempo real, pero rara vez ofrecen un endpoint REST con histórico profundo gratis.
- **CoinGlass** es el agregador de referencia del sector: escucha esos streams de múltiples exchanges y construye el histórico. Su [documentación de API](https://docs.coinglass.com/reference/aggregated-liquidation-history) cubre liquidación agregada, por exchange, heatmaps, etc. **De pago desde 29$/mes** (plan Hobbyist, uso personal, 30 peticiones/min); en diario, todos los planes dan histórico desde 2019, pero para intervalos de 1 minuto hace falta plan Standard o superior.
- **Trampa importante**: como cada agregador solo ve lo que sus conexiones a exchanges le permiten capturar, **distintos proveedores muestran cifras distintas de "la misma" liquidación total** — nunca mezcles series de liquidaciones de dos proveedores distintos en el mismo backtest.

### 2.6 Volatilidad implícita: DVOL de Deribit

**Qué mide, en cristiano**: es el "VIX de Bitcoin". No mide cuánto se ha movido el precio en el pasado (eso es volatilidad realizada), sino cuánto movimiento espera el mercado de opciones en los próximos 30 días, según lo que la gente está dispuesta a pagar por protegerse (opciones). Cuando DVOL se dispara, el mercado espera un mes movido; cuando está muy bajo y comprimido, suele preceder a rupturas fuertes en cualquier dirección.

- Índice oficial de Deribit, lanzado en **marzo de 2021** — no hay DVOL "real" (implícito) antes de esa fecha, por mucho que algún proveedor lo muestre "reconstruido" hacia atrás con supuestos.
- API pública de Deribit: `public/get_volatility_index_data` (histórico del índice) — [documentación](https://docs.deribit.com/api-reference/market-data/). También existe `public/get_historical_volatility`, que es volatilidad **realizada** (no confundir con la implícita del DVOL).
- Terceros que lo replican con variantes "point-in-time" (útiles para backtest sin lookahead): Tardis.dev (histórico tick desde 2021-04-01), Amberdata, Glassnode (con variante PiT), CryptoDataDownload (CSV gratis).

### 2.7 Skew 25-delta, estructura temporal y "max pain"

- **Skew 25-delta**: diferencia entre la volatilidad implícita de un put 25-delta y un call 25-delta, normalizada por la IV ATM. Skew positivo = el mercado paga más por protección bajista (miedo direccional); skew negativo = más apetito por calls (euforia/FOMO alcista). Deribit no publica un único número de skew "oficial" listo para consumir — hay que construirlo tú mismo a partir del libro de opciones (`public/get_book_summary_by_currency` u orderbook por instrumento), o pagar a Glassnode/Laevitas/Amberdata que ya lo calculan y sirven vía API.
- **Estructura temporal (term structure)**: comparar la IV ATM a 1 semana, 1 mes, 3 meses y 6 meses. Normalmente en contango (vencimientos lejanos más caros); quiebra a backwardation (corto plazo más caro que largo plazo) en momentos de pánico agudo — señal de estrés inminente/actual.
- **Open interest de opciones y "max pain"**: el max pain es el strike donde, si el precio cerrara ahí en el vencimiento, el conjunto de compradores de opciones (puts+calls) perdería más dinero (los vendedores de opciones ganan más). Es una teoría discutida — el "efecto imán" hacia el max pain es débil y muy dependiente del volumen que quede por cerrar cerca del vencimiento. Deribit da el OI bruto por instrumento gratis vía API; el cálculo de max pain "bonito" lo hacen gratis en dashboards CoinGlass/Laevitas o de pago si quieres API.

### 2.8 Posicionamiento institucional regulado: CFTC COT (CME)

- El **Commitment of Traders (COT)** de la CFTC desglosa, cada viernes, cómo estaban posicionados los distintos tipos de trader (dealers, asset managers, **leveraged funds** = hedge funds/CTAs, y otros) en los futuros de Bitcoin del CME, con el corte del martes anterior. Es **gratis** y oficial: [cftc.gov/MarketReports/CommitmentsofTraders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm).
- **Limitación estructural**: solo cubre futuros de Bitcoin regulados por CME (una fracción del mercado total, el resto se opera en exchanges cripto no regulados), y llega con **3 días de retraso estructural** respecto al momento real de la posición — no es apto para timing fino, sí para leer el sesgo de fondo de los grandes jugadores regulados.

---

## 3. On-chain

Estas métricas usan el hecho de que la blockchain de Bitcoin es un libro contable público: cada moneda que se mueve deja rastro del precio al que se movió por última vez. Esto permite calcular, para todo el suministro de BTC, quién está en ganancia o pérdida en cada momento — algo que no existe en ningún otro mercado financiero tradicional.

### 3.1 Métricas de valoración de ciclo: MVRV, MVRV Z-Score

- **Realized Cap (capitalización realizada)**: en vez de multiplicar el precio actual por todos los BTC en circulación (como hace la capitalización de mercado normal), la Realized Cap suma, para cada moneda, el precio al que se movió por última vez on-chain. Es como preguntarle a cada BTC "¿a cuánto te compraron la última vez?" y sumarlo todo. Esto da una especie de "coste base agregado" de todo el mercado.
- **MVRV** = Capitalización de Mercado ÷ Capitalización Realizada. Si MVRV = 3, de media todo el suministro está sentado sobre una ganancia latente de 3x respecto a su último coste. Es la versión cripto del "precio sobre valor en libros".
- **MVRV Z-Score** = (Cap. de Mercado − Cap. Realizada) ÷ desviación estándar de la Cap. de Mercado. Normaliza la diferencia para poder comparar entre ciclos con distinta escala de precio. Ejemplo para explicárselo a alguien no técnico: es como decir "el precio está a X desviaciones típicas por encima de lo que la gente pagó de media" — cuanto más alto, más "caliente" (sobrecomprado) está el mercado respecto a su propia historia.
- **Fuentes**:
  - [Glassnode](https://docs.glassnode.com/guides-and-tutorials/metric-guides/mvrv/mvrv-z-score) — el estándar de la industria. Gráficos gratis con retraso/limitación en Studio; **API completa solo desde el plan Professional** (~999$/año facturado anual según lo encontrado). El plan Advanced (49$/mes) da una "Light API" capada a 50 llamadas/día.
  - [Coin Metrics Community API](https://coinmetrics.io/community-network-data/) — **totalmente gratis, sin API key**, en `community-api.coinmetrics.io/v4`, licencia CC BY-NC 4.0. Da `CapMrktCurUSD` (cap. mercado) y `CapRealUSD` (cap. realizada) — con eso puedes calcular tú mismo el MVRV gratis, actualizado a diario.
  - [bitcoin-data.com (BGeometrics)](https://bitcoin-data.com/) — API REST gratuita con registro (sin tarjeta), pero **muy limitada: 8 peticiones/hora y 15/día en el plan free**. Cubre MVRV, NUPL, SOPR, realized price, hashrate, flujos de exchange, etc., con histórico desde el bloque génesis (2009) en granularidad diaria/horaria/por bloque.
  - [CryptoQuant](https://cryptoquant.com/) — gráficos gratis en la web, **API de pago desde el plan Professional (99$/mes facturado anual)**.
  - Gráficos gratuitos "para mirar" (no API): [checkonchain.com](https://charts.checkonchain.com/), [Look Into Bitcoin](https://www.lookintobitcoin.com/charts/mvrv-zscore/).

### 3.2 SOPR, aSOPR, STH-SOPR

- **SOPR (Spent Output Profit Ratio)** = precio al que se vendió una moneda ÷ precio al que se compró esa misma moneda. SOPR > 1 significa que, de media, las monedas que se movieron ese día se vendieron con beneficio; SOPR < 1, con pérdida. Ejemplo: si compraste 0.1 BTC a 20.000$ y hoy lo mueves con BTC a 60.000$, tu SOPR individual es 3; el SOPR de mercado es la media ponderada de todos los movimientos del día.
- **aSOPR (ajustado)**: filtra las salidas gastadas en menos de 1 hora (cambios de wallet, transacciones internas de exchanges que no son compra/venta real) — entre el 20% y el 40% del volumen diario es "ruido" de este tipo, así que aSOPR da una lectura más limpia.
- **STH-SOPR**: SOPR calculado solo con monedas de menos de 155 días de antigüedad — aísla el comportamiento de los especuladores/traders recientes (los que reaccionan a momentum), frente a los holders de largo plazo.
- **Uso típico**: en tendencia alcista, cuando el SOPR retesta el nivel 1.0 desde arriba y rebota, se lee como "soporte de coste base" (la gente que estaba en pérdida deja de vender en pánico); si lo rompe hacia abajo, se lee como señal de debilidad.
- **Fuentes**: mismas que MVRV (Glassnode es la referencia original, CryptoQuant tiene equivalente propio, bitcoin-data.com lo da gratis con las limitaciones de rate ya mencionadas).

### 3.3 NUPL (Net Unrealized Profit/Loss)

- NUPL = (Capitalización de Mercado − Capitalización Realizada) ÷ Capitalización de Mercado. Es prácticamente el mismo ingrediente que el MVRV, pero expresado como fracción del total: "¿qué porcentaje del valor total del mercado es ganancia latente sin realizar?"
- **Zonas de referencia** (siempre orientativas, no reglas fijas):
  - `> 0.75` → Euforia/Codicia (ha coincidido con techos macro en 2013, 2017 y 2021)
  - `0.5 – 0.75` → Creencia
  - `0.25 – 0.5` → Optimismo
  - `0 – 0.25` → Esperanza
  - `< 0` → Capitulación (media del mercado en pérdida)
- **Dato relevante para no confiar ciegamente**: en el ciclo 2024-2025 el NUPL **no llegó a superar 0.75** en el techo de ese ciclo — la primera vez que el patrón "falla" en la historia reciente. Esto ya avisa de lo poco robusta que es una regla basada en un umbral fijo cuando solo tienes 3-4 observaciones previas.

### 3.4 Realized Price, HODL Waves, Coin Days Destroyed, Dormancy, Reserve Risk

- **Realized Price** = Capitalización Realizada ÷ suministro circulante. Es el "coste base medio por moneda" del mercado — un soporte/resistencia psicológico e histórico muy vigilado (en mercados bajistas profundos, el precio de mercado suele tocar o perforar brevemente el realized price).
- **HODL Waves / Realized Cap HODL Waves**: dividen todo el suministro de BTC en "cohortes" según cuánto tiempo llevan sin moverse (menos de 1 mes, 1-3 meses, ... más de 5 años), y muestran qué % del valor total (o del suministro) representa cada cohorte. Sirven para ver visualmente si "las manos fuertes" (monedas viejas) están acumulando (banda de +5 años engordando) o distribuyendo (banda vieja adelgazando, coincide históricamente con la parte final de los ciclos alcistas).
- **Coin Days Destroyed (CDD)**: cada día que una moneda no se mueve, acumula "1 día-moneda". Cuando finalmente se gasta, esos días acumulados se "destruyen" y se contabilizan. Da más peso a que se mueva una moneda vieja que una recién comprada — repuntes de CDD indican que holders antiguos están vendiendo.
- **Dormancy**: CDD dividido entre el volumen de monedas transferidas ese día — dormancy alta = las monedas que se mueven hoy son, de media, viejas (mercado dominado por ventas de holders antiguos); dormancy baja = movimiento de monedas jóvenes (actividad normal de trading/día a día).
- **Reserve Risk**: combina precio y dormancy acumulada para estimar la relación entre "confianza de los holders de largo plazo" y precio — valores bajos = mucha confianza (poca destrucción de días-moneda) con precio todavía bajo, considerado zona de oportunidad histórica.
- **Fuentes**: Glassnode es quien documenta y mantiene estas métricas con más rigor (de pago para API), CryptoQuant tiene variantes similares, y — dato importante — **como todo esto se calcula a partir de datos 100% públicos de la blockchain**, técnicamente es posible calcularlo tú mismo gratis corriendo un nodo completo y parseando las transacciones; el coste de estos proveedores es el trabajo de cómputo/ingeniería ya hecho, no el acceso al dato crudo en sí.

### 3.5 Puell Multiple y Hash Ribbons (indicadores de mineros)

- **Puell Multiple** = valor en USD de todo el BTC emitido hoy (recompensa de bloque) ÷ media móvil de 365 días de ese mismo valor. Cuando está alto, los mineros ganan mucho más de lo normal (incentivo a vender agresivamente = presión vendedora); cuando está bajo, los mineros pasan penurias económicas y algunos apagan máquinas (menos presión vendedora futura, suele coincidir con suelos de mercado).
- **Hash Ribbons** (creado por Charles Edwards, Capriole Investments, 2019): compara la media móvil de 30 días del hashrate contra la de 60 días. Cuando la de 30 cruza por debajo de la de 60, hay "capitulación de mineros" (apagan equipos no rentables); la señal de compra clásica se da cuando la de 30 vuelve a cruzar por encima de la de 60 (recuperación confirmada). Según la fuente consultada, de las aproximadamente 20 señales de compra desde 2011, alrededor del 85% acertó identificando un suelo local — pero son ~20 señales en 15 años, una muestra pequeña.
- **Fuentes**: Glassnode/CryptoQuant/Bitcoin Magazine Pro (gráficos gratis, API de pago); el hashrate bruto para calcularlo tú mismo gratis está en [mempool.space](https://mempool.space/docs/api/rest) (API pública sin key, series de hashrate semanal desde 2009) y en [Look Into Bitcoin](https://www.lookintobitcoin.com/charts/hash-ribbons/) (gráfico gratis).

### 3.6 Direcciones activas, comisiones, hashrate (actividad de red)

- **[Blockchain.com Charts API](https://www.blockchain.com/api/charts_api)**: gratis, sin key, JSON o CSV. Series: direcciones únicas activas, comisiones totales (BTC y USD), hashrate estimado, número de transacciones, etc. URL tipo `https://api.blockchain.info/charts/hash-rate?format=json`.
- **[mempool.space API](https://mempool.space/docs/api/rest)**: gratis, sin key, muy rica en detalle de mempool, comisiones (fee estimates en tiempo real), dificultad, pools de minado y su cuota de hashrate. Ideal para monitorización operativa (por ejemplo, saber si las comisiones on-chain están disparadas, señal indirecta de congestión/actividad).
- **[Coin Metrics Community API](https://coinmetrics.readthedocs.io/en/latest/community.html)**: gratis, series `AdrActCnt` (direcciones activas), `FeeTotUSD`, `HashRate`, actualizadas a diario.

### 3.7 Netflows y reservas en exchanges (y por qué hay que desconfiar un poco)

- **Qué mide**: cuánto BTC entra y sale de las wallets identificadas como pertenecientes a exchanges. Entradas grandes suelen leerse como "intención de vender" (la gente manda BTC al exchange para venderlo); salidas grandes como "acumulación / retirada a custodia propia" (menos oferta líquida disponible para vender).
- **El problema de fondo**: nadie tiene la lista "oficial" de qué direcciones pertenecen a qué exchange. Cada proveedor (Glassnode, CryptoQuant) usa sus propios algoritmos de clustering y heurísticas propietarias para etiquetar direcciones, y **esas etiquetas se revisan y actualizan constantemente**, lo que significa que el histórico de "reservas de exchange de 2021" puede cambiar de valor si hoy identifican una wallet nueva que resulta pertenecer a un exchange. Esto es un riesgo de *lookahead* real si no usas datos "point-in-time" (ver sección 6).
- Por eso, **CryptoQuant y Glassnode dan cifras distintas** para "la misma" reserva total de exchanges — no son intercambiables, y mezclar series de ambos en un mismo modelo es un error común.
- **Fuentes**: CryptoQuant (considerado el más completo en esto, de pago para API), Glassnode (de pago), [CoinGlass Balance](https://www.coinglass.com/Balance) (gráfico gratis, sin API en el plan gratuito).

### 3.8 Ballenas (whales)

- Se define arbitrariamente una "ballena" como entidad con más de cierto umbral de BTC (por ejemplo, 1.000 BTC agregados en Glassnode). Se sigue el netflow de exchange asociado a esas entidades como proxy de "qué está haciendo el dinero grande".
- **Fuentes**: Glassnode (de pago), [Santiment](https://api.santiment.net/) (plan gratuito da hasta 1 año de histórico en métricas restringidas, pero con **30 días de retraso** respecto al dato actual — para uso en tiempo real necesitas plan de pago).

### 3.9 Suministro de stablecoins y Stablecoin Supply Ratio (SSR)

- **Idea**: las stablecoins (USDT, USDC...) son la "pólvora seca" del mercado cripto — dinero ya dentro del ecosistema, listo para comprar BTC sin pasar por un banco. Un aumento fuerte del suministro de stablecoins se interpreta como potencial de compra latente.
- **SSR** = Capitalización de mercado de BTC ÷ suministro total de stablecoins. SSR bajo = mucha "pólvora" en relación al tamaño de BTC (más poder de compra latente por cada dólar de BTC); SSR alto = lo contrario. A mediados de agosto de 2026, el SSR rondaba ~4,16 según la fuente consultada.
- **Cuidado**: no toda stablecoin en circulación está "esperando comprar BTC" — mucha se usa para trading entre altcoins, para pagos, o simplemente reposa en wallets sin intención de compra inminente. Es una proxy imperfecta de demanda potencial, no una medida directa de intención de compra.
- **Fuentes gratuitas**: [DefiLlama Stablecoins API](https://stablecoins.llama.fi/) (gratis, sin key), Coin Metrics Community API (series `SplyUSDT`, etc., gratis).

### 3.10 Flujos de los ETF spot de Bitcoin

- Desde enero de 2024 existen ETFs spot de Bitcoin en EE.UU. (IBIT de BlackRock, FBTC de Fidelity, ARKB, BITB, GBTC de Grayscale reconvertido, etc.). Sus flujos diarios de entrada/salida (creación/redención de participaciones) son uno de los indicadores de demanda institucional más seguidos desde entonces.
- **[Farside Investors](https://farside.co.uk/btc/)** — gratis, la referencia de facto para datos crudos en formato tabla/spreadsheet, actualizado a diario (por la noche/madrugada hora española, ya que se basa en el cierre de EE.UU.). Cubre los flujos de cada ticker por separado y el total.
- **[SoSoValue](https://www.sosovalue.com)** — dashboard gratuito equivalente, con visualizaciones más elaboradas.
- **CoinGlass** — ofrece esto empaquetado en su API de pago junto con el resto de derivados.
- **Importante**: tanto Farside como SoSoValue **recopilan y agregan datos que en última instancia publican los propios emisores de los ETF** (BlackRock, Fidelity, etc.) — no son la fuente primaria, así que en teoría pueden llevar pequeñas revisiones o discrepancias puntuales entre ellos. Para verificación cruzada de un día concreto, la fuente primaria es la propia web del emisor del fondo (p. ej. la página de holdings de IBIT).

### 3.11 Dune Analytics

- Plataforma de consultas SQL sobre datos on-chain indexados (fuerte en EVM/Ethereum; para Bitcoin nativo la cobertura es más limitada, aunque cubre wrapped BTC y algunos datasets comunitarios de Bitcoin).
- **Aviso urgente y con fecha concreta**: según lo encontrado en esta investigación (8 de septiembre de 2026), **Dune restringe su plan gratuito a solo lectura (view-only) a partir del 10 de septiembre de 2026** para cuentas creadas antes del 21 de julio de 2026 — es decir, en dos días desde hoy. Si el bot dependiera de consultas propias en Dune con cuenta gratuita, dejaría de poder ejecutarlas (solo podrías ver dashboards ya publicados por otros, no lanzar tus propias queries). Verifica el estado exacto antes de construir nada sobre esto: [Dune Docs – FAQ](https://docs.dune.com/api-reference/overview/faq).

### 3.12 Latencia y riesgo de revisión — resumen práctico

| Fuente | ¿Se revisa a posteriori? | Motivo |
|---|---|---|
| Precio OHLCV en exchange | Prácticamente no (salvo vela abierta) | Es un hecho de mercado cerrado |
| On-chain "crudo" (bloques, hashrate, fees) | No | Dato inmutable de la blockchain |
| On-chain "etiquetado" (exchange balances, whale flows) | **Sí, con frecuencia** | Depende de clustering/heurísticas que mejoran con el tiempo |
| Métricas derivadas de precio agregado (realized cap, MVRV) | Rara vez, salvo cambios de metodología del proveedor | Se recalcula si cambia la fuente de precio de referencia |
| ETF flows | Ocasionalmente (correcciones menores) | Depende de la publicación del emisor |

---

## 4. Macro

Bitcoin no vive en una burbuja: en 2022-2026 su correlación con activos de riesgo tradicionales (Nasdaq) y con la liquidez global ha sido, en muchos tramos, más determinante que cualquier métrica on-chain.

### 4.1 DXY (índice del dólar)

- El índice DXY "real" (el que todo el mundo mira, basado en una cesta de 6 divisas, calculado por ICE) es un producto propietario de ICE — no hay una API gratuita que replique exactamente esa metodología con histórico bulk.
- **Alternativas gratuitas**:
  - **Yahoo Finance** (`^DXY` o `DX-Y.NYB`) y **Stooq** dan una serie que sigue muy de cerca al DXY real, gratis, vía scraping/descarga CSV — suficiente para uso de trading algorítmico no institucional.
  - **FRED `DTWEXBGS`** (Broad Dollar Index de la Fed, calculado con una cesta mucho más amplia de divisas, no exactamente igual al DXY de ICE) — gratis, diario, desde 2006. Es una *proxy* razonable de "fortaleza del dólar", no un sustituto exacto del DXY.
- **Relación con BTC**: correlación negativa, pero **inestable en el tiempo** — ha oscilado entre -0.4 y -0.9 en distintos periodos de los últimos 5 años, llegando a un mínimo de -0.90 en abril de 2026. Es decir, es real pero **no un mecanismo fijo** — tratar el DXY como filtro de régimen macro (dólar fuerte = viento en contra para activos de riesgo) es razonable; construir una regla de entrada/salida basada en un umbral fijo de DXY es más frágil.

### 4.2 Tipos de interés: US10Y y rendimientos reales (TIPS)

- **US10Y (rendimiento nominal del bono a 10 años)**: FRED `DGS10`, gratis, diario, desde 1962.
- **Rendimiento real (TIPS a 10 años)**: FRED `DFII10`, gratis, diario. El rendimiento real (nominal menos inflación esperada) es, según muchos analistas macro, más relevante para activos "sin yield" como el oro y Bitcoin que el nominal — cuando el real sube fuerte, el coste de oportunidad de tener un activo que no paga interés (BTC, oro) aumenta.

### 4.3 Oro, índices bursátiles y volatilidad

- **Oro**: FRED tiene series de precio del oro LBMA; también accesible gratis vía Yahoo Finance (`GC=F`) o Stooq (`XAUUSD`).
- **SPX / Nasdaq**: Yahoo Finance (`^GSPC`, `^IXIC`) y Stooq, gratis, décadas de histórico diario.
- **VIX** (volatilidad implícita de opciones sobre el S&P 500): gratis en varias fuentes — [CBOE oficial](https://www.cboe.com/tradable-products/vix/vix-historical-data) (desde 1990), FRED (`VIXCLS`), Yahoo Finance.
- **MOVE Index** (equivalente al VIX pero para el mercado de bonos del Tesoro de EE.UU., mide volatilidad implícita de tasas): el índice oficial es de ICE (antes BofA Merrill Lynch, de ahí "ICE BofA MOVE"). Se puede consultar **gratis vía Yahoo Finance (`^MOVE`) e Investing.com** para uso puntual/gráfico; el histórico bulk oficial vía API requiere suscripción a ICE Data Services. No se encontró evidencia de que el índice se haya discontinuado en 2026 — sigue publicándose con normalidad.
- **Por qué importa el MOVE para BTC**: en episodios de estrés en el mercado de bonos (2022, marzo 2023 con la crisis de bancos regionales en EE.UU.), los picos de MOVE han coincidido con ventas fuertes y correlacionadas en cripto — es un termómetro de "estrés en el sistema financiero tradicional" que puede contagiar a BTC vía liquidación forzosa de posiciones apalancadas cross-asset.

### 4.4 Liquidez global: balance de la Fed, reverse repo, M2

- **Balance de la Fed**: FRED `WALCL` ("Total Assets"), semanal (dato del miércoles), gratis, desde 2002.
- **Reverse Repo (RRP)**: FRED `RRPONTSYD` (Overnight Reverse Repurchase Agreements), diario, gratis, desde 2003 (relevante en volumen sobre todo desde 2013 en adelante, y especialmente desde 2021).
- **Cuenta General del Tesoro (TGA)**: FRED `WTREGEN`.
- **"Liquidez neta"** (fórmula popular entre traders macro): `WALCL − WTREGEN − RRPONTSYD`. La idea es aislar cuánta liquidez disponible hay realmente en el sistema bancario, descontando el dinero "aparcado" en la cuenta del Tesoro o en el mecanismo de reverse repo.
- **M2**: FRED `M2SL`, mensual, gratis, desde 1959. **Trampa de metodología importante**: en mayo de 2020 la Fed **redefinió** qué depósitos cuentan dentro de M2 (incorporó depósitos de ahorro de una manera distinta), generando un **salto de nivel discontinuo** en la serie que no representa un cambio económico real — si usas M2 en niveles sin ajustar, tu modelo verá un "escalón" artificial en 2020. Trabaja con tasas de variación interanual/intermensual, no con el nivel bruto, o al menos sé consciente del salto.
- **Liquidez global (más allá de EE.UU.)**: no existe una serie FRED única — hay que construirla combinando balances de Fed + BCE + Banco de Japón + Banco Popular de China, y M2 de varias zonas económicas. Varios analistas (p. ej. Michael Howell/CrossBorderCapital) publican índices propios; no son gratuitos ni estandarizados, cada uno con su metodología.
- **Relación con BTC y el problema del "lag"**: hay bastante literatura informal (no papers revisados por pares encontrados en esta búsqueda) que sugiere que Bitcoin sigue a la liquidez global con un retraso de entre 60 y 90 días (algunas fuentes hablan de hasta 8 meses para índices de liquidez más amplios). **Ojo**: la correlación móvil a 180 días entre BTC y M2 global desplazado ha oscilado entre +0.95 y −0.90 según el periodo — es decir, el "lag óptimo" que funcionó en 2020-2021 no tiene por qué seguir funcionando igual en 2026. Trátalo como una variable de contexto/régimen, no como un reloj preciso.

### 4.5 El problema de los horarios: macro de sesión vs. BTC 24/7

Este es un punto que se pasa por alto muy a menudo y que puede romper un backtest sin que se note:

- Los datos macro (SPX, DXY, US10Y, VIX) solo se actualizan durante el horario de mercado correspondiente (bolsa de EE.UU. 9:30-16:00 hora de Nueva York, bonos algo más amplio) y **no cotizan fines de semana ni festivos**.
- BTC cotiza 24 horas, 7 días a la semana, 365 días al año.
- Si tu bot usa "el valor de SPX" o "el valor de DXY" como variable de entrada un sábado a las 3 de la madrugada, en realidad está usando **el cierre del viernes**, que puede tener ya 30-50 horas de antigüedad — y tu modelo no lo sabe si no lo marcas explícitamente.
- **Recomendación práctica**: para cualquier serie macro, guarda también el timestamp de la última actualización real (no solo el valor), y en fin de semana/festivo usa forward-fill explícito sabiendo que es un dato "congelado", no lectura fresca. No fabriques nunca un movimiento sintético de SPX de sábado a partir de futuros o CFDs sin dejar constancia de que es una fuente distinta con su propia dinámica.

### 4.6 Calendario de eventos

- **FOMC**: la Reserva Federal se reúne aproximadamente cada 6 semanas (8 reuniones/año), anuncio a las 14:00 hora del Este. Fuente oficial: [federalreserve.gov](https://www.federalreserve.gov/).
- **CPI (inflación)**: publicado mensualmente por el Bureau of Labor Statistics (BLS), normalmente 12-14 días después del cierre del mes de referencia, a las 8:30 hora del Este.
- **NFP (nóminas no agrícolas)**: BLS, primer viernes de cada mes, 8:30 hora del Este.
- **Vencimientos de derivados**: los futuros trimestrales de CME y las opciones grandes de Deribit vencen normalmente el último viernes del mes/trimestre — suelen generar volatilidad de "pinning" o de recolocación de cobertura en las horas previas.
- **Halving de Bitcoin**: el último fue en abril de 2024; el próximo está previsto alrededor de **abril de 2028** (cada 210.000 bloques, ritmo variable según hashrate).
- **Fuentes gratuitas de calendario**: la BLS y la Fed son las fuentes primarias oficiales; para un calendario agregado y consumible hay agregadores gratuitos basados en el feed de ForexFactory (varias herramientas de terceros lo normalizan a JSON).

---

## 5. Evidencia: ¿qué predice de verdad?

Aquí toca ser exigente. La mayoría del contenido divulgativo sobre estas métricas confunde tres cosas distintas: **(a)** una correlación contemporánea real, **(b)** un patrón que coincidió con lo que pasó después en 2-4 ocasiones históricas, y **(c)** evidencia estadística robusta con poder predictivo fuera de muestra. Casi todo lo que circula en redes sociales cripto es (b) disfrazado de (c).

### 5.1 Un problema estructural que hay que entender primero: muchas métricas on-chain están mecánicamente ligadas al precio

MVRV, NUPL y SOPR se calculan literalmente a partir del precio (actual y pasado) multiplicado por cantidades de monedas. Esto significa que, por construcción, **se mueven junto con el precio de forma casi contemporánea** — no es sorprendente que "MVRV alto" coincida con "precio alto", porque MVRV *contiene* el precio en su fórmula. Que una métrica "coincida" con techos y suelos no prueba que los **anticipe**; hay que comprobar específicamente si la señal aparece *antes* de que el precio se mueva, no *a la vez* o *después*.

### 5.2 MVRV Z-Score

- Sí hay trabajo de backtest serio: un estudio (referenciado en ScienceDirect, "Using on-chain data to predict Bitcoin cycles") construye y prueba estrategias basadas en comprar cuando el Z-Score cae por debajo de −0.2, contrastándolo en tres ciclos de Bitcoin (2013-2025), con mejora del rendimiento ajustado a riesgo frente a comprar y mantener.
- **Pero la muestra es de solo 3 ciclos**, todos ellos gobernados por el mismo evento estructural (el halving cada 4 años) — es una muestra estadísticamente muy pequeña para separar "patrón real" de "narrativa que se ha repetido por casualidad/por autocumplimiento (mucha gente actúa siguiendo esta misma métrica, lo que puede generar el patrón artificialmente)".
- **Extremos de verdad raros**: un MVRV Z-Score por encima de 7 (zona de "techo de ciclo" clásica) **solo ha ocurrido 2 veces en toda la historia de Bitcoin** (2013 y 2017); el techo de 2021 y el de 2025 quedaron muy por debajo de ese umbral histórico (el pico de 2025 rondó ~2.5). Con 2 observaciones, cualquier "regla" de trading es, estadísticamente hablando, casi una anécdota.
- **Veredicto**: útil como **mapa de contexto de ciclo** (¿estamos en zona barata o cara respecto a la historia?), no como señal de timing preciso. Evidencia predictiva: **media**, y decreciente en fiabilidad conforme el mercado madura (institucionalización cambia los rangos históricos).

### 5.3 SOPR / aSOPR / STH-SOPR

- Uso extendido entre traders como confirmación de "retest de soporte de coste base" en tendencias alcistas. Es, por diseño, una métrica **fuertemente contemporánea** al precio (mide beneficio/pérdida de lo que se mueve *hoy*, con el precio de *hoy*) — su valor añadido real está en confirmar comportamiento agregado del mercado (¿la gente vende con pánico o con calma?), no en anticipar movimientos futuros con antelación de días.
- No se encontró en esta investigación ningún estudio académico revisado por pares que demuestre poder predictivo del SOPR sobre el retorno *futuro* de BTC a un horizonte concreto (días/semanas) con significancia estadística fuera de muestra.
- **Veredicto**: evidencia predictiva **baja-media** — funciona mejor como indicador de confirmación/sentimiento coincidente que como señal adelantada.

### 5.4 Funding rate

- Hay un paper serio (Emre Inan, SSRN, "Predictability of Funding Rates") que muestra que modelos autorregresivos (DAR) predicen razonablemente bien **el propio funding rate del periodo siguiente** en Binance y Bybit — es decir, el funding tiene autocorrelación (momentum en sí mismo). **Esto no es lo mismo que decir que el funding predice el retorno futuro del precio de BTC.**
- La creencia popular ("funding extremadamente positivo y sostenido precede a una corrección/long squeeze") es plausible mecánicamente (mucho apalancamiento largo = más combustible para una cascada de liquidaciones), pero no se encontró un estudio académico riguroso que la cuantifique con un horizonte y muestra concretos en esta búsqueda.
- **Veredicto**: evidencia predictiva **media** como medida de "crowding"/riesgo de posicionamiento (útil para gestión de riesgo — evitar abrir largos nuevos cuando el funding ya está en extremos históricos), pero no como señal direccional por sí sola.

### 5.5 Netflows de exchanges

- La lógica intuitiva (entra BTC a exchange = intención de venta) es razonable pero tiene un problema de **causalidad inversa**: cuando el precio ya está cayendo, la gente entra en pánico y manda BTC a vender, lo cual generaría "netflow alto" como **consecuencia** de la caída, no como su causa anticipada.
- Los estudios de causalidad de Granger encontrados sobre redes de transacción y precio en Bitcoin muestran resultados mixtos y dependientes del periodo — no hay un consenso claro de que el netflow *lidere* de forma robusta y estable.
- **Veredicto**: evidencia predictiva **media-baja**; más útil como confirmación a posteriori o como alerta de riesgo (grandes entradas repentinas de ballenas conocidas) que como señal sistemática de entrada/salida.

### 5.6 Flujos de los ETFs spot de BTC

- Es innegable que 2024-2026 mostró una correlación contemporánea fuerte entre flujos de ETF y movimiento de precio (ejemplos documentados: salidas de $4.500M en junio de 2026 coincidiendo con caídas fuertes; más de $2.000M de salidas en dos semanas de mayo de 2026 coincidiendo con la caída de 80.000$ a cerca de 67.000$).
- Cifras como "los flujos de ETF explican el 45% de los movimientos semanales de BTC" circulan en medios especializados, pero son **estimaciones de blogs/medios, no papers académicos revisados por pares** — hay que tratarlas con la misma cautela que cualquier cifra sin metodología pública auditable.
- Aquí también hay riesgo de **causalidad inversa parcial**: parte del flujo de ETF es reactivo (los inversores institucionales compran *después* de ver momentum, no necesariamente antes), lo que infla la correlación contemporánea sin garantizar poder predictivo a varios días vista.
- **Limitación de muestra**: solo hay datos desde enero de 2024 — apenas dos años y medio de historia al momento de escribir esto, que incluyen un único ciclo de mercado. Cualquier "regla" calibrada sobre esta ventana es, por definición, no probada fuera de muestra en un ciclo bajista completo con ETFs ya existentes.
- **Veredicto**: evidencia predictiva **media** como indicador coincidente/confirmatorio de demanda institucional, **baja-incierta** como señal adelantada accionable.

### 5.7 DXY y macro

- La correlación negativa BTC-DXY es real y ampliamente documentada, pero **inestable en el tiempo** (de -0.4 a -0.9 según el periodo) — es un filtro de régimen razonable, no un indicador de timing.
- **Veredicto**: evidencia predictiva **media** como variable de contexto/régimen (mejor en modelos que combinan varias señales macro que como regla aislada).

### 5.8 Resumen de escepticismo: métricas con extremos "raros" que invalidan reglas simples

Cuantas menos veces ha ocurrido el "extremo" de una métrica en la historia, menos fiable es cualquier regla de trading basada en ese umbral — por simple estadística de muestra pequeña:

| Métrica | Extremo citado | Nº de veces observado en la historia de BTC |
|---|---|---|
| MVRV Z-Score | > 7 (techo de ciclo) | **2 veces** (2013, 2017) |
| NUPL | > 0.75 sostenido (euforia de techo) | **3-4 veces** (2013, 2017, 2021; ausente en 2025) |
| Puell Multiple | > 4 (extremo de mineros) | Puñado de veces, concentradas en techos de ciclo |
| Hash Ribbons | Señal de compra (cruce 30/60 MA) | ~20 señales desde 2011 |
| DXY 30d corr. con BTC | ≤ -0.90 | Episodio puntual, abril 2026 |

Con muestras de 2 a 20 observaciones en 15 años, **ningún backtest sobre estas señales tiene potencia estadística real** — lo máximo que se puede decir honestamente es "esto ha coincidido con momentos importantes en el pasado", no "esto predice el futuro con una probabilidad calculable".

---

## 6. Trampas de datos y cómo montar un almacén "point-in-time"

### 6.1 Revisiones retroactivas

Ya mencionado en cada sección, pero para resumir el patrón general: **cualquier métrica que dependa de "etiquetar" quién posee una dirección (exchanges, ballenas, mineros) puede cambiar de valor histórico el día que el proveedor mejora su algoritmo de clustering.** Glassnode lo documenta explícitamente en su ["Exchange Data: Transparency Notice"](https://docs.glassnode.com/further-information/exchange-data-transparency-notice) y ofrece métricas **Point-in-Time (PiT)** específicamente para evitar este problema en backtesting: [docs.glassnode.com/data/point-in-time-metrics](https://docs.glassnode.com/data/point-in-time-metrics). Su propio blog de investigación lo explica sin rodeos: ["Your Backtest Is Lying: Why You Must Use Point-in-Time Data"](https://research.glassnode.com/why-use-point-in-time-data/).

### 6.2 Cambios de metodología del proveedor

Glassnode documenta en su changelog cambios como: actualización de la fuente de precisión de volumen spot (cambia valores históricos de volumen), o cambios en el cálculo de liquidaciones en ciertos exchanges. **Cualquier serie histórica de un proveedor de pago puede "moverse por debajo de tus pies"** sin que tu bot se entere si simplemente vuelves a descargarla entera cada vez.

### 6.3 Datos que solo existen desde una fecha concreta (no se puede "inventar" historia)

Resumen de arranques duros que limitan cuánto puedes backtestear con cada señal:

- DVOL (IV implícita real de Deribit): **marzo de 2021**
- Flujos de ETF spot BTC: **enero de 2024**
- Funding rate Binance perpetuo BTCUSDT: **septiembre de 2019**
- Open interest histórico vía API oficial de exchanges: **prácticamente inexistente más allá de 30 días** salvo que lo hayas ido guardando tú o pagues a un agregador
- M2 sin salto de definición: reconstrucción limpia solo hasta **mayo de 2020** hacia atrás con ajuste manual

### 6.4 Point-in-time vs. recalculado — la distinción que más dinero cuesta si se ignora

- **Point-in-time (PiT)**: el valor exacto que un proveedor habría mostrado si hubieras consultado la métrica *ese mismo día*, congelado para siempre, aunque después se descubran nuevas direcciones de exchange o se corrija algo.
- **Recalculado (recomputed)**: el valor "actual, mejor conocido hoy" de una fecha pasada, que puede ser distinto del que existía entonces.
- Si tu bot entrena o backtestea con series **recalculadas** en vez de PiT, estás dándole información del futuro sin darte cuenta (*lookahead bias* silencioso) — tu backtest parecerá mejor de lo que el sistema habría sido realmente operando en tiempo real.

### 6.5 Cómo montar un almacén de datos "respetuoso con el punto en el tiempo" (explicado sin jerga)

Idea central: **nunca sobrescribas datos históricos cuando un proveedor te da una versión "corregida"** — guarda ambas versiones, con marca de tiempo de cuándo se guardó cada una.

1. **Ingesta append-only**: cada vez que descargas un dato (por ejemplo, "reserva de exchanges el 1 de marzo de 2024"), guárdalo junto con la fecha en la que **tú lo descargaste**, no solo la fecha a la que se refiere el dato. Si mañana descargas otra vez ese mismo 1 de marzo de 2024 y el valor ha cambiado, guarda una fila nueva, no sobrescribas la anterior.
2. **Dos fechas por cada dato** (esto se llama diseño "bitemporal"): la fecha del evento (`fecha_valor`) y la fecha en que se conoció ese valor (`fecha_ingesta`). Para hacer un backtest honesto, tu simulación en el "día X" solo puede usar filas cuya `fecha_ingesta` sea ≤ X.
3. **Herramientas que ya implementan esto**: [ArcticDB](https://arcticdb.io/) (de Man Group, código abierto, pensado justo para esto: versiona automáticamente cada escritura y permite "viajar en el tiempo" a lo que se sabía en cualquier fecha pasada) o [TimescaleDB](https://github.com/timescale/timescaledb) (extensión de PostgreSQL, más manual pero muy sólida, tendrías que implementar tú el patrón bitemporal con dos columnas de fecha).
4. **Cuando el proveedor no ofrece variante PiT** (la mayoría de fuentes gratuitas no la ofrecen): la aproximación defensiva razonable es **aplicar un retraso de seguridad** a la serie igual a la ventana de revisión típica conocida de esa métrica (por ejemplo, si sabes que las reservas de exchange de CryptoQuant se pueden revisar hasta 2-3 días después, no dejes que tu backtest use el valor "de hoy" el mismo día — usa el valor tal y como estaba disponible hace esos 2-3 días).
5. **Nunca mezcles fuentes a mitad de serie**: si empezaste tu histórico de netflows con CryptoQuant y luego cambias a Glassnode porque es más barato, vas a introducir un salto artificial en el dato justo en la fecha del cambio — trata ambas fuentes como series distintas, nunca como continuación la una de la otra.

---

## 7. Tabla resumen final

| Métrica | Fuente principal | ¿Gratis o pago? | Histórico disponible | Latencia | Riesgo de lookahead | Evidencia predictiva |
|---|---|---|---|---|---|---|
| OHLCV spot (API en vivo) | Binance / Bybit / Kraken | Gratis | Binance desde 2017, Kraken desde 2013 | Tiempo real (vela abierta cuidado) | Bajo | N/A (es el precio) |
| OHLCV dumps masivos | data.binance.vision | Gratis | Igual que arriba | Diario/mensual | Bajo | N/A |
| Funding rate | Binance/Bybit (API), OKX (API, cap ~1 año) | Gratis | Desde 2019 (Binance) si se pagina bien | Tiempo real | Bajo si se recolecta bien | Media (crowding, no dirección) |
| Open interest histórico | APIs de exchange | Gratis pero solo 30 días | Nulo sin recolección propia o pago | Tiempo real | Alto si dependes solo de la API | Media |
| Long/short ratio | Binance API | Gratis, solo 30 días | Igual que OI | Tiempo real | Alto (histórico) | Media (contrarian) |
| Basis / futuros CME | CME DataMine / CF Benchmarks | Pago (histórico bulk) | Desde 2017 (listado CME) | Diario | Bajo si compras oficial | Media |
| Liquidaciones agregadas | CoinGlass | Pago (desde $29/mes) | Diario desde ~2019 según plan | Near real-time | Medio (subconteo por proveedor) | Media-baja |
| DVOL (IV 30d BTC) | Deribit API (oficial) / Glassnode PiT | Gratis (Deribit) / pago (PiT) | Desde marzo 2021 | Tiempo real | Bajo (Deribit) / medio sin PiT | Media |
| Skew 25-delta | Glassnode/Laevitas/Amberdata (o cálculo propio) | Pago (o gratis si lo calculas) | ~2021 en adelante | Near real-time | Medio | Media (sentimiento direccional) |
| OI opciones / max pain | Deribit API (bruto) / CoinGlass, Laevitas (calculado) | Gratis bruto / pago calculado | Desde apertura mercado opciones | Diario/tiempo real | Bajo | Baja |
| COT CME (posicionamiento) | CFTC.gov | Gratis | Desde 2017 | Semanal, 3 días de retraso | Bajo (inherente) | Media |
| MVRV / MVRV Z-Score | Glassnode / Coin Metrics Community (gratis) / bitcoin-data.com | Mixto | Desde ~2010-2011 | Diaria | Medio | Media (extremos muy raros: 2 en historia) |
| SOPR / aSOPR / STH-SOPR | Glassnode / CryptoQuant / bitcoin-data.com | Mixto | Desde ~2011 | Diaria | Medio | Baja-media (contemporáneo, no adelantado) |
| NUPL | Glassnode / CryptoQuant / bitcoin-data.com | Mixto | Desde ~2010-2011 | Diaria | Medio | Media (solo 3-4 techos observados) |
| Realized Cap / Realized Price | Coin Metrics Community (gratis) / Glassnode | Mixto | Desde 2009-2011 | Diaria | Medio | Base de otras métricas |
| HODL Waves | checkonchain/Look Into Bitcoin (gráfico gratis) / Glassnode-CryptoQuant (API pago) | Mixto | Desde 2009 | Diaria | Medio | Media (fase de ciclo) |
| CDD / Dormancy / Reserve Risk | Glassnode (pago) / cálculo propio (gratis, nodo propio) | Mixto | Desde 2009 | Diaria | Medio | Media-baja |
| Netflows / reservas exchange | CryptoQuant / Glassnode (pago) / CoinGlass (vista gratis) | Pago mayoritariamente | Desde ~2015-2017 | Horas de retraso | **Alto** (clustering se revisa) | Media (causalidad discutible) |
| Ballenas (whale netflow) | Glassnode / Santiment (gratis con 30 días de retraso) | Pago / gratis parcial | Desde ~2017 | Variable | Alto | Media |
| Hashrate / Hash Ribbons | mempool.space (gratis) / Look Into Bitcoin (gratis) | Gratis | Desde 2009 | Near real-time | Bajo | Media (~20 señales en 15 años) |
| Puell Multiple | Glassnode/CryptoQuant/BitcoinMagazinePro | Mixto (gráfico gratis, API pago) | Desde 2009 | Diaria | Bajo-medio | Media (extremos poco frecuentes) |
| Direcciones activas / comisiones | Blockchain.com (gratis) / mempool.space (gratis) / Coin Metrics (gratis) | Gratis | Desde 2009 | Diaria | Bajo | Baja-media |
| Stablecoin supply / SSR | DefiLlama (gratis) / Coin Metrics Community (gratis) | Gratis | Desde 2014 (USDT) | Diaria | Bajo | Media |
| Flujos ETF spot BTC | Farside Investors (gratis) / SoSoValue (gratis) | Gratis | Desde enero 2024 | Diaria (noche US) | Medio (revisiones ocasionales) | Media (coincidente fuerte, adelanto dudoso) |
| DXY | FRED DTWEXBGS (gratis) / Yahoo-Stooq (gratis) | Gratis | DTWEXBGS desde 2006 | Diaria | Bajo | Media (correlación inestable) |
| US10Y / TIPS reales | FRED DGS10 / DFII10 | Gratis | Desde 1962 / 2003 | Diaria | Bajo | Media (canal de liquidez) |
| Oro / SPX / Nasdaq / VIX | FRED, Yahoo, Stooq | Gratis | Décadas | Diaria (solo sesión) | Bajo | Baja-media individualmente |
| MOVE Index | Yahoo/Investing (vista gratis) / ICE Data (bulk pago) | Mixto | Amplio vía Yahoo | Diaria (solo sesión bono) | Bajo | Baja-media (shocks macro) |
| Fed balance sheet / RRP / M2 | FRED (WALCL, RRPONTSYD, M2SL) | Gratis | Desde 2002/2003/1959 (salto M2 en 2020) | Semanal/diaria/mensual | Bajo (ojo al salto de M2) | Media (lag variable 60-90 días) |
| Fear & Greed Index (cripto) | Alternative.me API | Gratis | Desde 2018 | Diaria | Bajo | Baja-media (reactivo) |

---

### Nota final de prudencia

Ninguna de estas señales, por sí sola, ha demostrado en esta investigación poder predictivo robusto, estable y fuera de muestra sobre el retorno futuro de Bitcoin a un horizonte concreto. Lo más defendible con la evidencia disponible es: **(1)** usar las métricas on-chain de valoración (MVRV, NUPL) como mapa de contexto de ciclo de muy largo plazo, no como gatillo de entrada/salida; **(2)** usar funding/OI/long-short como gestión de riesgo de posicionamiento (evitar apalancarse en la misma dirección que una masa ya muy apalancada), no como señal direccional; **(3)** usar el macro (DXY, liquidez, tipos reales) como filtro de régimen que active o desactive otras estrategias, no como predictor de precisión diaria; y **(4)** para cualquier cosa que vaya a downstream a un backtest, resolver primero el problema de point-in-time — de lo contrario, cualquier resultado "prometedor" puede ser simplemente lookahead bias disfrazado de edge.
