# registro/ — la memoria del proyecto

## Qué guarda
- **`intentos.jsonl`** — un registro, uno por línea, de cada configuración distinta
  probada. Es la base del presupuesto de intentos (puerta 4). Se hereda el conteo de 43
  intentos de `corvus3` — no se reinicia a cero — pero cada uno se re-verifica de forma
  individual (ver `docs/00-PLAN-MAESTRO.md` §10.1).
  - Regla de contabilidad: corregir un bug en un intento ya registrado actualiza ese
    mismo registro y NO cuenta como intento nuevo. Probar una variante genuinamente
    distinta SÍ cuenta como intento nuevo y se añade como línea nueva.
- **Accesos a validación (2025)** — cada vez que una estrategia mira los datos de 2025,
  se anota cuándo, qué estrategia y por qué. Si esta lista crece demasiado, significa
  que se está gastando la validación y hacen falta datos nuevos.
- **Accesos a la reserva (2026-hoy)** — se anota igual, pero se espera que esté vacío
  hasta el final del proyecto.
- **Señales emitidas vs. ejecutadas** — lo que el bot avisó por Telegram frente a lo que
  el usuario realmente hizo (ver `ejecucion/README.md`).

## Por qué es su propia carpeta y no está mezclado con `docs/`
`docs/` son documentos que se escriben y se leen. `registro/` son datos que se van
acumulando automáticamente con cada acción del sistema — se tratan como datos, no como
texto a editar a mano.

## Estado (8-sept-2026)
`intentos.jsonl` pendiente de crear, heredando los 43 intentos de
`~/Desktop/corvus3/user_data/intentos.jsonl` como punto de partida para la
re-verificación uno a uno.
