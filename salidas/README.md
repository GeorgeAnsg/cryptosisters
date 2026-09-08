# salidas/ — el CUÁNDO CERRAR

## Qué hace
Una vez que una posición está abierta, esta capa decide cuándo cerrarla:
- Objetivo de beneficio (take-profit).
- Stop de pérdida.
- Tiempo máximo en la operación (si no ha pasado nada, se cierra igualmente).
- Trailing (mover el stop a favor si el precio avanza).

## Por qué es su propia carpeta y no parte del motor
Un hallazgo ya documentado en `corvus3` (Regla 10 del catálogo heredado): un cribado
rápido puede parecer que funciona porque mide "qué pasa a N velas fijas", pero la
operación real no llega a esa vela — sale antes por el stop o por una salida dinámica.
`bb_extremo` pasó el cribado y luego falló el backtest real por esta razón exacta.
Separar "cuándo entro" (motor) de "cuándo salgo" (esta carpeta) obliga a probar la
salida de verdad, con las reglas de salida de verdad, no con un horizonte de mentira.

## Qué NO hace
- No decide si abrir la operación.
- No decide el tamaño.
- No sabe nada de otras posiciones abiertas.

## Catálogo previsto (S1-S4)
Ver `docs/00-PLAN-MAESTRO.md` §7.5.

## Estado (8-sept-2026)
Vacío.
