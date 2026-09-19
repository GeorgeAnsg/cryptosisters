# entradas/ — el CUÁNDO Y CÓMO ABRIR

## Qué hace
Una vez que un motor (`motores/`) emite un candidato con su pronóstico, esta capa
decide dos cosas distintas:
- **Cuándo exactamente entrar** — ¿en cuanto se detecta el patrón, o conviene esperar
  algo más de confirmación?
- **Cómo entrar** — orden a mercado o límite, de una vez o escalonada.

## Por qué es su propia carpeta y no parte del motor
Mismo argumento que `salidas/`: un motor solo pronostica ("aquí probablemente pasa
algo, con esta intensidad"), no decide acción. Mezclar la entrada dentro del motor
impediría probar la entrada de verdad (coste de ejecución, tipo de orden) sin
contaminar la puntuación del patrón.

## Punto de partida ya validado (no hay que redescubrirlo)
El 12-sept-2026 se probó explícitamente, para doble techo y doble suelo por separado,
si esperar a que la confianza en vivo suba (el patrón se va formando y la probabilidad
crece día a día tras detectarse) mejora el resultado frente a entrar en cuanto se
detecta. En los dos patrones la respuesta fue que NO. Implementado ya en
`entradas/doble_techo.py`/`doble_suelo.py` y re-confirmado ese mismo día con la lógica
corregida (ver más abajo) sobre BTC y ETH — entrar en día 0 gana con claridad en los 4
casos:

| | día 0 | esperar a confianza≥50% | esperar a confianza≥90% |
|---|---|---|---|
| BTC técho (retorno medio) | **3.39%** | -0.34% | -1.56% |
| BTC suelo (retorno medio) | **7.81%** | 3.94% | 5.25% |
| ETH técho (retorno medio) | **3.29%** | 0.91% | -2.36% |
| ETH suelo (retorno medio) | **9.67%** | 5.10% | 4.51% |

**Regla de entrada por defecto, con esa base empírica:** entrar en cuanto el motor
emite el candidato (día 0 de la detección), no esperar confirmación adicional.

**Matiz importante (fácil de malinterpretar, nos pasó al re-verificarlo):** "día 0" NO
significa "opera cualquier máximo/mínimo aparente reciente sin filtrar". Se comprobó
por accidente: evaluar TODOS los máximos/mínimos aparentes (cualquier punto que sea el
más alto/bajo de los últimos 3 días) sin más filtro da un retorno medio malo, porque la
mayoría nunca llega a ser un patrón real. La población correcta para esta regla es "un
candidato que la puntuación (`probabilidad_total`) ya considera relevante" — el filtro
sigue siendo la puntuación (continua, sin cortes duros, igual que en el resto del
proyecto), no el tiempo de espera. "Día 0" solo dice: una vez ahí, no esperes más días
de confirmación pensando que la nota va a subir y merecer más la pena — ya no mejora.

## Qué NO hace
- No decide el tamaño de la posición (eso es de `tamano/`).
- No decide cuándo cerrar la operación (eso es de `salidas/`).
- No sabe si hay otras posiciones abiertas (eso es de `cartera/`).
- No coloca la orden de verdad ni avisa al usuario (eso es de `ejecucion/`) — aquí solo
  se decide QUÉ orden habría que mandar, no se manda.

## Qué falta explorar
- Tipo de orden (mercado vs límite) y si fraccionar la entrada en vez de todo de golpe.
- El coste de ejecución real: el usuario opera manualmente en QuantFury tras un aviso de
  Telegram (`ejecucion/README.md`), así que hay un retraso humano entre "el bot sugiere"
  y "el usuario ejecuta" que ya se identificó como una fuente real de diferencia — una
  regla de entrada tiene que ser realista con ese retraso, no asumir ejecución instantánea.
- Si conviene usar `confirmacion_cruzada()` (capa 4 del motor de techo) como parte de la
  regla de entrada: tal como está medida hoy (ventana ±N días) sirve para backtest pero
  no es utilizable en vivo sin ajustarla (ver aviso en `motores/doble_techo.py`).

## Estado (12-sept-2026)
Vacío en código. La regla "día 0, sin esperar confirmación" está documentada arriba
como punto de partida, pero todavía no se ha escrito como función reutilizable aquí.
