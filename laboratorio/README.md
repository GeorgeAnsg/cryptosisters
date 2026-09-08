# laboratorio/ — cribados y experimentos (AISLADO)

## La regla más importante de esta carpeta
**Nadie importa nada de aquí. Nunca.** Ni `motores/`, ni `filtros/`, ni ninguna otra
carpeta puede hacer `import` de código que viva en `laboratorio/`.

## Por qué existe esta regla
Aquí se prueban ideas rápido y barato — cribados vectorizados, tests estadísticos
preliminares, prototipos. Es el sitio correcto para *descartar* ideas malas rápido. Pero
un cribado rápido puede parecer que funciona por razones que no sobreviven a un backtest
real (mirar `salidas/README.md` para el caso concreto de `bb_extremo`, que pasó el
cribado y falló el backtest de verdad). Si el código del laboratorio se pudiera importar
directamente en producción, sería muy fácil que una idea a medio demostrar se colara en
el sistema real por el camino corto. Eso es exactamente lo que pasó antes.

## Cómo se usa correctamente
1. Se prueba la idea aquí, con datos de la partición de **Desarrollo** solamente.
2. Si sobrevive al cribado, se re-escribe desde cero en su capa correspondiente
   (`motores/`, `filtros/`, etc.), pasando ahí las 6 puertas de verdad (`tests/`).
3. El código de `laboratorio/` se queda como lo que es: un experimento, no una pieza del
   sistema.

## Estado (8-sept-2026)
Vacío. El primer uso será la re-verificación de StochRSI+ADX (ver `motores/README.md`).
