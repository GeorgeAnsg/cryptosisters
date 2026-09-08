# tamano/ — el CUÁNTO

## Qué hace
Responde una sola pregunta: dado que una operación está permitida (pasó `filtros/`),
**¿cuánto capital pongo?**

La fórmula, ya resuelta en el plan (§6.1):

> tamaño = pronóstico **escalado** × **tapado** (con un máximo) × volatilidad objetivo × capital

## Por qué existe esta carpeta y por qué es tan importante
Se descubrió (con datos, no por intuición) que la "fuerza" de una señal NO predice si la
operación va a salir bien (correlación -0,050 y 0,034 — básicamente ruido; el grupo de
señales "más fuertes" fue el que peor resultado dio). Eso significa una cosa muy
concreta: **la fuerza de la señal nunca debe usarse para elegir qué operación tomar.**

Pero sí sirve para otra cosa: si una señal es más intensa de lo normal, tiene sentido
arriesgar un poco más en tamaño — con un tope, para que una señal extrema (probablemente
un error o un evento raro) no se coma la cartera entera.

## Qué NO hace
- No decide SI se opera (eso ya lo decidieron `motores/` + `filtros/`).
- No decide cuándo cerrar (`salidas/`).
- No decide si hay hueco en la cartera para una posición más (`cartera/`).

## Catálogo previsto (T1-T5)
Ver `docs/00-PLAN-MAESTRO.md` §7.4.

## Estado (8-sept-2026)
Vacío. Depende de tener al menos un motor y su escalado de pronóstico definidos.
