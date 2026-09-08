# corvus4

Bot de trading de BTC (extensible a ETH y otras cryptos), construido desde cero con la
lección aprendida de `corvus2`/`corvus3`: cada capa hace una sola cosa, no sabe nada de
las demás, y nada se acepta como bueno sin pasar 6 puertas de comprobación objetivas.

**Para entender el proyecto entero, empieza por `docs/00-PLAN-MAESTRO.md`.** Este README
es solo el mapa de carpetas.

## El mapa (orden = el camino que sigue una operación real)

```
datos/        → lo que entra: precio, funding, flujos, macro (con procedencia y fecha)
motores/      → ALFA: histórico → candidato con un pronóstico
filtros/      → riesgo POR OPERACIÓN: contexto → permitido / vetado
tamano/       → CUÁNTO: pronóstico + volatilidad + capital → tamaño
salidas/      → CUÁNDO CERRAR: objetivo, stop, tiempo máximo, trailing
cartera/      → riesgo GLOBAL + ÁRBITRO: qué se toma y cuánto riesgo total se abre
ejecucion/    → estrategia Freqtrade + aviso de Telegram + qué se ejecutó de verdad
laboratorio/  → cribados y experimentos — AISLADO, nadie importa nada de aquí
tests/        → las 6 puertas
registro/     → intentos.jsonl, accesos a validación, señales emitidas vs ejecutadas
docs/         → el plan maestro, pre-registros, bitácora
investigacion/→ toda la investigación previa (frameworks, estrategias, datos, etc.)
```

Cada carpeta tiene su propio `README.md` explicando qué hace, qué NO hace, y por qué está
separada de las demás. Léelos según los vayas necesitando — no hace falta leer todos de
golpe.

## Las dos reglas que no se negocian

1. Ninguna capa importa código de otra salvo por su interfaz de entrada/salida.
2. `laboratorio/` no se importa desde ningún sitio. Lo que se demuestre ahí se
   **reescribe** en su capa correspondiente, pasando ahí las 6 puertas de verdad.

## Estado (8-sept-2026)

Esqueleto de carpetas recién creado. Próximo paso: escribir las 6 puertas en `tests/` y
usarlas para re-verificar, en orden, StochRSI+ADX → Canal/Doble suelo → resto del
catálogo heredado → motores nuevos. Ver `docs/00-PLAN-MAESTRO.md` §10.1 y §5.
