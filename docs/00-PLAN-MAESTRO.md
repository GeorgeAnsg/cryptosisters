# CORVUS IV · Plan maestro

**Un bot de trading para Bitcoin, construido desde cero, explicado para que se entienda.**

Fecha: 8 de septiembre de 2026 · Documento vivo: se actualiza aquí, no se reescribe de cero.
Anexos de investigación en `corvus4/investigacion/` (01 a 06), con todas las fuentes.

---

## Cómo leer este documento

Está escrito para que **tú** puedas dar órdenes con criterio. Cada idea lleva: qué es en
lenguaje llano, por qué importa, y qué decisión concreta tomamos.

**La advertencia que gobierna todo lo demás.** Un bot que gana dinero no es un bot que
acierta. Es un bot que (1) tiene una ventaja pequeña y real, (2) no la destruye con costes,
(3) sobrevive a las rachas malas, y (4) no se está engañando a sí mismo con un backtest
bonito. Los puntos 3 y 4 son donde muere casi todo —incluidos tus bots anteriores—, no el 1.
Por eso este plan dedica más espacio al método que a las señales.

---

## 1. El objetivo y las restricciones reales

Un sistema que **emite señales sobre Bitcoin** (extensible a ETH y otras líquidas), que tú
ejecutas a mano en QuantFury desde un aviso de Telegram, y cuya ventaja esté demostrada con
datos que el sistema nunca vio mientras se construía.

| Restricción | Consecuencia de diseño |
|---|---|
| **Ejecución manual** | Pocos avisos al día. Nada de scalping. Las señales deben tolerar minutos de retraso, y ese retraso hay que medirlo. |
| **Máximo 5 posiciones** | Hay que elegir. Y en cripto 5 posiciones no son 5 apuestas: son casi una sola con 5 nombres. |
| **QuantFury: sin comisión, sin coste de apalancamiento, precios reales del libro de Binance/Coinbase** | Ver 1.1 — cambia la estrategia entera. |
| **Tú no programas** | Cada pieza con nombre propio, sitio propio y explicación. Si no puedes decirme "quita el filtro X", el diseño ha fallado. |
| **BTC como activo principal** | Menos ruido, mejor liquidez... y muchos menos datos independientes. Ver sección 3. |

### 1.1 Lo que QuantFury cambia (y casi nadie tiene en cuenta)

Su centro de ayuda es explícito: las operaciones se ejecutan **al precio real del libro de
órdenes de Binance/Coinbase según el tamaño**, sin comisión de compraventa y **sin coste de
apalancamiento ni de mantener la posición abierta**. Eso tiene tres consecuencias enormes:

1. **Tu coste real es cruzar el spread, más tu retraso humano.** Es bajo, pero no es cero, y
   está escondido dentro del precio de ejecución. La única forma seria de conocerlo es
   **medirlo**: comparar tus precios de ejecución contra el punto medio de un exchange grande
   en el mismo instante. Hasta que exista esa medición, el backtest usa una estimación
   pesimista y la dobla.
2. **Mantener una posición abierta días o semanas te sale gratis.** En cualquier exchange de
   perpetuos, aguantar una posición cuesta funding (una tasa de 0,03 % cada 8 h ≈ 33 %
   anualizado). Tú no lo pagas. **Esto favorece de forma decisiva las estrategias lentas
   frente a las rápidas**, y es la mayor ventaja estructural que tienes.
3. **Pero tampoco lo cobras.** No puedes ganar dinero cobrando funding, ni montar
   cash-and-carry (necesitarías spot y perpetuo a la vez en dos sitios). La familia entera de
   "cobrar una prima" está cerrada para ti: el funding te sirve **como información sobre el
   posicionamiento ajeno, no como ingreso**.

Un detalle pendiente de confirmar: existía un artículo de su soporte titulado "Trading Crypto
on a Short Time Interval" cuyo dominio antiguo ya no responde, y no he podido verificar si
sigue vigente alguna regla sobre operaciones muy cortas. **Antes de construir nada por debajo
de 1 h, conviene preguntárselo a su soporte.**

### 1.2 Qué NO vamos a hacer

- **Predecir el precio.** Nadie lo hace de forma fiable.
- **ML como generador principal de señal.** Es donde el bot viejo fingió su ventaja. Entra,
  si acaso, como filtro secundario sobre señales que ya funcionan solas (*meta-labeling*).
- **Optimizar hasta que el backtest brille.** Cada configuración probada quema evidencia
  (sección 3).
- **Operar en 1m/5m.** Incompatible con ejecución manual, y el spread se come la ventaja.
- **Competir en velocidad** en datos macro o noticias: ahí la carrera se gana con colocation
  y FPGA, con presupuestos de cinco o seis cifras al mes. No es una opinión, es la estructura
  del mercado.

---

## 2. La pregunta central: ¿se puede anticipar a Bitcoin?

**Al precio de Bitcoin, no. A tres cosas distintas del precio, sí.** Todo lo que funciona en
trading sistemático cae en una de estas familias:

**Familia 1 · Cobrar una prima por un riesgo que otros no quieren.** Funding, basis, prima de
volatilidad. Es la familia con el mecanismo más sólido, porque alguien paga de verdad por
algo que quiere. **Cerrada para ti por la estructura de QuantFury** (ver 1.1). El funding se
queda como *información*, no como ingreso.

**Familia 2 · Explotar comportamientos que se repiten.** La información se difunde despacio
(las tendencias persisten), el pánico exagera (rebotes tras cascadas de liquidación), las
instituciones operan en horario de oficina (horas y días distintos entre sí), y hay flujos en
fechas conocidas. **Es tu familia principal.** También la que más se sobreajusta.

**Familia 3 · Saber algo antes que los demás.** A escala de segundos pierdes siempre. A
escala de días hay hueco, pero no por saber antes: por **agregar mejor** información pública
tediosa de juntar (flujos de ETF, posicionamiento, reservas). Ahí el bot gana por constancia,
no por velocidad.

**Familia 4 · Gestionar el riesgo mejor que la media.** No es una señal, y produce más dinero
que la mayoría de las señales: tamaño correcto, no operar cuando no hay ventaja, sobrevivir a
los meses malos. Entre dos personas con la misma señal, la diferencia a un año es casi toda
esto. Y un bot lo hace perfecto, que es justo lo que un humano no consigue.

**Orden de construcción, por tanto:** 4 (riesgo) → 2 (comportamiento) → 3 (información
agregada). La familia 1 solo aporta contexto.

---

## 3. El presupuesto de intentos: el hallazgo que condiciona el proyecto

Éste es el número más importante de todo el documento y lo he calculado yo, no lo he copiado.

Si pruebas muchas configuraciones y te quedas con la mejor, esa mejor tiene un Sharpe alto
**aunque ninguna tenga ventaja real** — es el máximo de N muestras de ruido. Bailey y López de
Prado dan la fórmula exacta del Sharpe que cabe esperar por puro azar:

| Configuraciones probadas | Sharpe esperado POR AZAR (con 5 años de datos) |
|---|---|
| 10 | 0,70 |
| **43 (donde estás hoy)** | **0,99** |
| 100 | 1,13 |
| 1.000 | 1,46 |

Y al revés: **con 5 años de datos de desarrollo, el máximo teórico son ~45 configuraciones
independientes** antes de que un Sharpe de 1 sea lo esperable por suerte. Tu `intentos.jsonl`
de corvus3 tiene **43 registrados**.

**Traducción:** el presupuesto está prácticamente agotado. Cualquier idea nueva que dé un
Sharpe alrededor de 1 sobre 2020-2024 es indistinguible de la suerte. Esto no se arregla
probando con más cuidado; solo hay dos salidas, y hay que elegir explícitamente:

- **A · Ampliar la evidencia.** Más historia (BTC desde 2017 en spot, no solo desde 2020 en
  perpetuo de Bybit), más activos independientes, barras más finas donde tenga sentido, y
  medir por **evento de mercado**, no por señal. Cada observación genuinamente independiente
  que añades sube el listón que puedes permitirte.
- **B · Gastar los intentos que quedan solo en hipótesis con evidencia previa fuerte**, en
  vez de explorando a ver qué sale. Explorar es carísimo ahora.

**Decisión propuesta: las dos, en este orden.** Primero A (fase 1 del plan), y hasta que A
esté hecho, solo se prueban ideas del grupo prioritario del catálogo.

### 3.1 La salida A, ya ejecutada esta noche

No hacía falta esperar a la fase 1 para la parte más barata. Descargado y auditado el
8-sept-2026 desde los volcados oficiales de `data.binance.vision`:

| Serie | Velas | Desde | Hasta | Auditoría |
|---|---|---|---|---|
| BTC/USDT spot 1d | 3.302 | **2017-08-17** | 2026-08-31 | limpia: 0 huecos, 0 duplicados |
| BTC/USDT spot 4h | 19.794 | 2017-08-17 | 2026-08-31 | 9 huecos, **todos anteriores a 2019** (caídas de Binance en sus inicios) |
| BTC/USDT spot 1h / 15m | — | 2017-08 | 2026-08 | descargando |

**El efecto sobre el presupuesto de intentos es enorme:**

| Histórico disponible | Techo de configuraciones independientes |
|---|---|
| 5 años (2020-2024, perpetuo de Bybit) | **45** ← donde estabas, con 43 gastados |
| 7 años | 139 |
| **9 años (2017-2026, spot de Binance)** | **420** |

Pasar de 5 a 9 años de histórico multiplica por **nueve** el número de ideas que puedes
permitirte probar antes de que el resultado sea indistinguible de la suerte. Una descarga de
diez minutos ha hecho más por la viabilidad del proyecto que cualquier indicador nuevo.

Dos avisos para no malinterpretarlo:
- **El techo sube, no se reinicia.** Los 43 intentos siguen contando; lo que cambia es que
  ahora caben muchos más.
- **2017-2019 es otro Bitcoin.** Sirve para tener más muestra y más regímenes distintos (un
  bajista completo en 2018 que no está en tu tramo actual), pero la regla 8 sigue mandando:
  lo reciente pesa más, y una señal que solo funciona en 2017-2018 es una foto vieja.

---

## 4. Lo que ya sabemos que NO funciona

42 intentos con datos reales. Empezar de cero **no es volver a probar lo descartado**.

| Señal | Veredicto | Mecanismo del fallo |
|---|---|---|
| MACD, ADX+DI, EMA (9/21/50, 200, diaria), Supertrend, rotura de 20 y 100 velas, impulso >1,5×ATR | Descartados | **Confirmar una tendencia es llegar tarde** |
| RSI puro, envolvente, 3 velas del mismo color | Descartados | Sin ventaja / trampa de win-rate |
| VWAP simple, Volume Profile POC, estructura de mercado simple | Descartados | Estado demasiado persistente |
| Fear & Greed extremo, DVOL extremo | Descartados | **7–11 episodios independientes en 5 años**: no hay muestra |
| Filtro macro-calendario (FOMC/CPI/NFP) | Descartado | −10 a −15 % en el bot viejo |
| Bollinger banda inferior (`bb_extremo`) | **Cayó en backtest real** tras pasar 4 pruebas | El cribado a horizonte fijo no representa la salida real |
| ML como señal principal | Descartado | Donde el bot viejo fingió su ventaja |

Y a esto, la investigación de hoy añade descartes **antes de gastar un solo intento**:

| Idea | Por qué se descarta de entrada | Fuente |
|---|---|---|
| **Fair Value Gap (FVG)** | Backtest publicado con resultado **negativo** | anexo 06 §1.1 |
| **Max pain de opciones** | Refutado: la predictibilidad se explica por reversión, no por "imán" | anexo 02 §4.6, 04 §7 |
| **Gap del CME** | **Estructuralmente muerto**: CME opera 24/7 desde el 29-may-2026 | verificado hoy |
| **Halving como timing** | n = 4. No hay inferencia posible | anexo 04 §6.5 |
| **Grid puro** | Fallo estructural documentado en mercados con tendencia | anexo 02 §9.2 |
| **Order book imbalance como señal** | Efecto real pero **sub-económico** tras costes; terreno de HFT | anexo 04 §4.1 |
| **Puntuar noticias históricas con un LLM** | El modelo **ya sabe** lo que pasó después: el backtest está contaminado | anexo 04 §2.2 |
| **Sentimiento de Reddit** | Evidencia contradictoria entre estudios serios | anexo 04 §7 |
| **Cash-and-carry, pairs trading con financiación** | Requiere spot + perpetuo simultáneos; no ejecutable en tu setup | anexo 02 §5.2 |
| **Datos institucionales (Kaiko L2, The Tie)** | 1.000–2.500 $/mes. No se justifica | anexo 04 §7 |

### 4.1 Los cinco mecanismos que explican casi todos los fallos

1. **Confirmar es llegar tarde.** Cualquier indicador que necesita recorrido previo dispara
   cuando el movimiento ya pasó.
2. **En cripto, contar señales miente.** 30 monedas con la misma señal el mismo día son *un*
   evento contado 30 veces. Al colapsar por evento, tres conclusiones se dieron la vuelta.
3. **Los eventos raros no dan muestra.** Un extremo que ocurre 8 veces en 5 años no sostiene
   una regla. (MVRV Z > 7: **2 veces en la historia**. NUPL > 0,75: 3-4 veces.)
4. **Un cribado barato solo sirve para descartar.** La fricción real solo puede restar.
5. **Lo publicado se agota.** Una estrategia de sentimiento medida antes y después de hacerse
   popular cayó de +2,24 % a +0,88 %. Toda señal conocida tiene vida media.

---

## 5. El método: las puertas que toda idea debe cruzar

Se heredan las 4 de corvus3 y se añaden 2 que salen de la investigación de hoy.

| # | Puerta | Qué comprueba | Estado |
|---|---|---|---|
| 1 | **Causalidad** | Ningún indicador mira al futuro: calcular sobre las primeras *t* velas da lo mismo que calcular sobre todo y quedarse con *t* filas | Ya la tienes + automatizable con `freqtrade lookahead-analysis` |
| 2 | **Paridad** | Backtest y vivo son el mismo código | Ya la tienes |
| 3 | **Costes** | Sobrevive al **doble** del coste estimado (spread real + retraso humano) | Ya la tienes; el coste pasa de estimado a **medido** (§8) |
| 4 | **Intentos (DSR)** | Corrige el Sharpe por cuántas configuraciones se probaron | Ya la tienes — y el presupuesto está casi agotado (§3) |
| 5 | **Recursividad / calentamiento** | EMA, RSI, ADX, ATR **no dan el mismo valor** con 500 velas que con 5.000; en vivo solo tienes un trozo | **NUEVA** — `freqtrade recursive-analysis` |
| 6 | **Riesgo de cartera** | Ninguna operación se juzga sola: exposición total y correlación con lo ya abierto | **NUEVA** — inspirada en el `risk_overlay` de pysystemtrade |

**Partición de datos** (heredada, no se resetea):

| Tramo | Periodo | Cuántas veces se mira |
|---|---|---|
| Desarrollo | 2020-01 → 2024-12 | sin límite |
| Validación | 2025-01 → 2025-12 | pocas, registradas (ya van 5; el límite propio era 2-3) |
| **Reserva final** | 2026-01 → hoy | **una sola vez, al final** |

Y la regla que más veces ha salvado el proyecto: **lo reciente pesa más**. Una señal que
promedia bien porque fue buena en 2020-21 y falla desde 2023 es una foto vieja.

**El protocolo completo de validación** (32 pasos, del pre-registro al dinero real) está en
`investigacion/05-metodologia-validacion.md` §10. Los tres pasos que más se saltan:
- Registrar **todos** los intentos, incluidos los descartados: sin ese número, la Puerta 4 no
  existe.
- Ejecutar el stop/objetivo contra el **máximo y mínimo de la vela**, no contra el cierre.
- Si el holdout falla, **la estrategia se descarta o se rediseña desde cero**. Nunca se
  reutiliza el mismo holdout tras un ajuste.

---

## 6. La arquitectura: qué carpeta hace qué

Cadena de montaje donde cada pieza hace una sola cosa y no sabe nada de las demás. Confirmado
por el mejor sistema abierto que existe (`pysystemtrade`, revisado hoy).

```
corvus4/
├── datos/         Todo lo que entra: precio, funding, flujos, macro. Con procedencia y fecha.
├── motores/       ALFA. Histórico → candidatos con un pronóstico. No sabe de filtros ni riesgo.
├── filtros/       RIESGO POR OPERACIÓN. Contexto → permitido / vetado.
├── tamano/        CUÁNTO. Pronóstico + volatilidad + capital → tamaño.
├── salidas/       CUÁNDO CERRAR. Objetivo, stop, tiempo máximo, trailing.
├── cartera/       RIESGO GLOBAL + ÁRBITRO. Qué señales se toman y cuánto riesgo total se abre.
├── ejecucion/     Freqtrade IStrategy + aviso de Telegram + registro de lo ejecutado de verdad.
├── laboratorio/   Cribados y experimentos. AISLADO: nadie importa nada de aquí.
├── tests/         Las 6 puertas.
├── docs/          Este documento, pre-registros, bitácora.
└── registro/      intentos.jsonl · accesos a validación · señales emitidas vs ejecutadas
```

**Tres capas nuevas respecto a corvus3:** `datos/` (los datos dejan de vivir dentro de
Freqtrade y ganan reglas propias), `cartera/` (el árbitro pendiente + el riesgo global), y
`ejecucion/` (el puente de Telegram, que hoy no existe y **es la mitad del sistema**).

**Dos reglas de arquitectura, no negociables:**
1. Ninguna capa importa código de otra salvo por su interfaz (candidato → pronóstico;
   contexto → permitido/vetado).
2. **`laboratorio/` no se puede importar desde ninguna parte.** Lo que se demuestre ahí se
   *reescribe* en su capa. Ese salto es justo por donde se coló `bb_extremo`.

### 6.1 El árbitro, resuelto

Descubriste que la "fuerza" no correlaciona con el resultado (−0,050 y 0,034; el cuartil más
fuerte es el peor) y concluiste que no sirve para elegir. Correcto. Lo que faltaba:

> **La fuerza nunca debió usarse para elegir. Se usa para decidir el tamaño** — y antes hay
> que *escalarla* (que su valor absoluto medio sea constante, comparable entre motores) y
> *taparla* (un máximo, para que una señal extrema no se coma la cartera).

Eran dos preguntas fundidas en una:
- *¿Cuál tomo?* → prioridad fija por calidad demostrada del motor. Sin criterio mejor que el
  azar, repartir es tan bueno como elegir (ya lo comprobaste: 5 huecos vs 1 no cambia el
  signo, solo la varianza).
- *¿Cuánto pongo?* → pronóstico escalado × volatilidad objetivo × capital.

Y una tercera pieza: **banda muerta**. No se reajusta una posición por cambios pequeños del
pronóstico, solo cuando sale de una banda. En ejecución manual es la diferencia entre 3
avisos al día y 40.

---

## 7. El catálogo: todo lo que se puede probar, ordenado por capa

Cada ficha: **qué es** · **por qué podría funcionar** · **evidencia** · **coste de probarlo**.
La columna que manda es la evidencia, porque el presupuesto de intentos está casi agotado (§3).

Los símbolos: 🟢 evidencia publicada razonable · 🟡 mecanismo creíble sin evidencia ·
🔴 evidencia en contra o muestra insuficiente · ⚙️ ya construido y validado por ti.

### 7.1 `datos/` — qué descargar, y en qué orden

**Nivel 1 · Gratis, timestamp fiable, empezar por aquí**

| Dato | Fuente | Histórico | Notas |
|---|---|---|---|
| OHLCV BTC/ETH 15m-1h-4h-1d | Bybit (ya lo tienes) + `data.binance.vision` | Bybit perp desde 2020; **Binance spot desde 2017** | Bajar spot de Binance **añade 3 años** de historia: es la vía más barata de ampliar el presupuesto de intentos (§3) |
| Funding rate | Bybit (ya lo tienes) + Binance API | desde 2019 paginando | Como **señal de posicionamiento**, no como ingreso |
| Trades públicos (tick) | Freqtrade `download-data --dl-trades` | según exchange | Habilita CVD/footprint **dentro del mismo framework**, sin romper paridad |
| DXY, US10Y, TIPS reales, oro | FRED (ya lo tienes) | décadas | Solo horario de sesión: ojo al fin de semana |
| DVOL (volatilidad implícita) | Deribit (ya lo tienes) | desde mar-2021 | |
| Fear & Greed | alternative.me | desde 2018 | Descartado como señal; vale como variable de contexto |
| Hashrate, comisiones, direcciones | mempool.space, Blockchain.com | desde 2009 | Gratis y sin revisiones |
| Suministro de stablecoins | DefiLlama | desde 2014 | Señal diluida desde 2025 (pagos, tesorería) |

**Nivel 2 · Gratis, diario, alta prioridad**

| Dato | Fuente | Histórico | Por qué importa |
|---|---|---|---|
| **Flujos de ETF spot de BTC** | Farside Investors | desde ene-2024 | **La señal de "dinero real" más limpia y barata que existe**: ~53,7 pb de movimiento por cada 100 M$ de flujo neto, **sin reversión posterior**. Solo 2,5 años de historia |
| COT del CME | CFTC | desde 2017 | Semanal, 3 días de retraso. Contexto, no timing |

**Nivel 3 · ⚠️ HAY QUE EMPEZAR A GUARDARLO HOY**

| Dato | Problema |
|---|---|
| **Open Interest** | Las APIs de exchange **solo dan 30 días**. Si no se guarda a diario desde hoy, el histórico no existe — y comprarlo cuesta dinero |
| **Long/short ratio** | Igual |
| **Liquidaciones** | Igual, y las fuentes agregadas (CoinGlass) son **estimaciones**, no datos verificados |

Esto es una tarea de fase 1 con carácter urgente: **cada día que pasa sin recolectar es un día
de histórico que se pierde para siempre.**

**Nivel 4 · De pago — decisión consciente de NO comprar**
Glassnode / CryptoQuant (on-chain con revisión retroactiva), Kaiko L2 (1.000-2.500 $/mes).
No se compran: el coste no se justifica y las métricas on-chain de valoración sirven de mapa
de ciclo, no de disparador.

**Cuatro reglas del almacén** (detalle en anexo 03 §6):
1. Lo crudo se guarda tal cual y **no se toca nunca**; las correcciones generan archivo nuevo.
2. Parquet/feather, no CSV, para lo grande.
3. Todo en UTC; una vela con marca `t` y duración `d` **solo puede influir a partir de t+d**.
4. Para las series que el proveedor **revisa a posteriori** (on-chain, macro), guardar *cuándo
   se supo* cada valor, no solo a qué fecha se refiere. Si no, el backtest usa el futuro.

### 7.2 `motores/` — la capa de alfa (candidatos de entrada)

**Grupo prioritario — los únicos donde yo gastaría intentos ahora**

| | Motor | Qué es | Por qué podría funcionar | Evidencia |
|---|---|---|---|---|
| M1 | **Momentum de 20-50 días en BTC diario, con salida por ATR** | Comprar cuando BTC marca máximo de N días; salir por trailing ATR, no por horizonte fijo | Es la familia con más evidencia académica de la historia, y **la salida dinámica es justo lo que no probaste** | 🟢 La pata "MAX" sobrevive fuera de muestra 2022-2024; la de mínimos se degrada |
| M2 | **Reversión tras cascada de liquidaciones / funding extremo negativo** | Funding en percentil extremo negativo + caída violenta → largo contrarian | Mecanismo real: apalancamiento forzado a cerrar, no opinión | 🟡 Mecanismo sólido, evidencia sistemática escasa (marzo-2020 es *un* evento) |
| M3 | **CVD / absorción (flujo de órdenes)** | Volumen agresivo comprador − vendedor acumulado; divergencia precio-delta | **El único candidato que mide flujo real** en vez de geometría de velas. Freqtrade lo soporta con trades públicos gratis | 🟡 Sin paper que lo cuantifique, pero el mejor mecanismo microestructural del catálogo |
| M4 | **StochRSI + ADX** | Las 3 variantes de tu catálogo | **Tu propio candidato más fuerte**, ya cribado con corrección por evento y por concentración | ⚙️🟢 Pendiente solo de Puertas 3 y 4 |

**Grupo secundario — plausibles, con mecanismo, sin evidencia publicada**

| | Motor | Definición operativa | Evidencia |
|---|---|---|---|
| M5 | Barrido de liquidez + reversión | Mecha que supera el máximo/mínimo del día anterior y **cierra dentro** en ≤N velas | 🟡 La menos mala de todo el universo ICT: señal pequeña y consistente frente al azar, sin significancia formal |
| M6 | AVWAP anclado a evento | VWAP desde un suelo/techo concreto, como coste medio agregado de quien entró ahí | 🟡 Mecanismo claro, divulgador no comercial, sin backtest público |
| M7 | Spring de Wyckoff | Rotura del mínimo de un rango lateral + recuperación rápida al interior | 🟡 El único trozo programable de Wyckoff |
| M8 | Divergencia alcista de RSI | Ya cribada por ti | ⚙️🟡 +0,205 % vs +0,064 % de referencia, n=20.652. Solo el lado alcista |
| M9 | Opening Range de sesión | Rango de los primeros K minutos tras la apertura de Londres/NY; rotura y reversión | 🟡 Antecedente clásico fuera de cripto; sin campana real el efecto puede ser más débil |
| M10 | Hammer con filtro RSI | Ya cribado por ti | ⚙️🟡 Modesto pero consistente (+0,90 pp por evento) |
| M11 | LVN como zona de aceleración | Zonas de bajo volumen del perfil como tramos rápidos (no como imán) | 🟡 Distinto del POC que ya descartaste |

**Grupo de descarte anticipado** (se listan para dejar constancia de que se miraron):
Fair Value Gap 🔴 (backtest publicado negativo), Order Blocks 🔴 (evidencia débil),
OTE/Fibonacci 🔴, Judas Swing / Silver Bullet 🔴 (folclore sin test), retesteo clásico de
rotura 🔴 (mismo "llegar tarde" que ya descartaste), gap del CME 🔴 (muerto desde
mayo-2026), max pain 🔴.

### 7.3 `filtros/` — riesgo por operación (contexto → permitido / vetado)

| | Filtro | Qué hace | Estado |
|---|---|---|---|
| F1 | Régimen BTC (MA200) | Veta compras en régimen bajista | ⚙️ construido |
| F2 | Sesión / fin de semana | Fin de semana: la mitad de volatilidad y ventaja mucho menor | ⚙️ construido y confirmado |
| F3 | Funding extremo | Mejora el canal (Sharpe 0,71→0,94); empeora el doble suelo | ⚙️ construido, aplicado solo donde ayuda |
| F4 | DXY / bonos reales + oro | Ayuda al doble suelo, no al canal | ⚙️ construido |
| F5 | **Régimen de volatilidad (percentil de ATR)** | No operar en los extremos de volatilidad | 🟢 Evidencia de que mejora sistemas de ruptura |
| F6 | **Perfil horario** | Permitir operar solo en las horas con actividad institucional real | 🟡 Trivial de medir con tus propios datos. **La hipótesis más barata del catálogo** |
| F7 | **Flujo de ETF como régimen** | Reducir/ampliar exposición según el flujo neto de la semana | 🟢 Impacto medido, sin reversión. Solo desde 2024 |
| F8 | **MVRV-Z como interruptor de ciclo** | Apagar compras en euforia extrema | 🟡 Sharpe 0,45→1,28 en un estudio, **pero solo 3 ciclos y el extremo ha ocurrido 2 veces** |
| F9 | Ventana de evento macro | **Reducir el tamaño**, nunca tomar dirección, alrededor de CPI/FOMC | 🔴 como señal direccional (n≈9) · 🟢 como reductor de riesgo |
| F10 | Veto por datos rotos | Si los datos llegan con huecos o desfasados, no se emite señal | Higiene, no opinión |

### 7.4 `tamano/` — cuánto apostar

| | Pieza | Qué hace | Nota |
|---|---|---|---|
| T1 | Vol-targeting | Menos dinero cuando el mercado se mueve mucho | ⚙️ construido |
| T2 | **Pronóstico escalado y con tope** | Normaliza la "fuerza" de cada motor a una escala común y la tapa | La solución al problema del árbitro (§6.1) |
| T3 | Kelly fraccional (¼) | Kelly completo arruina; los fondos serios usan ~0,4× | 🟢 |
| T4 | **Reducción por correlación** | Si ya hay 3 largos en cripto, el cuarto pesa menos | En cripto, correlación 0,7-0,9 **por defecto** salvo prueba en contra |
| T5 | **Banda muerta** | No reajustar por cambios pequeños | Reduce coste y reduce avisos. Clave en ejecución manual |

### 7.5 `salidas/` — cuándo cerrar

| | Pieza | Nota |
|---|---|---|
| S1 | Objetivo fijo + stop | ⚙️ construido. Usar `minimal_roi`/`stoploss` nativos, no `custom_exit`, salvo necesidad real (el bug que ya cazaste) |
| S2 | **Trailing por ATR (Chandelier)** | Favorece sistemas de tendencia; perjudica los de rango |
| S3 | Salida por tiempo máximo | Si la tesis no se cumple en N velas, fuera |
| S4 | **El experimento de salidas** | Comparar la MISMA entrada con: objetivo fijo · trailing ATR · parcial+trailing. **La literatura se contradice; tu backtest lo zanja mejor que cualquier fuente** |

### 7.6 `cartera/` — árbitro y riesgo global

| | Pieza | Qué hace |
|---|---|---|
| C1 | Prioridad fija por calidad demostrada | Nada de competir por "fuerza" |
| C2 | **Multiplicador global de riesgo (0 a 1)** | Toma el más conservador de: riesgo esperado alto, shock de correlación, volatilidad saltarina. Reduce **todas** las posiciones a la vez |
| C3 | Límite de exposición correlacionada | 5 largos en cripto = 1 apuesta |
| C4 | Límite diario de pérdidas + interruptor | Defensivo. Es la ventaja estructural del bot sobre un humano |

---

## 8. La operación real (la parte que ningún tutorial cuenta)

Tú no ejecutas automático. El backtest supone ejecución instantánea; tú tardas minutos, o
duermes. Eso hay que construirlo desde el principio, no parchearlo después.

1. **El aviso lo lleva todo**: par, dirección, precio de referencia, **tamaño exacto**, stop,
   objetivo, motivo (qué motor, qué filtros pasó) e identificador.
2. **Caducidad explícita**: "válido hasta las 14:00, o si el precio pasa de X". Entrar seis
   horas tarde a una señal de 4 h **no es la operación que se backtesteó**.
3. **Registro de lo emitido vs lo ejecutado**: respondes con el precio real de entrada, o "no
   ejecutada". Con eso se calculan tres números que hoy no existen en ninguna parte:
   - tu **slippage humano real** (el coste verdadero de la Puerta 3),
   - tu **tasa de ejecución** (cuántas señales se te escapan),
   - y si las que se escapan eran mejores o peores que las que coges.
4. **Interruptores**: máximo de posiciones, máximo de pérdida diaria, y veto global si los
   datos llegan rotos. **Mejor no avisar que avisar con datos malos.**
5. **Vigilancia de salud**: alarma si el bot lleva demasiado tiempo callado o emite mucho más
   de lo normal. El silencio por avería se parece demasiado al silencio por falta de señal.

---

## 9. El plan por fases

Cada fase tiene criterio de salida. La tentación es saltar a "probar ideas"; las fases 0-2
son las que hacen que las ideas de la fase 4 signifiquen algo.

### Fase 0 · Fundación
Repo nuevo con la estructura de §6, git desde el minuto uno, las **6 puertas implementadas
antes que ninguna estrategia**, `registro/intentos.jsonl` heredando la cuenta de 43, y la
partición de datos heredada sin resetear.
**Salida:** los tests pasan **y** puedo demostrar cada puerta con un caso que falla a
propósito. *Una puerta que nunca ha dicho que no, no está comprobada.*

### Fase 1 · Datos y coste real ← *la fase que amplía el presupuesto de intentos*
- **Recolector diario de OI y long/short desde el primer día** (lo que no se guarde hoy, se
  pierde).
- BTC spot de Binance desde 2017 (3 años más de historia).
- Funding de Binance con histórico completo.
- Trades públicos para CVD en el tramo que se vaya a usar.
- Flujos de ETF (Farside) y COT (CFTC).
- Auditoría de huecos y duplicados que **falle ruidosamente**.
- Medición del coste: spread del libro por tamaño.
**Salida:** una función `coste(par, tamaño, momento)` que usa todo backtest, y un informe de
calidad de datos sin huecos silenciosos.

### Fase 2 · Riesgo y tamaño ← *la fase que más dinero produce*
Vol-targeting, límite de exposición correlacionada, multiplicador global de riesgo, banda
muerta.
**Salida:** con una señal deliberadamente mediocre (comprar y mantener), la gestión de riesgo
ya mejora el Calmar frente a comprar y mantener a pelo.

### Fase 3 · El experimento de salidas
Sobre la señal que ya tienes validada (canal o doble suelo), comparar objetivo fijo vs
trailing ATR vs parcial. Es barato, no consume presupuesto de exploración (es la misma
entrada) y afecta a **todos** los motores futuros.

### Fase 4 · Motores del grupo prioritario, de uno en uno
M1 → M4 → M3 → M2, con las 6 puertas completas y el colapso por evento obligatorio.
**Salida por motor:** pasa las 6 puertas en Desarrollo y **aguanta 2023-2024 por sí solo**.

### Fase 5 · Contexto e información agregada
F7 (flujos de ETF), F5 (régimen de volatilidad), F6 (perfil horario), F8 (ciclo).

### Fase 6 · Dry-run, 3 meses mínimo, sin excepción
El bot emite, tú registras, nadie pone dinero. Aquí se mide el slippage humano real.
**Salida:** la diferencia entre lo simulado y lo registrado es **explicable**. Si no lo es, no
se pasa a dinero real: se investiga.

### Fase 7 · Dinero real, pequeño
Con el examen de 2026 mirado **una sola vez**, justo antes.

---

## 10. Decisiones — cerradas el 8-sept-2026

1. **Repo:** `~/Desktop/corvus4`.
2. **Universo:** solo BTC para construir y ajustar. ETH se guarda sellado, sin mirarlo, como
   prueba independiente para el final — la misma lógica que la reserva temporal de 2026.
3. **Largos y cortos.** QuantFury permite las dos direcciones a la vez en monedas distintas.
   Esto **duplica el catálogo utilizable** (la mitad de las ideas de reversión — comprar
   caídas — solo servían en largo) pero también duplica el riesgo de ejecución manual: cada
   motor necesita su versión corta explícita, testeada por separado, nunca asumida por
   simetría. Un motor que funciona en largo no funciona igual en corto — los mecanismos de
   "confirmar tarde" y de sincronización entre monedas no son simétricos entre subida y
   bajada, y hay que comprobarlo, no darlo por hecho.
4. **Riesgo:** 1 % del capital por operación, 3-4 % de pérdida máxima diaria (interruptor).
   Es el estándar habitual en trading sistemático con capital propio; se revisa con el uso y
   con lo que salga del dry-run (Fase 6).
5. **Los 43 intentos: se heredan enteros para el presupuesto, y se re-verifican uno a uno.**
   Ver §10.1 — es la decisión más importante de las cinco.

### 10.1 Por qué no basta con "confiar" o "descartar" los 43 — y qué se hace en su lugar

El usuario planteó algo correcto y que ya ha ocurrido más de una vez: parte de los 43
intentos registrados pudo tener fallos de metodología (el bug de resample de 4h que etiquetaba
la vela con la hora de inicio es el ejemplo real). Confiar en el veredicto a ciegas es
peligroso. Pero **descartar el número también lo es**, porque el presupuesto de intentos
(§3) mide cuántas veces se ha mirado el mismo bloque de datos — eso no se borra aunque la
conclusión que sacaste de esa mirada fuera errónea. El dato ya está gastado.

La solución es separar dos cosas que se estaban confundiendo en una:

- **El número 43 se queda igual para el cálculo del Sharpe desinflado.** No se reinicia.
- **Pero cada uno de los 43 se re-verifica, uno a uno, con el pipeline nuevo** — las 6
  puertas completas, incluidas las dos nuevas (recursividad, riesgo de cartera) — antes de
  dar su veredicto original por bueno.

**Regla de contabilidad para la re-verificación** (para que no se infle el presupuesto sin
querer):
- Si al re-verificar se descubre que el veredicto original estaba mal **por un bug de
  metodología** (causalidad rota, evento mal colapsado, coste omitido) → se corrige el
  mismo registro en `intentos.jsonl`, con una nota de qué bug tenía y la fecha de la
  corrección. **No cuenta como un intento nuevo**: es arreglar la medición de la misma
  pregunta, no hacer una pregunta distinta.
- Si al re-verificar surge la tentación de probar una variante genuinamente distinta
  (otro umbral, otro filtro) → **eso sí es un intento nuevo**, se registra como tal, y se
  resiste la tentación de colarlo como "parte de la re-verificación".

**Esto se convierte en el contenido real de la Fase 0-1**, no en un trabajo aparte: las 6
puertas no se construyen en abstracto, se construyen **contra el primer caso real que hay
que re-auditar**. Orden propuesto, de más a menos urgente:

1. **StochRSI + ADX** (tu candidato más fuerte, con las 3 variantes) — le faltaban ya las
   Puertas 3 y 4 antes de esta noche; es el caso natural para estrenar el pipeline completo.
2. **Canal (Donchian) y Doble suelo** — ya "validados en producción de facto" en corvus3,
   pero nunca pasaron por `recursive-analysis` ni por la Puerta 6 (riesgo de cartera). Antes
   de heredarlos como buenos, re-verificarlos con las puertas que no existían cuando se
   aprobaron.
3. El resto del catálogo de corvus3 (`docs/catalogo_bot_viejo.md`), en el orden en que están
   marcados como "candidato fuerte" o "pendiente".
4. Solo cuando el catálogo heredado esté re-auditado, se abren los motores nuevos de §7.2
   (M1-M4) — que sí consumen presupuesto nuevo de verdad.

Sí, esto lleva tiempo. Es exactamente el tipo de lentitud que las puertas existen para
imponer, y es más barato hacerlo ahora, uno a uno, que descubrir el bug número tres dentro de
seis meses con dinero real puesto.

---

## 11. Glosario mínimo

| Término | En cristiano |
|---|---|
| **Backtest** | Simular la estrategia sobre el pasado. Fácil de falsear sin querer. |
| **Dry-run** | El bot funciona en tiempo real con dinero falso. |
| **Lookahead** | Usar sin darte cuenta información que en ese momento no existía. El error más caro. |
| **Sharpe** | Rentabilidad dividida por cuánto se mueve el resultado: cuánto ganas por cada susto. |
| **Sharpe desinflado (DSR)** | El Sharpe corregido por cuántas cosas probaste antes. |
| **Drawdown** | Cuánto has caído desde tu máximo. Lo que de verdad duele. |
| **Slippage** | Diferencia entre el precio que esperabas y el que te dieron. |
| **Spread** | Diferencia entre comprar y vender. Tu coste real en QuantFury. |
| **Funding** | Pago periódico entre largos y cortos en perpetuos. Tú ni lo pagas ni lo cobras: lo usas como información. |
| **Open Interest** | Contratos abiertos. Mide cuánto apalancamiento hay en el sistema. |
| **CVD** | Volumen agresivo comprador menos vendedor, acumulado. Mide quién empuja de verdad. |
| **On-chain** | Datos de la cadena de Bitcoin (movimientos de monedas), no precios. |
| **Régimen** | El estado del mercado (alcista/bajista, tranquilo/volátil). |
| **Vol-targeting** | Poner menos dinero cuando el mercado se mueve mucho, para que el riesgo sea constante. |
| **Kelly** | Fórmula del tamaño óptimo. El completo arruina; se usa una fracción. |
| **Walk-forward** | Ajustar con un trozo de historia y comprobar con el siguiente, avanzando. |
| **Meta-labeling** | Usar ML no para decidir si comprar, sino para filtrar qué señales ya generadas merecen la pena. |
| **Pronóstico** | Número continuo de convicción. Sirve para el **tamaño**, no para elegir entre señales. |
| **Point-in-time** | Guardar no solo el valor de un dato, sino **cuándo se supo**. |

---

## 12. Los anexos

| Anexo | Contenido |
|---|---|
| `investigacion/01-frameworks-arquitectura.md` | Frameworks comparados con los repos descargados y leídos; estructura de carpetas; capa de datos; ejecución manual; recomendación de stack |
| `investigacion/02-estrategias-btc.md` | Estrategias públicas con reglas exactas, resultados, periodo y críticas; papers; repos por credibilidad; ranking de 17 hipótesis |
| `investigacion/03-datos-btc.md` | Todas las fuentes de datos (precio, derivados, on-chain, macro) con histórico, latencia, coste y riesgo de lookahead; tabla de 28 filas |
| `investigacion/04-noticias-sentimiento-flujo.md` | Noticias, LLM y su trampa de lookahead, sentimiento social, flujo de órdenes, flujos de ETF, eventos programados, y lo que no funciona |
| `investigacion/05-metodologia-validacion.md` | DSR, PBO, walk-forward, CPCV, etiquetado, regímenes, Kelly, costes, métricas, y el protocolo de 32 pasos |
| `investigacion/06-traders-discrecional.md` | ICT, Wyckoff, price action, volumen, sesiones, gestión de riesgo de traders reales, con veredicto de evidencia uno a uno |
| `investigacion/repos/` | 12 repos descargados y leídos (2 GB). Se pueden borrar cuando terminemos con ellos |

**Nada de lo descargado se ha ejecutado.** Todo se ha leído.
