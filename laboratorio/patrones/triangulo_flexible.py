"""
Patron "triangulo" (compresion), idea del usuario (11-sept-2026): lo
contrario de un canal (`canal_flexible.py`) -- en vez de dos lineas
(soporte y resistencia) razonablemente PARALELAS, aqui CONVERGEN: el
hueco entre ellas se va cerrando con el tiempo. Misma estructura minima
que canal (2 fondos + 2 picos alternados, fondo1 < pico1 < fondo2 <
pico2) y mismo mecanismo de deteccion, deduplicacion por idx_pico2,
volumen y contencion -- solo cambian 2 de las 5 dimensiones de
puntuacion, confirmado con el usuario (11-sept-2026, "tiene todo el
sentido del mundo, que sea muy similar al del canal"):

- "paralelismo" (premiar pendientes PARECIDAS) -> "convergencia"
  (premiar que el hueco entre las lineas al FINAL del tramo sea menor
  que al PRINCIPIO).
- "consistencia de ancho" (premiar ancho CONSTANTE) -> "consistencia de
  la convergencia" (premiar que el estrechamiento sea monotono y suave,
  no a bandazos).

Pendiente y contencion se quedan con el mismo mecanismo que canal
(contencion sigue siendo imprescindible: un triangulo tambien puede
romperse por dentro aunque los 4 puntos de anclaje converjan bien).

Tres variantes (mismo patron de llamada que canal_flexible.py):
- ascendente: el soporte sube, la resistencia se mantiene mas plana.
- descendente: la resistencia baja, el soporte se mantiene mas plano.
- simetrico: las dos lineas se mueven hacia el centro (soporte sube,
  resistencia baja), sin sesgo de direccion.

Solo se construye el DETECTOR (fase de deteccion) -- ninguna prueba de
rentabilidad todavia, mismo criterio que el resto del proyecto.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CandidatoTriangulo:
    idx_fondo1: int
    idx_pico1: int
    idx_fondo2: int
    idx_pico2: int
    precio_fondo1: float
    precio_pico1: float
    precio_fondo2: float
    precio_pico2: float
    probabilidad_forma: float  # 5 dimensiones de forma -- sin volumen
    pendiente_soporte_pct_dia: float
    pendiente_resistencia_pct_dia: float
    gap_inicial_pct: float
    gap_final_pct: float
    consistencia_convergencia: float  # 1.0 = estrechamiento perfectamente monotono
    peor_excursion_pct: float  # cuanto se salio el precio real de la banda, en el peor dia
    dias_total: int
    n_alternativas_decentes: int
    volumen_ratio: float
    score_volumen: float


def _detectar_fondos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Minimos locales causales -- identico al resto de detectores."""
    n = len(close)
    fondos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.min():
            fondos.append(i)
    return fondos


def _detectar_picos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Maximos locales causales -- identico al resto de detectores."""
    n = len(close)
    picos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.max():
            picos.append(i)
    return picos


def _detectar(
    df: pd.DataFrame,
    direccion: str,
    dias_min_tramo: int,
    dias_max_tramo: int,
    pendiente_ideal_pct_dia: float,
    convergencia_tolerancia_pct_dia: float,
    consistencia_tolerancia: float,
    contencion_tolerancia_pct: float,
    magnitud_ideal_pct: float,
    magnitud_tolerancia_exceso_pct: float,
    peso_pendiente: float,
    peso_convergencia: float,
    peso_consistencia: float,
    peso_contencion: float,
    peso_magnitud: float,
    vol_mult_ideal: float,
    dias_ventana_volumen: int,
) -> list[CandidatoTriangulo]:
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy() if "volume" in df.columns else None
    vol_media = df["volume"].rolling(30).mean().to_numpy() if volume is not None else None

    fondos = _detectar_fondos_simple(close)
    picos = _detectar_picos_simple(close)
    n = len(close)

    ascendente = direccion == "ascendente"
    descendente = direccion == "descendente"
    simetrico = direccion == "simetrico"

    por_pico2: dict[int, list[tuple]] = {}
    for i, idx_fondo1 in enumerate(fondos):
        precio_fondo1 = close[idx_fondo1]
        for idx_fondo2 in fondos[i + 1:]:
            dias_tramo = idx_fondo2 - idx_fondo1
            if dias_tramo > dias_max_tramo:
                break
            if dias_tramo < dias_min_tramo:
                continue
            precio_fondo2 = close[idx_fondo2]

            # requisito estructural de direccion, igual de flexible que en
            # canal: ascendente exige soporte subiendo, descendente no
            # exige nada al soporte (lo decide la resistencia), simetrico
            # exige soporte subiendo Y resistencia bajando (ver mas abajo,
            # tras calcular picos).
            if ascendente and precio_fondo2 <= precio_fondo1:
                continue
            if simetrico and precio_fondo2 <= precio_fondo1:
                continue

            pico1_opts = [p for p in picos if idx_fondo1 < p < idx_fondo2]
            if not pico1_opts:
                continue
            fin_busqueda_pico2 = idx_fondo1 + dias_max_tramo
            pico2_opts = [p for p in picos if idx_fondo2 < p <= min(fin_busqueda_pico2, n - 1)]
            if not pico2_opts:
                continue

            opciones = []
            for idx_pico1 in pico1_opts:
                precio_pico1 = close[idx_pico1]
                if precio_pico1 <= max(precio_fondo1, precio_fondo2):
                    continue  # el "techo" del tramo debe superar a los dos fondos que lo rodean
                for idx_pico2 in pico2_opts:
                    precio_pico2 = close[idx_pico2]
                    if descendente and precio_pico2 >= precio_pico1:
                        continue
                    if simetrico and precio_pico2 >= precio_pico1:
                        continue

                    dias_soporte = idx_fondo2 - idx_fondo1
                    dias_resistencia = idx_pico2 - idx_pico1
                    pend_soporte = (precio_fondo2 - precio_fondo1) / precio_fondo1 / dias_soporte * 100
                    pend_resistencia = (precio_pico2 - precio_pico1) / precio_pico1 / dias_resistencia * 100

                    slope_soporte_abs = (precio_fondo2 - precio_fondo1) / dias_soporte
                    slope_resistencia_abs = (precio_pico2 - precio_pico1) / dias_resistencia

                    def soporte_line(x: int) -> float:
                        return precio_fondo1 + slope_soporte_abs * (x - idx_fondo1)

                    def resistencia_line(x: int) -> float:
                        return precio_pico1 + slope_resistencia_abs * (x - idx_pico1)

                    gaps = [
                        resistencia_line(idx_fondo1) - precio_fondo1,
                        precio_pico1 - soporte_line(idx_pico1),
                        resistencia_line(idx_fondo2) - precio_fondo2,
                        precio_pico2 - soporte_line(idx_pico2),
                    ]
                    if any(g <= 0 for g in gaps):
                        continue  # las lineas se cruzan antes de tiempo -- no es un triangulo valido

                    precio_medio = float(np.mean([precio_fondo1, precio_pico1, precio_fondo2, precio_pico2]))

                    # gap real de la banda al INICIO (idx_fondo1) y al FINAL
                    # (idx_pico2) del tramo -- no en los 4 puntos de anclaje
                    # sueltos (esos pueden no coincidir con los extremos
                    # temporales del tramo), en las fechas limite reales.
                    gap_inicial = resistencia_line(idx_fondo1) - soporte_line(idx_fondo1)
                    gap_final = resistencia_line(idx_pico2) - soporte_line(idx_pico2)
                    if gap_inicial <= 0 or gap_final <= 0:
                        continue  # las lineas ya se cruzaron dentro del tramo -- invalido
                    gap_inicial_pct = gap_inicial / precio_medio * 100
                    gap_final_pct = gap_final / precio_medio * 100

                    # contencion: identica a canal_flexible.py -- recorre el
                    # camino real de precio y penaliza salirse de la banda
                    # (que aqui converge, no es constante).
                    xs = np.arange(idx_fondo1, idx_pico2 + 1)
                    banda_baja = precio_fondo1 + slope_soporte_abs * (xs - idx_fondo1)
                    banda_alta = precio_pico1 + slope_resistencia_abs * (xs - idx_pico1)
                    precios_tramo = close[idx_fondo1:idx_pico2 + 1]
                    excursion_baja = np.maximum(0.0, banda_baja - precios_tramo)
                    excursion_alta = np.maximum(0.0, precios_tramo - banda_alta)
                    peor_excursion_pct = float(np.max(excursion_baja + excursion_alta)) / precio_medio * 100

                    # pendiente: igual mecanismo que canal -- "cuanto se
                    # mueve la linea que SI tiene que moverse" (para
                    # ascendente/descendente la linea relevante es la que
                    # define la direccion; para simetrico, la media de
                    # ambas, igual que en canal).
                    if ascendente:
                        pendiente_relevante_abs = abs(pend_soporte)
                    elif descendente:
                        pendiente_relevante_abs = abs(pend_resistencia)
                    else:  # simetrico
                        pendiente_relevante_abs = (abs(pend_soporte) + abs(pend_resistencia)) / 2
                    score_pendiente = min(pendiente_relevante_abs / pendiente_ideal_pct_dia, 1.0)

                    # convergencia (sustituye a "paralelismo" de canal): en
                    # vez de premiar pendientes parecidas, premia que el
                    # hueco se haya estrechado de verdad entre el principio
                    # y el final del tramo -- tasa de estrechamiento por
                    # dia, comparada con una tolerancia (igual mecanismo
                    # continuo que el resto: nunca 0 exacto).
                    dias_totales = idx_pico2 - idx_fondo1
                    estrechamiento_pct_dia = (gap_inicial_pct - gap_final_pct) / dias_totales
                    if estrechamiento_pct_dia <= 0:
                        # el hueco se mantiene igual o crece -- no converge,
                        # penalizado con fuerza pero de forma continua
                        score_convergencia = float(np.exp(estrechamiento_pct_dia / convergencia_tolerancia_pct_dia))
                    else:
                        score_convergencia = min(estrechamiento_pct_dia / convergencia_tolerancia_pct_dia, 1.0)

                    # consistencia de la convergencia (sustituye a
                    # "consistencia de ancho" de canal): mide si el
                    # estrechamiento es monotono y suave, no a bandazos --
                    # se evalua el gap real de la banda en cada uno de los
                    # 4 puntos de anclaje y se comprueba que decrece de
                    # forma aproximadamente lineal (mismo principio que el
                    # coeficiente de variacion en canal, aplicado aqui a
                    # los incrementos entre gaps consecutivos).
                    gaps_puntos = np.array(gaps)
                    incrementos = np.diff(gaps_puntos)
                    if np.mean(np.abs(gaps_puntos)) > 0:
                        cv_incrementos = float(np.std(incrementos) / (np.mean(np.abs(gaps_puntos))))
                    else:
                        cv_incrementos = 1.0
                    consistencia_convergencia = float(np.exp(-abs(cv_incrementos) / consistencia_tolerancia))
                    score_consistencia = consistencia_convergencia
                    score_contencion = float(np.exp(-peor_excursion_pct / contencion_tolerancia_pct))

                    # magnitud: dimension nueva respecto a canal -- un
                    # triangulo con un gap_inicial minusculo apenas es una
                    # compresion real (ya empezaba casi cerrado), premia
                    # que el gap de partida sea sustancial antes de
                    # cerrarse.
                    #
                    # **Bug real encontrado el 11-sept-2026, mismo patron que
                    # el bug 2 de canal_flexible.py (ancho sin techo)**: la
                    # version anterior premiaba un gap_inicial grande SIN
                    # LIMITE (score = min(gap/algo, 1.0), solo suelo). El
                    # candidato "simetrico" mejor puntuado en todo el
                    # historico de BTC (0.946) resulto ser el techo de la
                    # mania de diciembre 2017 (fondo1=$8.020 23-nov-2017,
                    # pico1=$19.103 16-dic-2017, la subida parabolica previa
                    # al maximo historico) -- no es una compresion, es la
                    # subida-y-caida de una burbuja con un gap_inicial de
                    # 94% del precio, premiado como si fuera ideal. Corregido
                    # con puntuacion en PICO (identica logica a score_ancho
                    # en canal): premia acercarse a un tamaño de gap
                    # razonable y PENALIZA de forma continua pasarse de
                    # largo, en vez de premiar sin techo.
                    if gap_inicial_pct <= magnitud_ideal_pct:
                        score_magnitud = gap_inicial_pct / magnitud_ideal_pct
                    else:
                        exceso_magnitud = gap_inicial_pct - magnitud_ideal_pct
                        score_magnitud = float(np.exp(-exceso_magnitud / magnitud_tolerancia_exceso_pct))

                    score_pendiente_safe = max(score_pendiente, 1e-3)
                    score_convergencia_safe = max(score_convergencia, 1e-3)
                    score_consistencia_safe = max(score_consistencia, 1e-3)
                    score_contencion_safe = max(score_contencion, 1e-3)
                    score_magnitud_safe = max(score_magnitud, 1e-3)
                    prob_forma = (score_pendiente_safe ** peso_pendiente
                                  * score_convergencia_safe ** peso_convergencia
                                  * score_consistencia_safe ** peso_consistencia
                                  * score_contencion_safe ** peso_contencion
                                  * score_magnitud_safe ** peso_magnitud)

                    opciones.append((idx_fondo1, idx_pico1, idx_fondo2, idx_pico2,
                                      precio_fondo1, precio_pico1, precio_fondo2, precio_pico2,
                                      pend_soporte, pend_resistencia, gap_inicial_pct, gap_final_pct,
                                      consistencia_convergencia, peor_excursion_pct, prob_forma))

            for o in opciones:
                por_pico2.setdefault(o[3], []).append(o)

    candidatos: list[CandidatoTriangulo] = []
    for idx_pico2, opciones in por_pico2.items():
        opciones.sort(key=lambda o: o[14], reverse=True)
        (idx_fondo1, idx_pico1, idx_fondo2, _idx_pico2, precio_fondo1, precio_pico1,
         precio_fondo2, precio_pico2, pend_soporte, pend_resistencia, gap_inicial_pct,
         gap_final_pct, consistencia_convergencia, peor_excursion_pct, probabilidad_forma) = opciones[0]
        n_decentes = sum(1 for o in opciones if o[14] >= 0.3) - 1

        volumen_ratio = 0.0
        if volume is not None:
            fin_v = min(idx_pico2 + dias_ventana_volumen, n)
            tramo_vol = volume[idx_pico2:fin_v]
            tramo_media = vol_media[idx_pico2:fin_v]
            validos = ~np.isnan(tramo_media) & (tramo_media > 0)
            if validos.any():
                volumen_ratio = float((tramo_vol[validos] / tramo_media[validos]).max())
        score_volumen = min(volumen_ratio / vol_mult_ideal, 1.0)

        candidatos.append(CandidatoTriangulo(
            idx_fondo1=idx_fondo1, idx_pico1=idx_pico1, idx_fondo2=idx_fondo2, idx_pico2=idx_pico2,
            precio_fondo1=round(float(precio_fondo1), 6), precio_pico1=round(float(precio_pico1), 6),
            precio_fondo2=round(float(precio_fondo2), 6), precio_pico2=round(float(precio_pico2), 6),
            probabilidad_forma=round(probabilidad_forma, 3),
            pendiente_soporte_pct_dia=round(pend_soporte, 3),
            pendiente_resistencia_pct_dia=round(pend_resistencia, 3),
            gap_inicial_pct=round(gap_inicial_pct, 2), gap_final_pct=round(gap_final_pct, 2),
            consistencia_convergencia=round(consistencia_convergencia, 3),
            peor_excursion_pct=round(peor_excursion_pct, 2),
            dias_total=idx_pico2 - idx_fondo1, n_alternativas_decentes=n_decentes,
            volumen_ratio=round(volumen_ratio, 3), score_volumen=round(score_volumen, 3),
        ))

    return candidatos


def detectar_ascendente(
    df: pd.DataFrame,
    dias_min_tramo: int = 10,
    dias_max_tramo: int = 60,
    pendiente_ideal_pct_dia: float = 1.0,
    convergencia_tolerancia_pct_dia: float = 0.3,
    consistencia_tolerancia: float = 0.5,
    contencion_tolerancia_pct: float = 10.0,
    magnitud_ideal_pct: float = 15.0,
    magnitud_tolerancia_exceso_pct: float = 15.0,
    peso_pendiente: float = 0.05,
    peso_convergencia: float = 0.30,
    peso_consistencia: float = 0.15,
    peso_contencion: float = 0.35,
    peso_magnitud: float = 0.15,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoTriangulo]:
    return _detectar(df, "ascendente", dias_min_tramo, dias_max_tramo, pendiente_ideal_pct_dia,
                      convergencia_tolerancia_pct_dia, consistencia_tolerancia, contencion_tolerancia_pct,
                      magnitud_ideal_pct, magnitud_tolerancia_exceso_pct,
                      peso_pendiente, peso_convergencia, peso_consistencia, peso_contencion, peso_magnitud,
                      vol_mult_ideal, dias_ventana_volumen)


def detectar_descendente(
    df: pd.DataFrame,
    dias_min_tramo: int = 10,
    dias_max_tramo: int = 60,
    pendiente_ideal_pct_dia: float = 1.0,
    convergencia_tolerancia_pct_dia: float = 0.3,
    consistencia_tolerancia: float = 0.5,
    contencion_tolerancia_pct: float = 10.0,
    magnitud_ideal_pct: float = 15.0,
    magnitud_tolerancia_exceso_pct: float = 15.0,
    peso_pendiente: float = 0.05,
    peso_convergencia: float = 0.30,
    peso_consistencia: float = 0.15,
    peso_contencion: float = 0.35,
    peso_magnitud: float = 0.15,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoTriangulo]:
    return _detectar(df, "descendente", dias_min_tramo, dias_max_tramo, pendiente_ideal_pct_dia,
                      convergencia_tolerancia_pct_dia, consistencia_tolerancia, contencion_tolerancia_pct,
                      magnitud_ideal_pct, magnitud_tolerancia_exceso_pct,
                      peso_pendiente, peso_convergencia, peso_consistencia, peso_contencion, peso_magnitud,
                      vol_mult_ideal, dias_ventana_volumen)


def detectar_simetrico(
    df: pd.DataFrame,
    dias_min_tramo: int = 10,
    dias_max_tramo: int = 60,
    pendiente_ideal_pct_dia: float = 1.0,
    convergencia_tolerancia_pct_dia: float = 0.3,
    consistencia_tolerancia: float = 0.5,
    contencion_tolerancia_pct: float = 10.0,
    magnitud_ideal_pct: float = 15.0,
    magnitud_tolerancia_exceso_pct: float = 15.0,
    peso_pendiente: float = 0.05,
    peso_convergencia: float = 0.30,
    peso_consistencia: float = 0.15,
    peso_contencion: float = 0.35,
    peso_magnitud: float = 0.15,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoTriangulo]:
    return _detectar(df, "simetrico", dias_min_tramo, dias_max_tramo, pendiente_ideal_pct_dia,
                      convergencia_tolerancia_pct_dia, consistencia_tolerancia, contencion_tolerancia_pct,
                      magnitud_ideal_pct, magnitud_tolerancia_exceso_pct,
                      peso_pendiente, peso_convergencia, peso_consistencia, peso_contencion, peso_magnitud,
                      vol_mult_ideal, dias_ventana_volumen)


# (peso_pendiente, peso_convergencia, peso_consistencia, peso_contencion,
# peso_magnitud) -- suman 1.0. Mismo mecanismo que canal_flexible.py:
# varias configs con distinta dominancia para comprobar que el grid de
# pesos SI cambia que candidato gana.
PESOS_FORMA = [
    (0.05, 0.30, 0.15, 0.35, 0.15),  # equilibrado -- default
    (0.55, 0.10, 0.10, 0.15, 0.10),  # pendiente dominante
    (0.10, 0.55, 0.10, 0.15, 0.10),  # convergencia dominante
    (0.10, 0.10, 0.55, 0.15, 0.10),  # consistencia dominante
    (0.10, 0.10, 0.10, 0.60, 0.10),  # contencion casi absoluta
    (0.10, 0.15, 0.10, 0.15, 0.50),  # magnitud dominante -- compresion grande
]

# (magnitud_ideal_pct, magnitud_tolerancia_exceso_pct) -- rango a probar,
# igual criterio que IDEALES_ANCHO en canal_flexible.py: ninguno de los
# dos es un numero fijo elegido a mano. Pendiente del mismo barrido
# cruzado (ETH ajuste -> BTC/tiempo confirmacion) antes de fijar cual
# generaliza mejor.
IDEALES_MAGNITUD = [
    (8.0, 8.0),    # compresion que arranca estrecha
    (15.0, 15.0),  # el usado como default hasta ahora
    (22.0, 20.0),  # compresion que arranca amplia
    (30.0, 25.0),  # compresion muy amplia, tolerancia laxa
]
