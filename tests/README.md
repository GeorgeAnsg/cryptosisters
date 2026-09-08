# tests/ — las 6 puertas

## Qué es una "puerta"
Una comprobación que una idea tiene que pasar SÍ o SÍ antes de que se la considere
válida. No son opinión, son código que falla si algo está mal — la disciplina sola no
basta (el bot anterior también tenía intención de separar entrenamiento y prueba, y aun
así se coló un error de 12 meses de los 20 que se llamaban "fuera de muestra").

## Las 6 puertas

1. **Causalidad (lookahead).** Ningún indicador puede estar viendo datos del futuro.
   Se comprueba re-ejecutando el backtest con el histórico cortado en distintos puntos y
   viendo si las señales cambian donde no deberían.

2. **Paridad backtest-vivo.** El código que decide en el backtest tiene que ser el mismo
   código que decidiría en vivo — no una aproximación.

3. **Costes reales.** Ninguna estrategia se acepta sin descontar el coste real de
   ejecutarla (spread + retraso humano en QuantFury), no un coste asumido en cero.

4. **Presupuesto de intentos (DSR).** Cuántas configuraciones distintas se han probado
   ya, y si el resultado que se ve podría explicarse solo por haber probado muchas
   veces. Con los 9 años de datos ya descargados, el presupuesto es de ~420
   configuraciones (antes eran ~45 con 5 años).

5. **Recursividad / calentamiento (NUEVA).** Indicadores como EMA, RSI, ADX o ATR dan
   valores distintos según cuántas velas históricas tengan disponibles. En backtest hay
   todo el histórico; en vivo, el exchange solo da una ventana limitada. Si no se
   comprueba esto, el bot puede comportarse distinto en vivo de como se comportó en el
   backtest sin que sea culpa de ningún otro fallo.

6. **Riesgo de cartera (NUEVA).** Ninguna estrategia se acepta mirando solo su resultado
   aislado — tiene que comprobarse cómo se comporta combinada con las demás posiciones
   abiertas a la vez (correlación, sacudidas conjuntas).

Las puertas 5 y 6 son nuevas respecto a corvus3 — no existían ahí.

## Partición de datos que respetan estas pruebas
- **Desarrollo** (2020-2024 y ahora ampliado con los 9 años descargados): sin límite de
  accesos.
- **Validación** (2025): pocos accesos, cada uno se registra en `registro/`.
- **Reserva** (2026-hoy): una sola vez, al final, cuando algo ya pasó las 6 puertas y la
  validación.

## Estado (8-sept-2026)
Vacío. Es el primer código real a escribir (Fase 0), antes de tocar ningún motor.
