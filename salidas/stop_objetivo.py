"""
salidas/ -- CUANDO CERRAR una operacion ya abierta por `entradas/`.

Dos variantes de la misma mecanica (stop + objetivo por ATR, sin niveles
fijos en %), construidas juntas el 13-sept-2026 para compararlas entre si
con datos reales, no para asumir cual es mejor:

- FIJA: el multiplo de riesgo/recompensa (R) es el mismo para cualquier
  candidato, independientemente de lo fuerte que sea su patron.
- DINAMICA: el R escala linealmente con `probabilidad_total_si_confirma`
  del candidato (que ya calcula `entradas/`) -- un patron mas limpio
  aguanta un objetivo mas lejano, uno flojo se conforma con menos. Idea
  del usuario (13-sept-2026); no se asume que ayude, se compara con la
  fija en `laboratorio/` antes de decidir cual usar en produccion.

Mecanica compartida por las dos:
- Stop inicial: precio_entrada -/+ k_atr_stop * ATR(14) (resta si es
  largo/suelo, suma si es corto/techo) -- nunca un % fijo, se adapta a
  la volatilidad real de la moneda en el momento de entrar.
- Objetivo: precio_entrada +/- R * riesgo, donde riesgo = |precio_entrada
  - stop| y R viene de la variante fija o dinamica.
- Salida por tiempo: si en `dias_maximo` no se toca ni el stop ni el
  objetivo, se cierra al precio de ese ultimo dia (no se deja la
  operacion abierta indefinidamente).
- Si en el mismo dia se tocan stop Y objetivo (rango high/low de una vela
  volatil), se asume que el stop se ejecuto primero -- supuesto
  conservador estandar en backtesting sin datos intradia, sesga el
  resultado en contra de esta capa, nunca a su favor.

Que NO hace: no decide el tamano de la posicion (`tamano/`), no sabe si
hay otras operaciones abiertas (`cartera/`), no coloca ninguna orden real
(`ejecucion/`). Solo calcula, dado un candidato de entrada ya decidido,
en que precio saldria si el patron confirma y en que precio saldria si
falla.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

Direccion = Literal["largo", "corto"]


@dataclass
class NivelesSalida:
    stop: float
    objetivo: float
    riesgo: float  # |precio_entrada - stop|, en unidades de precio


def calcular_niveles_fijos(
    precio_entrada: float, atr_valor: float, direccion: Direccion,
    k_atr_stop: float, r_fijo: float,
) -> NivelesSalida:
    riesgo = k_atr_stop * atr_valor
    if direccion == "largo":
        stop = precio_entrada - riesgo
        objetivo = precio_entrada + r_fijo * riesgo
    else:
        stop = precio_entrada + riesgo
        objetivo = precio_entrada - r_fijo * riesgo
    return NivelesSalida(stop=stop, objetivo=objetivo, riesgo=riesgo)


def alinear_indices_4h(df: pd.DataFrame, df4h: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Para el dia `i` de `df` (velas diarias), las velas de `df4h` que caen
    dentro de ese dia estan en `df4h[inicio[i]:fin[i]]` -- por busqueda de
    fecha (no por indice fijo *6), para no asumir que todos los dias tienen
    exactamente 6 velas de 4h (el primer dia de historico disponible no las
    tiene). Graduado de `laboratorio/patrones/trailing_4h_persistencia.py`
    (18-sept-2026), sin cambios: es pura alineacion de datos ya cargados,
    no una decision de cuando cerrar, asi que no le corresponde saber nada
    de trailing ni de niveles -- solo lo usa quien llama a `simular_trade`
    con los parametros `trailing_*`."""
    dias4h = df4h["open_time"].dt.floor("D").to_numpy()
    dias_diarios = df["open_time"].dt.floor("D").to_numpy()
    inicio = np.searchsorted(dias4h, dias_diarios, side="left")
    fin = np.searchsorted(dias4h, dias_diarios, side="right")
    return inicio, fin


def calcular_niveles_dinamicos(
    precio_entrada: float, atr_valor: float, direccion: Direccion,
    k_atr_stop: float, r_min: float, r_max: float, probabilidad: float,
) -> NivelesSalida:
    """Igual que `calcular_niveles_fijos`, pero R = r_min + (r_max - r_min)
    * probabilidad -- `probabilidad` es `probabilidad_total_si_confirma`
    del candidato de `entradas/` (0-1, ya calculada)."""
    r_dinamico = r_min + (r_max - r_min) * probabilidad
    return calcular_niveles_fijos(precio_entrada, atr_valor, direccion, k_atr_stop, r_dinamico)


@dataclass
class TradeSalida:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo: Literal["stop", "stop_trailing", "objetivo", "tiempo_maximo", "senal_externa",
                     "condicion_persistente", "senal_confirmada", "trailing_retroceso_alto"]
    retorno_pct: float
    # Venta parcial (17-sept-2026): si se activo, la fraccion de la posicion
    # que YA se vendio a mitad de camino queda fuera de `retorno_pct` (que
    # sigue describiendo solo el cierre final, sobre `fraccion_restante` de
    # la posicion). Quien llama (ejecucion/) combina las dos partes usando
    # el tamano real de la posicion -- esta capa no conoce el tamano.
    fraccion_restante: float = 1.0
    idx_venta_parcial: int | None = None
    precio_venta_parcial: float | None = None


def simular_trade(
    df: pd.DataFrame, idx_entrada: int, direccion: Direccion,
    precio_entrada: float, niveles: NivelesSalida, dias_maximo: int,
    senal_externa: np.ndarray | None = None,
    condicion_persistente: np.ndarray | None = None, dias_persistencia: int = 1,
    atr_valor: float | None = None, k_atr_trailing: float | None = None,
    cushion_pct_minimo: float | None = None,
    prob_contraria: np.ndarray | None = None, umbral_contraria: float = 0.7,
    umbral_contraria_en_ganancia: float | None = None,
    venta_parcial_umbral: float | None = None, venta_parcial_fraccion: float | None = None,
    senal_con_confirmacion: np.ndarray | None = None, serie_confirmacion: np.ndarray | None = None,
    caida_relativa_confirmacion: float | None = None,
    df4h: pd.DataFrame | None = None,
    indice_4h_inicio: np.ndarray | None = None, indice_4h_fin: np.ndarray | None = None,
    trailing_activacion_pct: float | None = None, trailing_retroceso_pct: float | None = None,
    trailing_velas_persistencia: int = 1, trailing_umbral_intradia_pct: float | None = None,
) -> TradeSalida | None:
    """Recorre dia a dia desde `idx_entrada + 1` comprobando el rango
    high/low de cada vela (no solo el cierre) contra stop/objetivo.
    Devuelve None si no hay suficientes velas futuras en `df` para
    resolver la operacion dentro de `dias_maximo` (caso solo relevante al
    final del historico disponible).

    Dos ganchos GENERICOS para anadir motivos de salida sin que esta capa
    tenga que saber que es un "patron" o un "regimen" -- eso lo calcula
    quien llama (`salidas/` no importa `entradas/` ni `motores/` para
    esto, sigue sin saber nada de las demas capas):

    - `senal_externa`: array booleano (mismo largo que `df`) -- si en el
      dia `i` vale True, se cierra ESE MISMO DIA sin mas condicion. Pensado
      para una senal puntual ya filtrada por quien llama (ej. "aparecio un
      candidato de patron contrario con probabilidad suficiente").
    - `condicion_persistente` + `dias_persistencia`: `condicion_persistente`
      es un array booleano que puede ser cierto varios dias seguidos sin
      que cada uno, por si solo, sea motivo de salida -- se cierra solo
      cuando lleva `dias_persistencia` dias CONSECUTIVOS en True desde que
      empezo a estarlo (nunca acumulado a lo largo de toda la operacion).
      Pensado para "el regimen dejo de ser favorable" -- un solo dia de
      ruido no basta, exigir varios dias seguidos filtra ese ruido.

    - `atr_valor` + `k_atr_trailing`: activa un trailing stop (Chandelier,
      pieza S2 del plan maestro, 14-sept-2026) -- protege ganancias ya
      conseguidas dentro de la operacion, sin necesidad de ninguna senal de
      patron. Cada dia, el stop efectivo se recalcula como
      `maximo_favorable_desde_la_entrada -/+ k_atr_trailing * atr_valor`
      (resta si es largo, suma si es corto) y SOLO puede volverse mas
      protector que el nivel anterior (nunca se relaja) -- si el precio
      nunca avanza a favor, el trailing nunca mejora el stop original de
      `niveles.stop`, asi que esta idea no cambia nada para una operacion
      que no llega a ir ganando. Motivo de un caso real detectado el
      14-sept-2026: una operacion llego a un +17% de ganancia flotante y
      termino en -1.8% de perdida por no tener ningun mecanismo que
      protegiera esa ganancia mientras el precio se daba la vuelta.

    - `cushion_pct_minimo` (15-sept-2026): el trailing de arriba SOLO empieza
      a mover el stop una vez que el precio ya avanzo a favor al menos este
      porcentaje desde `precio_entrada` (ej. 0.03 = 3%). Antes de llegar a
      ese colchon, el stop se queda en `niveles.stop` de siempre -- pensado
      para no reaccionar al ruido normal de los primeros dias y solo activar
      la proteccion cuando ya hay una ganancia flotante real que proteger.
      Si es None, el trailing (si esta activo) empieza a moverse desde el
      primer avance a favor, sin colchon -- comportamiento identico al
      trailing simple ya probado.

    - `prob_contraria` + `umbral_contraria` + `umbral_contraria_en_ganancia`
      (14-sept-2026): version CONTINUA de `senal_externa`, para cuando quien
      llama tiene una nota 0-1 por dia (ej. `probabilidad_total_si_confirma`
      o `probabilidad_en_vivo` de un patron contrario) en vez de un booleano
      ya decidido. Se cierra el dia `i` si `prob_contraria[i]` supera el
      umbral que toque -- `umbral_contraria_en_ganancia` (mas permisivo) si
      la operacion YA VA GANANDO ese dia (precio a favor de la entrada),
      si no `umbral_contraria` (el normal). Si `umbral_contraria_en_ganancia`
      es None, se comporta igual que un umbral unico. Idea del usuario
      (14-sept-2026): una vez la operacion ya va bien, no hace falta una
      señal tan exigente para plantearse cerrar y proteger lo ganado.

    - `venta_parcial_umbral` + `venta_parcial_fraccion` (validado
      14-sept-2026, parametros confirmados: 0.20 / 0.50): en cuanto la
      ganancia flotante (medida sobre el rango high/low favorable del dia,
      no solo el cierre) alcanza `venta_parcial_umbral`, se vende esa
      `venta_parcial_fraccion` de la posicion a ese precio exacto y el
      resto sigue abierto con normalidad. Solo puede pasar una vez por
      operacion. El resultado de esa venta queda en `pnl_parcial_por_unidad`
      del dict que devuelve `simular_cuenta_generica` (ver mas abajo) --
      esta funcion de mas bajo nivel solo expone `idx_venta_parcial` y
      `precio_venta_parcial` en `TradeSalida`, quien la llama calcula el
      dinero real con el tamano de la posicion.

    - `senal_con_confirmacion` + `serie_confirmacion` +
      `caida_relativa_confirmacion` (validado 14-sept-2026, parametro
      confirmado: 0.30 -- pensado para `racha_rota`, ver
      `salidas/racha_rota.py`): version RETARDADA de `senal_externa`. El
      aviso booleano (`senal_con_confirmacion[i]`) NO cierra la operacion
      de inmediato -- solo se honra el dia en que `serie_confirmacion` ya
      se ha enfriado un `caida_relativa_confirmacion` relativo desde su
      propio extremo alcanzado DESDE que se abrio esta operacion. Pensado
      para no cortar una operacion sana en plena respiracion normal justo
      cuando aparece el aviso, esperando a que el impulso realmente pierda
      fuerza. Si `senal_con_confirmacion` es None, no tiene efecto.

    - `df4h` + `indice_4h_inicio` + `indice_4h_fin` + `trailing_activacion_pct`
      + `trailing_retroceso_pct` + `trailing_velas_persistencia` +
      `trailing_umbral_intradia_pct` (graduado 18-sept-2026 desde
      `laboratorio/patrones/trailing_retroceso_alto.py` y
      `trailing_4h_persistencia.py`): trailing por RETROCESO RELATIVO desde
      el pico de ganancia flotante de la propia operacion (no confundir con
      el trailing Chandelier de `k_atr_trailing` de arriba, basado en ATR y
      descartado en su validacion). Se activa en cuanto la ganancia de pico
      alcanza `trailing_activacion_pct`; a partir de ahi, si la ganancia
      actual cae a `trailing_retroceso_pct` relativo desde ese pico, se
      cierra por "trailing_retroceso_alto". Se resuelve a resolucion de 4h
      (`df4h`, alineado con `df` via `alinear_indices_4h`) en vez de una vez
      al dia -- pero SOLO exige `trailing_velas_persistencia` velas de 4h
      seguidas confirmando el retroceso mientras la ganancia de pico ya
      supera `trailing_umbral_intradia_pct`; por debajo de ese umbral se
      comprueba una unica vez al dia (al cierre), sin persistencia --
      exactamente igual que la version 100% diaria ya confirmada por
      separado. Si `df4h` es None, este mecanismo esta desactivado y
      `simular_trade` se comporta exactamente igual que antes de
      graduarlo (stop/objetivo comprobados una vez al dia, sin este
      trailing).

      SIN CONFIRMAR bajo el stop/objetivo real de produccion (18-sept-2026):
      el barrido umbral_intradia/velas_persistencia que dio 8/8 en
      `trailing_4h_persistencia.seleccion_robusta_condicional` +
      `confirmar_holdout_condicional` se hizo con K_ATR_STOP=2.5/R_FIJO=3.0
      (la "config moderada" de `prueba_cuenta_1000e_v3_racha.py`), no con
      K_ATR_STOP=1.2/R_FIJO=4.0 (el switch confirmado que usa realmente
      `ejecucion/cuenta_referencia.py`). Revalidado con los parametros
      reales, el mejor umbral/velas encontrado cae a solo 3/8 -- ver
      `registro/intentos.jsonl`, intento
      `trailing_4h_persistencia_condicional_stop_real`. `ejecucion/
      cuenta_referencia.py` NO invoca estos parametros por ahora; quedan
      aqui como hook opcional, disponible si una futura re-parametrizacion
      bajo el perfil de riesgo real llega a confirmarse.

    - `trailing_activacion_pct` + `trailing_retroceso_pct` SIN `df4h` (mismos
      dos parametros de arriba, pero sin pasar datos de 4h): version 100%
      DIARIA del trailing por retroceso relativo, graduada de
      `laboratorio/patrones/trailing_retroceso_alto.py`. Se comprueba una
      vez al dia, con el high/low de la propia vela diaria, ANTES del
      stop/objetivo del dia (si ambos se tocan la misma vela, el trailing
      manda, igual que en el laboratorio). CONFIRMADO 18-sept-2026 bajo el
      stop/objetivo real de produccion (K_ATR_STOP=1.2/R_FIJO=4.0):
      activacion=5%, retroceso=67.5% (NO 92.5% -- ese numero era del
      stop/objetivo viejo, ver arriba) gana en 8/8 combinaciones de ajuste +
      holdout. Es este mecanismo, no el condicional a 4h, el que usa
      `ejecucion/cuenta_referencia.py`."""
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None

    def _cerrar(i: int, precio_salida: float, motivo: str) -> TradeSalida:
        retorno = (precio_salida / precio_entrada - 1) * 100
        if direccion == "corto":
            retorno = -retorno
        return TradeSalida(idx_entrada, i, precio_entrada, precio_salida, motivo, round(retorno, 3),
                            fraccion_restante=fraccion_restante, idx_venta_parcial=idx_venta_parcial,
                            precio_venta_parcial=precio_venta_parcial)

    usa_trailing = atr_valor is not None and k_atr_trailing is not None
    usa_venta_parcial = venta_parcial_umbral is not None and venta_parcial_fraccion is not None
    usa_confirmacion = senal_con_confirmacion is not None and serie_confirmacion is not None \
        and caida_relativa_confirmacion is not None
    usa_trailing_retroceso = df4h is not None and indice_4h_inicio is not None and indice_4h_fin is not None \
        and trailing_activacion_pct is not None and trailing_retroceso_pct is not None
    usa_trailing_diario = not usa_trailing_retroceso \
        and trailing_activacion_pct is not None and trailing_retroceso_pct is not None
    extremo_favorable = precio_entrada
    stop_efectivo = niveles.stop
    fraccion_restante = 1.0
    idx_venta_parcial: int | None = None
    precio_venta_parcial: float | None = None
    extremo_confirmacion = 0.0

    if usa_trailing_retroceso:
        high4h = df4h["high"].to_numpy()
        low4h = df4h["low"].to_numpy()
        close4h = df4h["close"].to_numpy()
    mejor_ganancia_trailing_pct = 0.0
    racha_persistente_trailing = 0

    contador_persistente = 0
    for i in range(idx_entrada + 1, fin + 1):
        if usa_venta_parcial and idx_venta_parcial is None:
            ganancia_pct = (high[i] - precio_entrada) / precio_entrada if direccion == "largo" \
                else (precio_entrada - low[i]) / precio_entrada
            if ganancia_pct >= venta_parcial_umbral:
                idx_venta_parcial = i
                precio_venta_parcial = precio_entrada * (1 + venta_parcial_umbral) if direccion == "largo" \
                    else precio_entrada * (1 - venta_parcial_umbral)
                fraccion_restante = 1.0 - venta_parcial_fraccion

        if usa_trailing:
            if direccion == "largo":
                extremo_favorable = max(extremo_favorable, high[i])
                avance_pct = extremo_favorable / precio_entrada - 1
                supera_colchon = avance_pct >= (cushion_pct_minimo or 0.0)
                if extremo_favorable > precio_entrada and supera_colchon:  # solo cuenta si de verdad hay avance a favor
                    stop_efectivo = max(stop_efectivo, extremo_favorable - k_atr_trailing * atr_valor)
            else:
                extremo_favorable = min(extremo_favorable, low[i])
                avance_pct = 1 - extremo_favorable / precio_entrada
                supera_colchon = avance_pct >= (cushion_pct_minimo or 0.0)
                if extremo_favorable < precio_entrada and supera_colchon:
                    stop_efectivo = min(stop_efectivo, extremo_favorable + k_atr_trailing * atr_valor)

        if usa_trailing_retroceso:
            velas_del_dia = range(indice_4h_inicio[i], indice_4h_fin[i])
            n_velas_dia = indice_4h_fin[i] - indice_4h_inicio[i]
            for pos_local, j in enumerate(velas_del_dia):
                if direccion == "largo":
                    ganancia_pico_pct = (high4h[j] - precio_entrada) / precio_entrada
                    ganancia_actual_pct = (close4h[j] - precio_entrada) / precio_entrada
                else:
                    ganancia_pico_pct = (precio_entrada - low4h[j]) / precio_entrada
                    ganancia_actual_pct = (precio_entrada - close4h[j]) / precio_entrada
                mejor_ganancia_trailing_pct = max(mejor_ganancia_trailing_pct, ganancia_pico_pct)

                es_ultima_vela_del_dia = pos_local == n_velas_dia - 1
                modo_intradia = trailing_umbral_intradia_pct is None \
                    or mejor_ganancia_trailing_pct >= trailing_umbral_intradia_pct
                comprobar_ahora = modo_intradia or es_ultima_vela_del_dia

                if comprobar_ahora and trailing_retroceso_pct < 999 and mejor_ganancia_trailing_pct >= trailing_activacion_pct:
                    listón = mejor_ganancia_trailing_pct * (1 - trailing_retroceso_pct)
                    rompe = ganancia_actual_pct <= listón
                    if modo_intradia:
                        racha_persistente_trailing = racha_persistente_trailing + 1 if rompe else 0
                        dispara = racha_persistente_trailing >= trailing_velas_persistencia
                    else:
                        dispara = rompe
                    if dispara:
                        return _cerrar(i, close4h[j], "trailing_retroceso_alto")

                if direccion == "largo":
                    toca_stop_4h = low4h[j] <= stop_efectivo
                    toca_objetivo_4h = high4h[j] >= niveles.objetivo
                else:
                    toca_stop_4h = high4h[j] >= stop_efectivo
                    toca_objetivo_4h = low4h[j] <= niveles.objetivo
                if toca_stop_4h:
                    return _cerrar(i, stop_efectivo, "stop")
                if toca_objetivo_4h:
                    return _cerrar(i, niveles.objetivo, "objetivo")
        else:
            if usa_trailing_diario:
                if direccion == "largo":
                    ganancia_pico_pct = (high[i] - precio_entrada) / precio_entrada
                    ganancia_actual_pct = (close[i] - precio_entrada) / precio_entrada
                else:
                    ganancia_pico_pct = (precio_entrada - low[i]) / precio_entrada
                    ganancia_actual_pct = (precio_entrada - close[i]) / precio_entrada
                mejor_ganancia_trailing_pct = max(mejor_ganancia_trailing_pct, ganancia_pico_pct)
                if trailing_retroceso_pct < 999 and mejor_ganancia_trailing_pct >= trailing_activacion_pct:
                    listón = mejor_ganancia_trailing_pct * (1 - trailing_retroceso_pct)
                    if ganancia_actual_pct <= listón:
                        return _cerrar(i, close[i], "trailing_retroceso_alto")

            if direccion == "largo":
                toca_stop = low[i] <= stop_efectivo
                toca_objetivo = high[i] >= niveles.objetivo
            else:
                toca_stop = high[i] >= stop_efectivo
                toca_objetivo = low[i] <= niveles.objetivo

            if toca_stop:
                motivo = "stop_trailing" if usa_trailing and stop_efectivo != niveles.stop else "stop"
                return _cerrar(i, stop_efectivo, motivo)
            if toca_objetivo:
                return _cerrar(i, niveles.objetivo, "objetivo")
        if senal_externa is not None and senal_externa[i]:
            return _cerrar(i, close[i], "senal_externa")
        if usa_confirmacion:
            valor = serie_confirmacion[i]
            if not np.isnan(valor):
                if direccion == "largo":
                    extremo_confirmacion = max(extremo_confirmacion, valor)
                    listón = extremo_confirmacion * (1 - caida_relativa_confirmacion)
                    honra = extremo_confirmacion <= 0 or valor <= listón
                else:
                    extremo_confirmacion = min(extremo_confirmacion, valor)
                    listón = extremo_confirmacion * (1 - caida_relativa_confirmacion)
                    honra = extremo_confirmacion >= 0 or valor >= listón
                if senal_con_confirmacion[i] and honra:
                    return _cerrar(i, close[i], "senal_confirmada")
            elif senal_con_confirmacion[i]:
                return _cerrar(i, close[i], "senal_confirmada")
        if prob_contraria is not None:
            en_ganancia = (close[i] > precio_entrada) if direccion == "largo" else (close[i] < precio_entrada)
            umbral_efectivo = (
                umbral_contraria_en_ganancia
                if en_ganancia and umbral_contraria_en_ganancia is not None
                else umbral_contraria
            )
            if prob_contraria[i] >= umbral_efectivo:
                return _cerrar(i, close[i], "senal_externa")
        if condicion_persistente is not None:
            contador_persistente = contador_persistente + 1 if condicion_persistente[i] else 0
            if contador_persistente >= dias_persistencia:
                return _cerrar(i, close[i], "condicion_persistente")

    return _cerrar(fin, close[fin], "tiempo_maximo")
