# motores/ — el ALFA

## Qué es "un motor"
Un motor es una idea concreta de cuándo el precio va a moverse. Ejemplo: "cuando el
StochRSI sale de sobreventa y el ADX confirma tendencia, hay más probabilidad de subida
que de bajada en las próximas N velas". Eso es todo lo que hace un motor: mirar el
histórico de precio y decir "aquí hay una oportunidad, y creo que tiene esta fuerza".

## Qué entra y qué sale
- **Entra:** histórico de precio (velas OHLCV) y lo que se derive directamente de él
  (RSI, ADX, medias, etc.).
- **Sale:** un candidato con un **pronóstico** — no una orden, no un tamaño, solo "aquí
  probablemente pasa algo, y con esta intensidad".

## Lo que un motor NO sabe y NO debe saber
- No sabe si hay noticias importantes hoy (eso es de `filtros/`).
- No sabe cuánto capital hay ni cuánto arriesgar (eso es de `tamano/`).
- No sabe cuándo cerrar la operación (eso es de `salidas/`).
- No sabe si ya hay 5 posiciones abiertas o si el mercado entero está temblando
  (eso es de `cartera/`).

Si un motor empieza a mirar cosas de fuera de su carril, ya no es un motor: es un totum
revolutum donde nadie puede saber qué falló cuando algo va mal. Esa mezcla es exactamente
la que permitió que `bb_extremo` se colara sin pasar controles en el proyecto anterior.

## Estado (8-sept-2026)
Todavía no hay motores escritos en código en este repo. Antes de escribir uno nuevo,
tocan re-verificar los heredados de corvus3, en este orden (ver `docs/00-PLAN-MAESTRO.md`
§10.1):
1. **StochRSI + ADX** — el candidato más fuerte, pendiente de las puertas 3 y 4 nuevas.
2. **Canal (Donchian) y Doble suelo** — nunca pasaron por recursividad ni por riesgo de
   cartera.
3. Resto del catálogo heredado (MACD, EMA, Supertrend, rupturas de resistencia, RSI
   divergencia, Hammer+RSI, Doji...) — casi todos descartados ya, se revisan por si acaso.
4. Solo cuando lo anterior esté cerrado, se abren los motores nuevos (M1-M4 del
   catálogo, §7.2 del plan).

## Regla de oro
Un motor se re-escribe aquí **solo después** de demostrarse en `laboratorio/`. Nunca al
revés.
