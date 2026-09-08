# 01 · Frameworks, arquitectura e infraestructura

**Fecha:** 8 de septiembre de 2026
**Método:** repositorios reales descargados (`git clone --depth 1`) y **leídos**, nunca ejecutados.
Todo lo que se afirma aquí sobre un repo está comprobado en su código o en su documentación
descargada, no de memoria. Cuando algo es opinión, lo digo.

---

## 0. Qué hay descargado y revisado

Están en `corvus4/investigacion/repos/` (2,0 GB en total; se pueden borrar cuando
terminemos de leerlos — no hacen falta para que el bot funcione).

| Repo | Qué es | Último commit | Tamaño |
|---|---|---|---|
| `freqtrade` | El motor de bots cripto más usado en Python | **2026-09-07** | 103 MB |
| `freqtrade-strategies` | Estrategias de ejemplo oficiales | 2026-08-12 | 0,8 MB |
| `NostalgiaForInfinity` | La estrategia comunitaria más famosa de Freqtrade | **2026-09-07** | 21 MB |
| `jesse` | Framework alternativo de bots cripto | 2026-09-04 | 126 MB |
| `nautilus_trader` | Plataforma profesional event-driven (núcleo en Rust) | **2026-09-07** | 149 MB |
| `vectorbt` | Backtesting vectorizado ultrarrápido | 2026-08-02 | 186 MB |
| `backtesting.py` | Backtester minimalista | 2026-08-05 | 6 MB |
| `OctoBot` | Bot cripto con interfaz web | 2026-08-10 | 112 MB |
| `qlib` (Microsoft) | Plataforma de investigación cuantitativa con IA | 2026-07-23 | 14 MB |
| `pysystemtrade` (Rob Carver) | Sistema de futuros gestionados, referencia de arquitectura | 2026-07-18 | 880 MB |
| `mlfinlab` | Implementación del libro de López de Prado | **2021-12-01 (muerto)** | 3 MB |
| `ml4t` | Código del libro *Machine Learning for Trading* | 2026-09-07 | 402 MB |

**Primer dato duro:** `mlfinlab` (el que implementa las técnicas anti-sobreajuste de
López de Prado) lleva **sin tocarse desde diciembre de 2021** — el repo público quedó como
escaparate de la versión comercial. No se puede depender de él: las funciones que
necesitemos (validación con purga, etiquetado de triple barrera, Sharpe desinflado) hay que
escribirlas nosotros. Son entre 30 y 80 líneas cada una; no es un problema, pero conviene
saberlo antes de planificar.

---

## 1. La distinción que hay que entender antes de elegir nada

### Motor vectorizado vs. motor por eventos

**Vectorizado** (`vectorbt`, `backtesting.py` en parte, casi todo lo que hace la gente en
un notebook): calcula todo el histórico de golpe, como una hoja de cálculo gigante. Columna
de precios → columna de RSI → columna de "compra sí/no" → resultado. Es **rapidísimo**
(millones de combinaciones en minutos) y por eso es ideal para *cribar* ideas.

Su problema es estructural, y es exactamente el que ya te mordió: **cuando todo el histórico
está en memoria a la vez, mirar al futuro es trivial y silencioso.** Escribes
`df['maximo'] = df['high'].max()` y acabas de usar el máximo de 2026 para decidir una compra
de 2021. Nada falla, nada avisa, y el backtest sale precioso.

**Por eventos** (`freqtrade`, `nautilus_trader`, `jesse`): simula el paso del tiempo vela a
vela. En cada momento el código solo ve lo que existía hasta ese momento. Es mucho más lento
pero **es la única forma de que el backtest y el bot en vivo sean el mismo código**.

**Conclusión operativa (y es la misma regla de método que ya tienes):** el vectorizado sirve
para *descartar*, el de eventos para *confirmar*. Es la misma lección de la regla 10 de
corvus3 (`bb_extremo` pasó el cribado y perdió dinero en el backtest real), pero aplicada a
la elección de herramienta.

---

## 2. Ficha de cada framework

### Freqtrade — 2026.9 (versión leída en el repo: `__version__ = "2026.9-dev"`)

**Qué es:** el estándar de facto para bots cripto en Python. Motor por eventos, backtest,
dry-run (simulación en vivo con datos reales y dinero falso) y vivo con el **mismo código**.

**Módulos que trae** (leídos en `freqtrade/freqtrade/`): `data`, `exchange`, `optimize`
(backtest + hyperopt), `persistence` (base de datos de operaciones), `plugins` (protecciones,
listas de pares), `rpc` (Telegram, API REST, webhooks), `strategy`, `freqai` (capa de machine
learning), `leverage`, `wallets`.

**Tres cosas que trae y que valen oro para tu método** — no las tenías identificadas y tapan
agujeros reales:

1. **`freqtrade lookahead-analysis`** (`docs/lookahead-analysis.md`). Automatiza tu Puerta 1.
   No lee tu código: corre un backtest completo como referencia y luego lo vuelve a correr
   recortando el histórico, señal por señal, y compara. Si un indicador cambia de valor o una
   entrada se mueve, es que estaba mirando al futuro. Cita textual de la doc: el backtest
   *"inicializa todos los timestamps (carga el dataframe entero en memoria) y calcula todos
   los indicadores de golpe"* — por eso el sesgo es tan fácil de introducir sin notarlo.
   Fuerza `--cache none`, órdenes a mercado y protecciones apagadas para no generar falsos
   positivos.

2. **`freqtrade recursive-analysis`** (`docs/recursive-analysis.md`). **Esta es una puerta que
   no tienes** y que te puede estar mintiendo hoy. Los indicadores recursivos (EMA, RSI, ADX,
   ATR, cualquiera que arrastre el valor anterior) **no dan el mismo número si los calculas
   sobre 500 velas que sobre 5.000**. En backtest tienes el histórico entero; en vivo el
   exchange te da 1.000 velas y punto. Resultado: el bot en vivo calcula un RSI ligeramente
   distinto del que calculó el backtest, con las mismas reglas. El comando calcula el
   indicador con distintos `startup_candle_count` y te dice cuánto varía el último valor.
   *Es un fallo de paridad (tu Puerta 2) que no se ve mirando el código.*

3. **Orderflow desde trades públicos** (`docs/advanced-orderflow.md`, marcado como beta).
   Freqtrade puede descargar **trades tick a tick** (`download-data --dl-trades`) y construir
   footprint/delta, desequilibrios apilados (`stacked_imbalance_range`), volumen por nivel de
   precio. Es decir: **el análisis de flujo de órdenes es backtesteable dentro del mismo
   framework**, sin romper la paridad. Aviso de la propia doc: los datos de trades son
   enormes y el arranque se vuelve lento.

**Puntos débiles honestos:** el motor de backtest tiene supuestos que hay que conocer (las
órdenes se rellenan a precios de la vela, `custom_exit` solo ve el cierre de la vela — el bug
que ya cazaste el 7-sept), y el hyperopt es una máquina de sobreajustar si no cuentas los
intentos.

**Veredicto: sigue siendo la base correcta.** Ya lo conoces, ya tienes datos descargados,
resuelve paridad y Telegram de fábrica, y trae dos auditores automáticos (lookahead y
recursive) que refuerzan justo tu metodología.

---

### NostalgiaForInfinity — el caso de estudio más instructivo del ecosistema

Es la estrategia comunitaria más usada del mundo Freqtrade. La descargué y la medí:

| Métrica | Valor real medido |
|---|---|
| Líneas de `NostalgiaForInfinityX7.py` | **79.038** |
| Condiciones de entrada distintas | **109** |
| Números decimales codificados a mano (umbrales) | **16.937** |
| Timeframe obligatorio | 5m |
| Recomendación del autor | 6–12 operaciones abiertas, 40–80 pares |

**Qué se aprende de aquí:** con 16.937 umbrales ajustados a mano sobre el histórico, la
Puerta 4 (Deflated Sharpe) no da ningún número — el número de intentos efectivos es
incontable. Que la use mucha gente y esté viva (commit del 7-sept-2026) demuestra que
*funciona lo bastante como para que la gente siga usándola*, no que tenga ventaja demostrable.
Es exactamente el modelo que **no** debemos copiar: mucha condición, cero evidencia
estadística, imposible de auditar.

Sí merece la pena leerla para una cosa concreta: cómo estructura las **protecciones**
(condiciones de veto por régimen de mercado, por BTC cayendo, por número de operaciones
perdedoras seguidas). Ese catálogo de vetos es un buen banco de ideas para `filtros/`.

---

### pysystemtrade (Rob Carver) — **la referencia de arquitectura, y la parte más valiosa de toda esta descarga**

No es cripto (futuros gestionados), pero es el sistema con la **cadena de montaje mejor
diseñada** que existe en abierto. Lo que hay en `systems/` es literalmente una lista de
etapas, y cada etapa es una carpeta:

```
rawdata.py            → datos limpios y normalizados por volatilidad
forecasting.py        → cada REGLA de trading produce un "pronóstico" (número continuo)
trading_rules.py      → definición de las reglas
forecast_scale_cap.py → normaliza cada pronóstico a una escala común y lo tapa en ±20
forecast_combine.py   → COMBINA los pronósticos de varias reglas con pesos
positionsizing.py     → traduce pronóstico → tamaño según volatilidad y capital
portfolio.py          → reparte entre instrumentos
buffering.py          → banda muerta: no reajustar la posición por cambios pequeños
risk_overlay.py       → multiplicador global de riesgo (0 a 1) sobre TODA la cartera
accounts/             → contabilidad y métricas
```

Y sus reglas de trading provistas (`systems/provided/rules/`): `ewmac.py` (tendencia),
`breakout.py`, **`carry.py`**, `accel.py`, `cs_mr.py` (reversión transversal),
`rel_mom.py` (momentum relativo), `mr_wings.py`.

**Tres ideas de aquí que cambian el diseño de tu bot:**

1. **El pronóstico no es una "fuerza" para elegir, es un tamaño.** Tú descubriste el 7-sept
   que la "fuerza" no correlaciona con el resultado de la operación (−0,050 y 0,034) y que
   el cuartil más fuerte es el peor. La respuesta de Carver no es tirar el número: es que
   **ese número nunca debió usarse para elegir entre señales, sino para decidir cuánto
   apostar**, y solo después de escalarlo para que su valor absoluto medio sea constante y
   de taparlo en un máximo. Elegir *cuál* de 5 señales tomar y *cuánto* poner en cada una son
   dos preguntas distintas y tú las tenías fundidas en una.

2. **`risk_overlay.py` — la capa que te falta.** Es un multiplicador de 0 a 1 aplicado a
   **toda la cartera a la vez**, y toma el más conservador de tres cálculos: riesgo esperado
   demasiado alto, shock de correlación con posiciones extremas, y volatilidad "saltarina".
   Traducido a tu caso: en cripto, 5 posiciones largas en 5 monedas **son una sola apuesta**.
   Una capa que mire el riesgo total de la cartera (y no solo si cada operación individual
   pasa sus filtros) es exactamente lo que evita el escenario "todo se cae a la vez" que ya
   viste en `bb_extremo` (mayo-2021, Luna, marzo-2024).

3. **`buffering.py` — banda muerta.** No reajustas la posición cada vez que el pronóstico se
   mueve un poco; solo cuando sale de una banda. En un sistema **de ejecución manual por
   Telegram esto no es un detalle: es la diferencia entre 3 avisos al día y 40**. Reduce
   costes y reduce la carga sobre ti.

---

### NautilusTrader — potente, y probablemente excesivo hoy

Plataforma profesional por eventos con el núcleo en Rust (muy rápido, nanosegundos, soporta
datos de libro de órdenes completo). Vivo y muy activo (commit del 7-sept-2026).

**Cuándo tendría sentido:** si algún día el edge fuera de microestructura (libro de órdenes,
desequilibrios intradía a segundos). Para señales de 15m–4h ejecutadas a mano en QuantFury,
la potencia extra no compra nada y el coste de aprendizaje es alto.

**Anotación curiosa y útil:** el repo trae `AI_POLICY.md` y `CLAUDE.md` — es un proyecto
diseñado para que agentes de IA trabajen sobre él. Merece una ojeada como ejemplo de cómo
documentar un repo para que yo trabaje bien en él.

---

### Jesse (3.1.1) — el rival directo de Freqtrade

Framework cripto por eventos, con investigación (`jesse/research`), indicadores propios,
optimización y hasta un módulo `mcp` (para conectarse a asistentes de IA). Más ordenado y
moderno por dentro que Freqtrade en algunas partes.

**Por qué NO cambiar:** cambiar de framework significa reescribir los arneses, perder la
paridad ya verificada con corvus2/corvus3 (los números +94,95% / +171,65% reproducidos
exactamente) y volver a empezar la curva de errores conocidos. El coste es real y el beneficio
es estético. **No cambiar.**

---

### vectorbt / backtesting.py — el laboratorio de cribado

`vectorbt` (186 MB, activo) permite probar miles de combinaciones en segundos.
`backtesting.py` es el minimalista para una idea suelta.

**Uso correcto:** cribado masivo para **descartar**, con la regla 10 grabada en la frente
(el cribado no confirma nada). Además, cada combinación probada aquí **cuenta como un intento
para la Puerta 4** — probar 10.000 combinaciones en vectorbt y quedarse con la mejor es la
forma más rápida conocida de fabricar ruido con pinta de oro.

---

### qlib (Microsoft) y ml4t — biblioteca de ideas de ML

`qlib` estructura la investigación así: `data` → `model` → `strategy` → `backtest` →
`workflow`, con `contrib` lleno de modelos. `ml4t` es el código de un libro entero de ML para
trading.

**Uso correcto:** cantera de *features* y de código de referencia. **No** como generador de
señal principal — el bot viejo ya fingió su ventaja precisamente ahí (está anotado en tu
catálogo: *"ML como generador de señal principal — es donde el bot viejo fingió su ventaja"*).

---

### OctoBot y Hummingbot

`OctoBot` es un bot con interfaz web, orientado a usuario final más que a investigación.
`Hummingbot` está pensado para *market making* y arbitraje (proveer liquidez), que es otro
negocio distinto y depende de comisiones/rebates que en QuantFury no existen. **Ninguno de los
dos encaja con tu caso.**

---

## 3. Estructura de carpetas: tres plantillas reales y la propuesta

### Plantilla A — Freqtrade puro (lo que impone el framework)
```
user_data/
├── data/            datos OHLCV descargados
├── strategies/      clases IStrategy
├── hyperopts/       espacios de búsqueda
├── notebooks/       análisis
├── plot/            gráficos
└── backtest_results/
```
Suficiente para un bot pequeño. **Se rompe en cuanto tienes más de dos ideas**, porque todo
acaba dentro de la clase de estrategia: alfa, filtros, tamaño y ejecución mezclados. Es
exactamente el problema del que corvus3 huyó.

### Plantilla B — pysystemtrade (cadena de montaje por etapas)
```
sysdata/     acceso a datos          syscore/       utilidades
sysobjects/  objetos de dominio      sysquant/      matemáticas de cartera
systems/     LAS ETAPAS (ver arriba) sysexecution/  órdenes
sysbrokers/  conexión al bróker      sysproduction/ operativa diaria y monitorización
syslogdiag/  logs y diagnóstico      sysinit/       arranque de datos
```
**Lo importante no son los nombres, es la idea:** la investigación (`systems/`) está separada
de la producción (`sysproduction/`) y de los datos (`sysdata/`). Nunca se mezclan.

### Plantilla C — la de corvus3 (la tuya)
```
motores/   filtros/   tamano/   salidas/   arbitraje/   tests/   docs/   user_data/strategies/
```
Es buena y está bien pensada. Le faltan tres cosas que la investigación de hoy señala:
una capa de **datos** propia, una capa de **riesgo de cartera** (el `risk_overlay`), y una
capa de **operación** (el puente a Telegram, el registro de lo que tú ejecutas de verdad, la
monitorización).

### Propuesta para el bot nuevo

```
corvus4/
├── datos/                    ← NUEVO. Todo lo que entra, con su procedencia y su fecha
│   ├── descarga/             scripts de descarga (precio, funding, on-chain, macro)
│   ├── crudo/                tal cual llegó, jamás se edita a mano
│   ├── limpio/               parquet validado (sin huecos, sin duplicados, UTC)
│   └── catalogo.md           qué hay, de dónde salió, cada cuánto se actualiza
├── motores/                  alfa: histórico → candidatos (función pura)
├── filtros/                  riesgo por operación: contexto → permitido/vetado
├── tamano/                   cuánto apostar
├── salidas/                  cuándo cerrar
├── cartera/                  ← NUEVO. Árbitro + riesgo GLOBAL (el risk overlay)
├── ejecucion/                ← NUEVO. Freqtrade IStrategy + puente Telegram + registro real
├── laboratorio/              ← NUEVO. Cribados rápidos, cuadernos, experimentos desechables
├── tests/                    las puertas: causalidad, paridad, costes, intentos, recursividad
├── docs/                     esquema, partición de datos, pre-registros, bitácora
└── registro/                 intentos.jsonl, accesos a validación, señales emitidas vs ejecutadas
```

**La regla que hace que esto funcione** (la 6 de corvus3, ampliada): ninguna capa importa
código de otra salvo por su interfaz. Y una nueva: **`laboratorio/` no puede importarse desde
ninguna otra carpeta.** Lo que se demuestre ahí se *reescribe* en su capa; no se promociona
código de cribado a producción. Ese salto es justo donde se coló `bb_extremo`.

---

## 4. La capa de datos, en serio

Lo que ya tienes: 64 MB de OHLCV de Bybit y 8 CSV de macro (DVOL, rendimientos reales,
DXY proxy, oro) en corvus3.

Reglas para el almacén nuevo:

1. **Crudo inmutable.** Lo descargado se guarda tal cual, con la fecha de descarga en el
   nombre. Nunca se corrige en el sitio; las correcciones generan un archivo nuevo en `limpio/`.
2. **Parquet, no CSV**, para lo grande: 5–10× menos espacio, lectura mucho más rápida y
   conserva los tipos (un CSV convierte las fechas en texto y ahí nacen la mitad de los bugs
   de zona horaria).
3. **Todo en UTC, y la vela se etiqueta por su hora de APERTURA... pero solo se puede usar
   después de su CIERRE.** Éste es el bug exacto que hundió al bot viejo (una vela de 4h
   etiquetada con su hora de inicio dejaba ver 24h de futuro). La regla operativa: cualquier
   dato con marca temporal `t` de un timeframe de duración `d` solo puede influir en
   decisiones a partir de `t + d`.
4. **Datos "point-in-time" para lo que se revisa.** Los datos on-chain y macro **se corrigen
   a posteriori**: el valor de hoy no es el que verás dentro de un mes. Si backtesteas con el
   valor corregido, estás usando información del futuro. Para esas series hay que guardar
   *cuándo se supo cada valor*, no solo *a qué fecha se refiere*.
5. **Auditoría automática de huecos:** cada descarga verifica continuidad, duplicados, velas
   de volumen cero y saltos de precio imposibles, y falla ruidosamente. Un hueco silencioso
   en 2021 puede inventar una señal.

---

## 5. Ejecución manual por Telegram: lo que cambia

Tú no ejecutas automático. Eso tiene una consecuencia que casi nadie documenta: **el backtest
supone que la orden se ejecuta al instante y tú tardas minutos.**

Lo que hay que construir desde el principio:

1. **El aviso debe llevar todo lo necesario para actuar sin pensar**: par, dirección, precio
   de referencia, tamaño exacto, stop, objetivo, motivo (qué motor y qué filtros pasó), y un
   **identificador**.
2. **Registro de lo emitido vs lo ejecutado.** Respondes al aviso con el precio real al que
   entraste (o "no ejecutada"). Con eso se mide el **slippage humano real** — que es tu coste
   verdadero, y hoy es un número que no existe en ningún sitio. Es el único modo de que la
   Puerta 3 use un coste medido y no estimado.
3. **Caducidad de la señal.** Un aviso que llega mientras duermes debe tener fecha de
   caducidad explícita ("válido hasta las 14:00 o si el precio supera X"). Entrar 6 horas
   tarde a una señal de 4h no es la misma operación que se backtesteó.
4. **Interruptor de emergencia** y límites duros: máximo de posiciones abiertas, máximo de
   pérdidas diarias, y un veto global si el bot detecta que sus propios datos están rotos
   (mejor no avisar que avisar con datos malos).
5. **Vigilancia de "salud"**: si el bot no ha emitido nada en X días o emite muchísimo más de
   lo normal, avisa. El silencio por avería se parece demasiado al silencio por falta de señal.

---

## 6. Los tests que tiene que tener el proyecto

Los cinco que ya tienes, más dos nuevos que salen de esta investigación:

| Test | Qué comprueba | Estado |
|---|---|---|
| Causalidad | ningún indicador mira al futuro | ya lo tienes + **automatizable con `lookahead-analysis`** |
| Paridad | backtest y vivo son el mismo código | ya lo tienes |
| Costes | sobrevive al doble del coste estimado | ya lo tienes |
| Intentos (DSR) | corrige por cuántas configuraciones se probaron | ya lo tienes |
| Partición | no se tocan datos sellados | ya lo tienes |
| **Recursividad / calentamiento** | el indicador da el mismo valor con 500 velas que con 5.000 | **NUEVO — `recursive-analysis`** |
| **Riesgo de cartera** | la exposición total y la correlación entre posiciones no revientan el límite | **NUEVO — inspirado en `risk_overlay`** |

---

## 7. Recomendación

1. **Freqtrade se queda** como único camino de código (backtest = dry-run = vivo). Ya está
   validado en tu caso concreto y trae dos auditores que refuerzan tu método.
2. **La arquitectura de corvus3 se conserva**, y se le añaden tres capas: `datos/`,
   `cartera/` (árbitro + riesgo global) y `ejecucion/` (Telegram + registro real), más un
   `laboratorio/` explícitamente aislado.
3. **La respuesta al problema del árbitro no es un criterio mejor de selección, es dejar de
   seleccionar:** escalar el pronóstico, taparlo, combinarlo y usarlo para el *tamaño*
   (Carver), con una banda muerta que reduzca avisos.
4. **vectorbt entra como laboratorio de cribado**, con la contabilidad de intentos activada.
5. **mlfinlab NO se usa** (muerto desde 2021): las tres o cuatro funciones que hacen falta se
   escriben a mano y se testean.
