"""
Bandera / banderin -- ORQUESTA motores ya existentes en vez de reimplementar
nada desde cero (idea del usuario, 11-sept-2026: "una bandera realmente es
una caida de recuperacion mas seguida de canal ascendente o descendente").

- **Mastil bajista** = la misma pierna pico->fondo que ya detecta
  `caida_recuperacion.py`. Se reutiliza esa funcion TAL CUAL, pero con
  `peso_recuperacion=0` y `peso_redondeo=0` -- esas 2 dimensiones describen
  como es el REBOTE tras el fondo, y aqui el "rebote" no es un simple
  bounce sino una consolidacion en canal/triangulo, que se puntua aparte.
  Las 5 dimensiones que SI se reutilizan (caida, velocidad, mecha,
  desaceleracion, arranque_brusco) describen el mastil en si mismo, que es
  identico se convierta luego en recuperacion simple o en bandera.
- **Mastil alcista** = espejo con `subida_correccion.py` (mismo mecanismo,
  `peso_correccion=0`, `peso_redondeo=0`).
- **Bandera bajista**: tras el mastil bajista, un `canal_flexible.
  detectar_ascendente` CORTO (consolidacion inclinada EN CONTRA de la
  caida) que empieza cerca de `idx_fondo` del mastil.
- **Bandera alcista**: tras el mastil alcista, un `canal_flexible.
  detectar_descendente` corto que empieza cerca de `idx_techo` del mastil.
- **Banderin** (bajista o alcista): igual, pero la consolidacion es un
  `triangulo_flexible.detectar_simetrico` corto (banderin = converge, no
  va en canal paralelo -- ver docstring de triangulo_flexible.py sobre la
  distincion cuña/triangulo/banderin).

Dos dimensiones NUEVAS, propias de la orquestacion (no existian en ningun
motor previo, porque solo tienen sentido al ENCADENAR dos patrones):
- `score_proporcion`: la consolidacion debe ser proporcionalmente CORTA
  frente al mastil -- un mastil de 5 dias con una consolidacion de 60 no
  es una bandera, son dos patrones sin relacion real.
- `score_enganche`: la consolidacion debe empezar CERCA de donde termina
  el mastil (decaimiento continuo con la distancia en dias, nunca un corte
  duro).

Combinacion final: media geometrica ponderada de 4 componentes
(score_mastil, score_consolidacion, score_proporcion, score_enganche) --
mismo mecanismo que canal/triangulo/triple suelo-techo.

Solo se construye el DETECTOR -- ninguna prueba de rentabilidad todavia.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import laboratorio.patrones.caida_recuperacion as cr
import laboratorio.patrones.subida_correccion as sc
import laboratorio.patrones.canal_flexible as cf
import laboratorio.patrones.triangulo_flexible as tf


@dataclass
class CandidatoBanderaBanderin:
    tipo: str  # "bandera_bajista" | "bandera_alcista" | "banderin_bajista" | "banderin_alcista"
    idx_inicio_mastil: int
    idx_fin_mastil: int
    idx_inicio_consolidacion: int
    idx_fin_consolidacion: int
    probabilidad_forma: float
    score_mastil: float
    score_consolidacion: float
    score_proporcion: float
    score_enganche: float
    dias_mastil: int
    dias_consolidacion: int
    # Geometria completa -- solo para poder DIBUJAR el patron entero (mastil +
    # consolidacion), no aportan nada a la puntuacion. La consolidacion tiene
    # 4 puntos de anclaje (identico a CandidatoCanal/CandidatoTriangulo).
    precio_inicio_mastil: float
    precio_fin_mastil: float
    idx_pico1_consol: int
    idx_fondo2_consol: int
    precio_fondo1_consol: float
    precio_pico1_consol: float
    precio_fondo2_consol: float
    precio_pico2_consol: float


# Pesos reenviados a caida_recuperacion.detectar / subida_correccion.detectar.
# 15-sept-2026: `caida_recuperacion.detectar()` ya NO acepta peso_recuperacion/
# peso_redondeo (se retiraron por no ser causales, ver observacion 0021) --
# el mastil bajista usa directamente el grid causal de 5 dimensiones.
PESOS_MASTIL_BAJISTA = dict(
    peso_caida=0.30, peso_velocidad=0.30,
    peso_mecha=0.20, peso_desaceleracion=0.15, peso_arranque=0.05,
)
PESOS_MASTIL_ALCISTA = dict(
    peso_subida=0.30, peso_velocidad=0.30, peso_correccion=0.0,
    peso_mecha=0.20, peso_desaceleracion=0.15, peso_redondeo=0.0, peso_arranque=0.05,
)


def _detectar(
    df: pd.DataFrame,
    tipo: str,  # "bandera_bajista" | "bandera_alcista" | "banderin_bajista" | "banderin_alcista"
    dias_min_mastil: int = 3,
    dias_max_mastil: int = 20,
    dias_min_consolidacion: int = 5,
    dias_max_consolidacion: int = 30,
    ventana_busqueda_enganche_dias: int = 10,
    tolerancia_enganche_dias: float = 3.0,
    ratio_proporcion_ideal: float = 2.0,
    ratio_proporcion_tolerancia_exceso: float = 2.0,
    peso_mastil: float = 0.40,
    peso_consolidacion: float = 0.35,
    peso_proporcion: float = 0.15,
    peso_enganche: float = 0.10,
) -> list[CandidatoBanderaBanderin]:
    bajista = tipo.endswith("bajista")
    es_banderin = tipo.startswith("banderin")

    if bajista:
        mastiles = cr.detectar(df, ventana_min_dias=dias_min_mastil, ventana_max_dias=dias_max_mastil,
                                **PESOS_MASTIL_BAJISTA)
        anchor_attr = "idx_fondo"
        inicio_attr = "idx_pico"
    else:
        mastiles = sc.detectar(df, ventana_min_dias=dias_min_mastil, ventana_max_dias=dias_max_mastil,
                                **PESOS_MASTIL_ALCISTA)
        anchor_attr = "idx_techo"
        inicio_attr = "idx_valle"

    if es_banderin:
        consolidaciones = tf.detectar_simetrico(df, dias_min_tramo=dias_min_consolidacion,
                                                  dias_max_tramo=dias_max_consolidacion)
    elif bajista:
        consolidaciones = cf.detectar_ascendente(df, dias_min_tramo=dias_min_consolidacion,
                                                   dias_max_tramo=dias_max_consolidacion)
    else:
        consolidaciones = cf.detectar_descendente(df, dias_min_tramo=dias_min_consolidacion,
                                                    dias_max_tramo=dias_max_consolidacion)

    if not mastiles or not consolidaciones:
        return []

    close = df["close"].to_numpy()

    por_fin: dict[int, list[tuple]] = {}
    for m in mastiles:
        anchor = getattr(m, anchor_attr)
        inicio_mastil = getattr(m, inicio_attr)
        dias_mastil = anchor - inicio_mastil
        if dias_mastil <= 0:
            continue

        candidatas_cercanas = [c for c in consolidaciones
                                if abs(c.idx_fondo1 - anchor) <= ventana_busqueda_enganche_dias]
        if not candidatas_cercanas:
            continue

        for c in candidatas_cercanas:
            dias_consolidacion = c.idx_pico2 - c.idx_fondo1
            if dias_consolidacion <= 0:
                continue

            gap_enganche = abs(c.idx_fondo1 - anchor)
            score_enganche = float(np.exp(-gap_enganche / tolerancia_enganche_dias))

            ratio = dias_consolidacion / dias_mastil
            if ratio <= ratio_proporcion_ideal:
                score_proporcion = 1.0
            else:
                exceso = ratio - ratio_proporcion_ideal
                score_proporcion = float(np.exp(-exceso / ratio_proporcion_tolerancia_exceso))

            score_mastil = m.probabilidad_forma
            score_consolidacion = c.probabilidad_forma

            score_mastil_safe = max(score_mastil, 1e-3)
            score_consolidacion_safe = max(score_consolidacion, 1e-3)
            score_proporcion_safe = max(score_proporcion, 1e-3)
            score_enganche_safe = max(score_enganche, 1e-3)
            probabilidad_forma = (score_mastil_safe ** peso_mastil
                                   * score_consolidacion_safe ** peso_consolidacion
                                   * score_proporcion_safe ** peso_proporcion
                                   * score_enganche_safe ** peso_enganche)

            opcion = (inicio_mastil, anchor, c.idx_fondo1, c.idx_pico2,
                      score_mastil, score_consolidacion, score_proporcion, score_enganche,
                      dias_mastil, dias_consolidacion, probabilidad_forma,
                      c.idx_pico1, c.idx_fondo2, c.precio_fondo1, c.precio_pico1,
                      c.precio_fondo2, c.precio_pico2)
            por_fin.setdefault(c.idx_pico2, []).append(opcion)

    candidatos: list[CandidatoBanderaBanderin] = []
    for idx_fin, opciones in por_fin.items():
        opciones.sort(key=lambda o: o[10], reverse=True)
        (idx_inicio_mastil, idx_fin_mastil, idx_inicio_consolidacion, idx_fin_consolidacion,
         score_mastil, score_consolidacion, score_proporcion, score_enganche,
         dias_mastil, dias_consolidacion, probabilidad_forma,
         idx_pico1_consol, idx_fondo2_consol, precio_fondo1_consol, precio_pico1_consol,
         precio_fondo2_consol, precio_pico2_consol) = opciones[0]

        candidatos.append(CandidatoBanderaBanderin(
            tipo=tipo, idx_inicio_mastil=idx_inicio_mastil, idx_fin_mastil=idx_fin_mastil,
            idx_inicio_consolidacion=idx_inicio_consolidacion, idx_fin_consolidacion=idx_fin_consolidacion,
            probabilidad_forma=round(probabilidad_forma, 3),
            score_mastil=round(score_mastil, 3), score_consolidacion=round(score_consolidacion, 3),
            score_proporcion=round(score_proporcion, 3), score_enganche=round(score_enganche, 3),
            dias_mastil=dias_mastil, dias_consolidacion=dias_consolidacion,
            precio_inicio_mastil=round(float(close[idx_inicio_mastil]), 6),
            precio_fin_mastil=round(float(close[idx_fin_mastil]), 6),
            idx_pico1_consol=idx_pico1_consol, idx_fondo2_consol=idx_fondo2_consol,
            precio_fondo1_consol=precio_fondo1_consol, precio_pico1_consol=precio_pico1_consol,
            precio_fondo2_consol=precio_fondo2_consol, precio_pico2_consol=precio_pico2_consol,
        ))

    return candidatos


def detectar_bandera_bajista(df: pd.DataFrame, **kwargs) -> list[CandidatoBanderaBanderin]:
    return _detectar(df, "bandera_bajista", **kwargs)


def detectar_bandera_alcista(df: pd.DataFrame, **kwargs) -> list[CandidatoBanderaBanderin]:
    return _detectar(df, "bandera_alcista", **kwargs)


def detectar_banderin_bajista(df: pd.DataFrame, **kwargs) -> list[CandidatoBanderaBanderin]:
    return _detectar(df, "banderin_bajista", **kwargs)


def detectar_banderin_alcista(df: pd.DataFrame, **kwargs) -> list[CandidatoBanderaBanderin]:
    return _detectar(df, "banderin_alcista", **kwargs)


# (peso_mastil, peso_consolidacion, peso_proporcion, peso_enganche) -- suman 1.0.
# Mismo mecanismo que el resto de detectores: varias configs con distinta
# dominancia para comprobar que el grid de pesos SI discrimina.
PESOS_FORMA = [
    (0.40, 0.35, 0.15, 0.10),  # equilibrado -- default
    (0.70, 0.15, 0.10, 0.05),  # mastil dominante -- "que el impulso sea fuerte" importa mas
    (0.15, 0.70, 0.10, 0.05),  # consolidacion dominante -- "que el canal/triangulo sea limpio" importa mas
    (0.15, 0.15, 0.55, 0.15),  # proporcion dominante -- que sea corta de verdad frente al mastil
    (0.15, 0.15, 0.15, 0.55),  # enganche casi absoluto -- que empiece justo donde termina el mastil
]
