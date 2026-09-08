# Nota sobre el presupuesto de intentos — corregido a 64, no 43

La decisión cerrada en `docs/00-PLAN-MAESTRO.md` §10 hablaba de heredar "los
43 intentos" — esos son los de `corvus3/user_data/intentos.jsonl`. Al ponerse
a registrar Canal se descubrió que `corvus2` tiene su **propio** registro de
21 intentos anteriores (`corvus2/user_data/intentos.jsonl`), y que ahí es
donde se construyó y probó Canal por primera vez (`RoturaCanal`,
`RoturaCanalLargo`).

La cadena real es tr → corvus2 (21 intentos) → corvus3 (43 intentos,
construidos encima de corvus2) → corvus4. Contar solo 43 se dejaría fuera
21 pruebas reales que sí se hicieron sobre este mismo linaje de proyecto.

**Decisión (8-sept-2026):** `registro/intentos.jsonl` hereda los 64
(21 + 43), no 43. Es la lectura más honesta del espíritu de la decisión
original (desconfiar y verificar bien), aplicada al presupuesto también.
Esto hace el listón de la Puerta 4 (DSR) un poco más exigente de lo que se
había calculado antes — con 9 años de datos el presupuesto es de ~420
configuraciones independientes; con 66 ya gastados (64 heredados + 2 de
corvus4), sigue habiendo margen amplio, pero el número de partida correcto
es 66, no 45.
