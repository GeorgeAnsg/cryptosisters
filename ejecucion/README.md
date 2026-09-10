# ejecucion/ — el puente hacia el mundo real

## Qué hace
Es la mitad del sistema que hoy no existe en ningún corvus anterior. Tres piezas:

1. **La estrategia de Freqtrade** (`IStrategy`) que conecta motores + filtros + tamaño +
   salidas + cartera en un pipeline ejecutable.
2. **El aviso de Telegram.** Como el usuario ejecuta manualmente en QuantFury (no hay
   API de trading automática ahí), el bot no compra ni vende solo: manda un mensaje con
   la operación sugerida, y el usuario decide si la ejecuta.
3. **El registro de lo que de verdad pasó.** Se anota tanto la señal EMITIDA (lo que el
   bot sugirió) como la señal EJECUTADA (lo que el usuario realmente hizo, y cuándo) —
   porque puede haber diferencia (tarda en mirar el móvil, decide no seguir un aviso,
   etc.) y esa diferencia es información real sobre el coste de ejecución manual.

## Por qué importa tanto
Sin esta carpeta, todo lo demás es un ejercicio académico. Es literalmente el puente
entre "el bot decide algo" y "el usuario gana o pierde dinero real".

## Estado (10-sept-2026)
La pieza de Telegram/QuantFury sigue vacía (Fase 6-7 del plan). Pero se ha añadido una
pieza distinta y más simple: `paper_trading/` — un piloto de forward-test con dinero
FICTICIO sobre precio REAL de Binance, para el grid adaptativo en BTC, comparando en
paralelo tres formas de ejecutar la misma estrategia (spot / futuros a mercado / futuros
límite en Bybit) para ver cuánto se lleva cada una en comisiones reales según van llegando
datos nuevos. No requiere cuenta ni API key de ningún exchange — pensado para dejar
corriendo sin supervisión en un servidor pequeño (ver `paper_trading/README.md`) durante
semanas/meses antes de decidir si merece la pena operar con dinero real.
