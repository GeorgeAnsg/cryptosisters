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

## Estado (8-sept-2026)
Vacío. Es de las últimas piezas a construir (Fase 6-7 del plan), pero se documenta desde
ya para que el hueco quede visible en la arquitectura.
