# Catálogo de datos

Qué hay, de dónde salió, cuándo se descargó y qué garantías tiene. **Este archivo se
actualiza cada vez que entra un dato nuevo.** Un dato sin ficha aquí no se usa en un backtest.

## Reglas del almacén

1. **`crudo/` es inmutable.** Lo descargado se guarda tal cual viene de la fuente. Nunca se
   corrige en el sitio; las correcciones generan un archivo nuevo en `limpio/`.
2. **Todo en UTC.** Una vela con marca temporal `t` y duración `d` **solo puede influir en
   decisiones a partir de `t + d`**. Es el bug exacto que hundió al bot viejo: una vela de 4h
   etiquetada con su hora de inicio dejaba ver 24h de futuro.
3. **Point-in-time para lo que se revisa.** Las series on-chain y macro se corrigen a
   posteriori. De ésas hay que guardar *cuándo se supo* cada valor, no solo a qué fecha se
   refiere. Backtestear con el valor ya corregido es usar el futuro.
4. **Nada entra sin pasar `descarga/auditoria.py`.** Y la auditoría falla ruidosamente: un
   hueco silencioso en 2021 puede inventar una señal que nunca existió.

## Inventario

### Precio · descargado el 8-sept-2026

| Archivo | Velas | Desde | Hasta | Auditoría |
|---|---|---|---|---|
| `BTCUSDT_1d_spot_binance.csv` | 3.302 | 2017-08-17 | 2026-08-31 | ✅ **limpio**: 0 huecos, 0 duplicados, 0 desalineados |
| `BTCUSDT_4h_spot_binance.csv` | 19.794 | 2017-08-17 | 2026-08-31 | ⚠️ 9 huecos, todos < 2019. Alineación perfecta |
| `BTCUSDT_1h_spot_binance.csv` | 79.117 | 2017-08-17 | 2026-08-31 | 🔴 29 huecos + **43 velas mal alineadas (todas en 2018)** + 4 de volumen cero |
| `BTCUSDT_15m_spot_binance.csv` | 316.414 | 2017-08-17 | 2026-08-31 | 🔴 32 huecos + **81 velas mal alineadas (todas en 2018)** + 60 de volumen cero |
| `ETHUSDT_1d_spot_binance.csv` | 3.302 | 2017-08-17 | 2026-08-31 | ✅ **limpio** |
| `ETHUSDT_4h_spot_binance.csv` | 19.794 | 2017-08-17 | 2026-08-31 | ⚠️ 9 huecos, todos < 2019. Alineación perfecta |

Fuente de todos: volcados oficiales `data.binance.vision`, spot, mensuales.

### 🔴 El defecto que encontró la auditoría la primera noche

En 1h y 15m hay velas cuya marca de apertura **no cae donde debería**: por ejemplo una vela
"de 1h" que abre a las 03:28, o una "de 15m" que abre a las 05:58. Son **43 en 1h y 81 en
15m, todas en 2018**, y aparecen justo después de las caídas de Binance de aquel año: al
reanudar el servicio, el exchange reabrió las velas en el minuto en que volvió, no en el
minuto redondo.

**Por qué importa:** una vela que dice ser de una hora pero cubre 32 minutos rompe cualquier
indicador que asuma un paso constante, y lo hace en silencio. Es una versión más sutil del
bug que hundió al bot viejo.

**Qué se hace con ellas** (decidir antes de usar 1h o 15m, y dejarlo escrito aquí):
- **Opción A, la recomendada:** usar 1h y 15m **solo desde 2019-01-01**. Se pierde 1,4 años
  de un Bitcoin que además era otro activo, y a cambio la serie queda impecable.
- Opción B: eliminar esas 124 velas y aceptar los huecos resultantes.
- **Nunca**: rellenarlas hacia atrás ni interpolarlas. Inventar precio es inventar señal.

El diario y el 4h **no están afectados** — y el diario, que es el que sostiene el salto de 45
a 420 configuraciones del presupuesto de intentos, está perfectamente limpio en los 9 años.

**Saltos de precio >30 % detectados y verificados como reales**, no errores: 2020-03-12
(crash del COVID, BTC 7.935 → 4.800) y 2017-09-15 (prohibición china, en 4h).

**Por qué spot de Binance y no el perpetuo de Bybit que ya teníamos:** el spot empieza en
agosto de 2017; el perpetuo, en marzo de 2020. Esos tres años extra suben el techo de
configuraciones que podemos permitirnos probar de **45 a 420** (ver `docs/00-PLAN-MAESTRO.md`
§3.1). El perpetuo de Bybit sigue siendo válido y se conserva: es el que refleja el mercado
donde se paga funding.

**Saltos de precio >30 % detectados y verificados como reales:** 2020-03-12 (crash del COVID)
y 2017-09-15 (prohibición china a los exchanges). No son errores de datos.

### Heredado de corvus3 (no se vuelve a descargar)

| Qué | Dónde | Nota |
|---|---|---|
| OHLCV de 34 pares en 4h, perpetuo Bybit | `corvus3/user_data/data/bybit/futures/` | desde 2020-03 |
| BTC 15m/1h/4h perpetuo + funding rate 1h | idem | |
| DXY (proxy FRED), US10Y, US2Y, rendimientos reales (TIPS), oro | `corvus3/user_data/data/macro/` | series de FRED |
| DVOL de Deribit (1h) | idem | desde 2021-03 |

### Pendiente, por orden de urgencia

| Prioridad | Dato | Por qué |
|---|---|---|
| 🔴 **URGENTE** | Open interest · long/short ratio · liquidaciones | Las APIs de exchange **solo dan 30 días**. Cada día sin recolectar es histórico perdido para siempre. Necesita un recolector diario |
| 🟠 alta | Funding de Binance con histórico completo (desde 2019) | Señal de posicionamiento; el de Bybit ya lo tenemos |
| 🟠 alta | Flujos diarios de ETF spot (Farside) | La señal de "dinero real" más limpia y barata. Desde ene-2024 |
| 🟡 media | Trades públicos (tick) para CVD | `freqtrade download-data --dl-trades`. Pesado: solo el tramo que se vaya a usar |
| 🟡 media | COT del CME (CFTC) | Semanal, gratis, contexto de posicionamiento institucional |
| ⚪ baja | Hashrate, comisiones, direcciones activas, supply de stablecoins | Gratis y sin revisiones, pero evidencia predictiva baja |

## Herramientas

| Script | Qué hace |
|---|---|
| `descarga/binance_spot_klines.py` | Baja velas de spot de los volcados oficiales de Binance. Sin dependencias externas. `python3 binance_spot_klines.py BTCUSDT 1d,4h,1h,15m` |
| `descarga/auditoria.py` | Audita orden, duplicados, huecos, coherencia OHLC, volumen cero y saltos imposibles. Devuelve código de error si algo falla. `python3 auditoria.py` audita todo `crudo/` |
