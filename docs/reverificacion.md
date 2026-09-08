# Re-verificación de los 43 intentos heredados — seguimiento

Ver `docs/00-PLAN-MAESTRO.md` §10.1 para el porqué y el orden de esta lista.
Orden: StochRSI+ADX → Canal (Donchian) y Doble suelo → resto del catálogo →
motores nuevos.

Cada candidato pasa por las 6 puertas de `tests/`. Solo cuando pasa las 6 se
re-escribe de verdad en `motores/`. Si falla una, se para ahí y se anota el
motivo — no hace falta gastar tiempo en las puertas siguientes.

## 1. StochRSI + ADX

Código del candidato: `laboratorio/stochrsi_adx.py` (réplica fiel de
`~/Desktop/tr/v6/core/bot_indicators.py`). Tres variantes: A) sobreventa sin
mirar tendencia, B) sobreventa solo en tendencia bajista confirmada, C) cruce
alcista.

| Puerta | Qué comprueba, en una frase | Resultado | Fecha |
|---|---|---|---|
| 1. Causalidad | ¿El indicador usó alguna vez datos del futuro? | **PASA** — 60 cortes al azar sobre BTC 4h (2017-2026), 0 diferencias | 2026-09-08 |
| 2. Paridad backtest-vivo | ¿El código de decisión sería el mismo en vivo? | Pendiente | — |
| 3. Costes reales | ¿Sigue siendo rentable descontando spread + retraso de ejecución manual? | Pendiente | — |
| 4. Presupuesto de intentos (DSR) | ¿El resultado podría ser azar por cuántas veces se ha probado? | Pendiente | — |
| 5. Recursividad/calentamiento | ¿Cambia la señal según cuánto histórico tenga disponible el bot en vivo? | Pendiente | — |
| 6. Riesgo de cartera | ¿Se comporta bien combinado con las demás posiciones abiertas? | Pendiente | — |

**Qué significa el resultado de hoy, para decidir:** la Puerta 1 solo descarta
una cosa muy concreta — que el indicador estuviera haciendo trampa mirando al
futuro. No la hacía. Esto NO confirma todavía que StochRSI+ADX vaya a ganar
dinero: solo confirma que, si al final resulta que gana dinero, no será por
esta trampa. Quedan 5 puertas más antes de poder decidir si esto se construye
de verdad en `motores/`.

## 2. Canal (Donchian) y Doble suelo

Pendiente — siguiente en la cola.

## 3. Resto del catálogo heredado

Pendiente.

## 4. Motores nuevos (M1-M4)

No se abre hasta cerrar los tres puntos anteriores.
