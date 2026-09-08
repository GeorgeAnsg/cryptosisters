# filtros/ — el riesgo POR OPERACIÓN

## Qué hace
Coge el contexto del momento (sesión horaria, volatilidad reciente, si hay noticias
importantes, si el mercado está en tendencia o en lateral, etc.) y responde una sola
pregunta por cada candidato que le llega de `motores/`:

> ¿Esta operación concreta, en este momento concreto, está **permitida** o **vetada**?

No mejora el pronóstico, no lo toca. Solo lo deja pasar o lo bloquea.

## Ejemplo para entenderlo
Un motor dice "aquí hay una señal de compra". Un filtro puede decir "sí, pero no en la
hora de menor liquidez del día" o "no, hay una decisión de tipos de interés dentro de
20 minutos". El motor sigue teniendo razón sobre el patrón; el filtro decide si es
buen momento para actuar sobre él.

## Qué NO hace
- No genera candidatos (eso es `motores/`).
- No decide cuánto arriesgar (eso es `tamano/`).
- No mira cuántas posiciones hay ya abiertas en el resto de la cartera — eso es un
  veto *global*, vive en `cartera/`, no aquí. Un filtro solo ve la operación individual.

## Catálogo previsto (F1-F10)
Ver `docs/00-PLAN-MAESTRO.md` §7.3 para la lista completa con prioridades.

## Estado (8-sept-2026)
Vacío. Se empieza a poblar en cuanto haya al menos un motor re-verificado que necesite
filtros para pasar la puerta de costes reales.
