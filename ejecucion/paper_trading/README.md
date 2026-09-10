# Paper trading — 12 cripto + oro + 3 acciones + 2 índices

Forward-test con dinero FICTICIO sobre precio REAL. Compara en paralelo
tres formas de ejecutar el mismo grid: spot, futuros a mercado, futuros
límite en Bybit — mismo código, mismo histórico, solo cambia el coste por
operación que se resta.

**No ejecuta ninguna orden real. No necesita ninguna cuenta ni clave de
API.** Es contabilidad ficticia para comprobar si el backtest se sostiene
con datos que van llegando de verdad, antes de arriesgar nada.

Dos scripts:
- `bot_grid_papel.py` — BTC, ETH, XRP, BNB, SOL, ADA, DOGE, LINK, AVAX,
  DOT, LTC, TRX (Binance público, sin auth). Todos con la misma config
  genérica — deliberado, no un descuido: es la config validada en BTC/ETH
  con 9 años de datos, y lo que este forward test comprueba es si esa
  misma receta generaliza al resto, no si cada uno tiene su óptimo propio
  (ajustar cada activo a su propio historial sería la misma trampa de
  sobreajuste que ya pasó con el oro — ver aviso abajo).
- `bot_grid_papel_oro.py` — oro (Yahoo Finance, futuro GC=F; no hay ningún
  token cripto de oro fiable, PAXG demostró comportarse distinto al oro
  real).
- `bot_grid_papel_acciones.py` — Nvidia, Google, Coca-Cola, S&P 500
  (`^GSPC`) y Nasdaq (`^IXIC`) (Yahoo Finance, mismo endpoint que el oro,
  cambia solo el símbolo). Los índices llevan el mismo aviso de
  fragilidad que las acciones sueltas — ver más abajo.
- `notificar_resumen.py` — aviso de Telegram al arrancar el contenedor +
  resumen nocturno (a partir de las 20:00 hora Madrid, una vez al día) con
  el capital ficticio de cada activo. Rescatado y simplificado de la
  función de Telegram del bot viejo (`v6/core/bot_core.py:send_telegram`).
  Necesita `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` como variables de entorno
  en Coolify — si faltan, no manda nada y no rompe el bucle. **Esto es solo
  el titular legible; los CSV de `logs/` siguen siendo la fuente detallada
  de cada acción tomada en cada ciclo** — revísalos si quieres ver el
  detalle completo, no solo el resumen de la noche.

**Aviso de fiabilidad, para leer los resultados con la cabeza correcta:**
BTC y ETH tienen evidencia sólida detrás (Doble suelo/Techo confirmados,
grid probado extensamente, 9 años de datos). El resto de cripto
(XRP/BNB/SOL/ADA/DOGE/LINK/AVAX/DOT/LTC/TRX) nunca se habían probado con
el GRID hasta ahora — esto es, de facto, su primera prueba, aunque sea en
vivo y no en backtest. Dentro de ese grupo, BNB/XRP/SOL arrancan con años
de historial real (ya descargado en `datos/crudo/`); ADA/DOGE/LINK/AVAX/
DOT/LTC/TRX arrancan solo con las últimas ~166 sesiones de 4h que da la
API de Binance de una vez, así que sus primeras semanas tienen menos
"calentamiento" de indicadores (ADX/ATR) — no es un fallo, solo hay que
esperar más para confiar en su lectura. El oro es el candidato más frágil
de todos: su resultado "bueno" solo se vio en una ventana corta de 2,4
años que coincidió con un rally, y la versión ajustada específicamente a
él se rompió al probarla en plata y platino — aquí corre con la config
genérica de BTC/ETH, no la ajustada, precisamente para no arrastrar ese
sobreajuste. Trata sus números con más escepticismo que los del resto.

**Nvidia/Google/Coca-Cola son el grupo más especulativo de todos, por
encima incluso del oro.** No es solo que el grid nunca se haya probado en
ellas — es que el mecanismo en sí nunca se ha probado en un mercado que
NO cotiza 24/7. Una acción cierra cada tarde y reabre al día siguiente con
un salto de precio (a veces grande, por resultados trimestrales u otra
noticia) que no existe en cripto; cosas como el re-centrado periódico del
grid o el cálculo de ATR nunca se han visto sometidas a esos huecos. Este
forward test no está comprobando "¿funciona la config genérica aquí
también?" (esa es la pregunta para el resto de activos) — está
comprobando algo más básico: "¿se comporta el grid de forma razonable en
un mercado con horario, o hace algo raro?". Además, las variantes de
coste (spot/futuros mercado/futuros límite) están pensadas para cripto en
Bybit — no representan comisiones reales de bolsa, así que compáralas
entre sí para ver el efecto relativo del coste, no como cifra de
comisión real. Trátalo como una curiosidad exploratoria, no como una señal.

**Coste de añadir más activos:** es prácticamente cero. Los 12 pares
cripto tardan ~7-8 segundos en total (una llamada API + una simulación
por activo, nada de cómputo pesado). Añadir más solo es sumar el símbolo
a `PARES_CRIPTO` en `bot_grid_papel.py` — no requiere cambios de código.

## Uso manual (para probarlo)
```bash
cd corvus4
python3 ejecucion/paper_trading/bot_grid_papel.py             # los 12 cripto de una vez
python3 ejecucion/paper_trading/bot_grid_papel_oro.py         # el oro
python3 ejecucion/paper_trading/bot_grid_papel_acciones.py    # NVDA, GOOGL, KO
```
La primera vez que un activo arranca sin nada guardado (`datos_vivos/`
vacío), pagina Binance hacia atrás hasta traer todo su histórico real
(años, no solo los últimos 1000 velas que da una sola llamada) — tarda
unos segundos por activo, una sola vez. **Esto es importante en un
despliegue nuevo**: `datos/crudo/` (el histórico ya validado en local)
está en `.gitignore` y no viaja con el repo a Coolify, así que el bot en
el servidor SIEMPRE arranca así, paginando desde cero, no leyendo esa
carpeta. A partir de la primera vez, vive en `datos_vivos/` y crece con
cada ejecución normal (una sola llamada, barato). Cada activo anota su
resultado en `logs/<PAR>_4h_paper.csv` (una fila por ejecución, con el
capital ficticio de las tres variantes).

## Desplegar en Coolify (Hetzner)

Hay un `Dockerfile` listo — el contenedor corre en bucle infinito,
ejecutando los 18 activos (12 cripto + oro + 3 acciones + 2 índices) cada 4 horas (no
expone ningún puerto, es un proceso de fondo, no un servicio web).

**Importante — persistencia.** Los scripts escriben en la carpeta que
diga la variable de entorno `CORVUS4_DATA_ROOT` (por defecto, en local,
junto al propio script — así lo que ya se probó a mano sigue funcionando
igual). El `Dockerfile` fija `CORVUS4_DATA_ROOT=/app/data`. Eso significa
que si Coolify redespliega el contenedor desde una imagen nueva sin más,
**se pierde todo el historial acumulado y el log del forward test empieza
de cero cada vez** — justo lo que no quieres si vamos a revisarlo día a
día. Antes de dar el despliegue por bueno:

1. En la configuración del recurso en Coolify, añade **un único volumen
   persistente** que monte `/app/data`. No hace falta montar nada más —
   `datos_vivos/` y `logs/` se crean solos ahí dentro.
2. El build context del Dockerfile es la raíz del repo (`corvus4/`), no
   esta subcarpeta — así puede hacer `sys.path` hacia `laboratorio/` y
   `datos/`. Confirma que Coolify apunta el contexto de build a la raíz.
3. Tras el primer despliegue, entra al contenedor (o revisa los logs de
   Coolify) y comprueba que aparece la primera línea de cada activo antes
   de dejarlo correr solo.

## Cómo leer los resultados
Cada fila del CSV es una foto del capital ficticio acumulado hasta ese
momento (arrancando en 100) en las tres variantes. Compáralas entre sí
(¿se separan mucho con el tiempo? ¿alguna empieza a caer mientras las
otras suben?) y compáralas contra el backtest original — si empiezan a
divergir de forma sostenida (no un mal día suelto), es la señal de que
algo del mundo real no está en el backtest y hay que investigarlo antes
de considerar operar con dinero real. Para BTC/ETH, cualquier divergencia
sostenida es una señal fuerte (mucha evidencia previa detrás). Para
XRP/BNB/oro, un mal resultado no es tan sorprendente — todavía no tenían
evidencia sólida antes de este forward test.
