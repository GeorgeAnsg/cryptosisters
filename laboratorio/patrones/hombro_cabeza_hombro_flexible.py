"""
Hombro-cabeza-hombro (H-C-H), variante directa de `triple_techo_flexible.py`
(11-sept-2026, idea del usuario) -- misma estructura de 5 puntos
(pico1->fondo1->pico2->fondo2->pico3), pero en vez de exigir que los 3
picos sean PARECIDOS entre si (triple techo), aqui se exige que el del
medio (la "cabeza") sea claramente MAS ALTO que los otros dos (los
"hombros"), y son los HOMBROS los que deben parecerse entre si.

Dimensiones (7 en total, `probabilidad_forma`):
- simetria_hombros: parecido entre hombro1 (pico1) y hombro2 (pico3) --
  igual mecanismo que "nivel" en triple techo, pero solo entre esos 2
  puntos (la cabeza se puntua aparte, no debe parecerse a los hombros).
- dominancia_cabeza: cuanto sobresale la cabeza sobre el hombro mas alto
  de los dos. Puntuacion en PICO (mismo mecanismo que "ancho" en
  canal_flexible.py y "magnitud" en triangulo_flexible.py): premia
  acercarse al ideal y PENALIZA pasarse de largo -- una cabeza
  extraordinariamente mas alta que los hombros probablemente no sea un
  H-C-H real sino un pico parabolico aislado sin relacion con los hombros
  (mismo patron de bug ya encontrado dos veces en este proyecto, aplicado
  aqui de forma preventiva).
- nivel_cuello: parecido entre fondo1 y fondo2 (la "linea de cuello" que
  conecta los 2 valles intermedios) -- igual mecanismo que nivel_cuello
  en doble_suelo/techo.
- caida1, caida2: dos caidas intermedias, separadas (mismo mecanismo que
  triple techo).
- altura: sobre la caida MAS PEQUEÑA de las dos (patron tan grande como
  su eslabon mas debil, igual que triple techo).
- tiempo: plano dentro del rango permitido.

Volumen separado desde el arranque, mismo mecanismo que el resto de
detectores. Media GEOMETRICA ponderada desde el arranque (igual que
triple_suelo/techo_flexible.py, no aritmetica).

`detectar()` = H-C-H normal (patron de techo, bajista tras confirmarse).
`detectar_invertido()` = espejo con fondos/valles (patron de suelo,
alcista tras confirmarse) -- cabeza mas BAJA que los hombros.

Solo se construye el DETECTOR -- ninguna prueba de rentabilidad todavia.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CandidatoHCH:
    tipo: str  # "hch" | "hch_invertido"
    idx_hombro1: int
    idx_valle1: int
    idx_cabeza: int
    idx_valle2: int
    idx_hombro2: int
    probabilidad_forma: float  # 7 dimensiones -- sin volumen
    diferencia_hombros_pct: float
    dominancia_cabeza_pct: float
    diferencia_cuello_pct: float
    caida1_pct: float
    caida2_pct: float
    dias_total: int
    n_alternativas_decentes: int
    volumen_ratio: float
    score_volumen: float


def _maximos_locales(close: np.ndarray, ventana: int = 3) -> list[int]:
    n = len(close)
    picos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.max():
            picos.append(i)
    return picos


def _minimos_locales(close: np.ndarray, ventana: int = 3) -> list[int]:
    n = len(close)
    valles = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.min():
            valles.append(i)
    return valles


def _detectar(
    df: pd.DataFrame,
    invertido: bool,
    dias_min_tramo: int = 8,
    dias_max_tramo: int = 90,
    tolerancia_hombros_pct: float = 15.0,
    dominancia_ideal_pct: float = 10.0,
    dominancia_tolerancia_exceso_pct: float = 15.0,
    tolerancia_cuello_pct: float = 15.0,
    caida_ideal_pct: float = 8.0,
    altura_ideal_pct: float = 20.0,
    peso_simetria_hombros: float = 0.20,
    peso_dominancia_cabeza: float = 0.20,
    peso_nivel_cuello: float = 0.15,
    peso_caida1: float = 0.10,
    peso_caida2: float = 0.10,
    peso_altura: float = 0.20,
    peso_tiempo: float = 0.05,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoHCH]:
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy() if "volume" in df.columns else None
    vol_media = df["volume"].rolling(30).mean().to_numpy() if volume is not None else None

    # invertido: cabeza es un fondo (minimo), hombros son picos alrededor
    # -- se detecta sobre -close para reutilizar la misma logica de
    # "maximos" en ambos casos (mismo truco que doble_suelo/techo).
    serie = -close if invertido else close
    extremos = _maximos_locales(serie)
    valles = _minimos_locales(serie)
    n = len(close)

    por_hombro2: dict[int, list[tuple]] = {}
    for i, idx_hombro1 in enumerate(extremos):
        precio_hombro1 = close[idx_hombro1]
        for idx_cabeza in extremos[i + 1:]:
            dias_1c = idx_cabeza - idx_hombro1
            if dias_1c > dias_max_tramo:
                break
            if dias_1c < dias_min_tramo // 2:
                continue
            precio_cabeza = close[idx_cabeza]

            valle1_opts = [v for v in valles if idx_hombro1 < v < idx_cabeza]
            if not valle1_opts:
                continue

            for idx_hombro2 in extremos:
                if idx_hombro2 <= idx_cabeza:
                    continue
                dias_total = idx_hombro2 - idx_hombro1
                if dias_total > dias_max_tramo:
                    break
                if dias_total < dias_min_tramo:
                    continue
                precio_hombro2 = close[idx_hombro2]

                # requisito ESTRUCTURAL: la cabeza debe superar a los dos
                # hombros (o, invertido, quedar por debajo de los dos) --
                # define que es H-C-H, no un filtro de calidad.
                if not invertido and not (precio_cabeza > precio_hombro1 and precio_cabeza > precio_hombro2):
                    continue
                if invertido and not (precio_cabeza < precio_hombro1 and precio_cabeza < precio_hombro2):
                    continue

                valle2_opts = [v for v in valles if idx_cabeza < v < idx_hombro2]
                if not valle2_opts:
                    continue

                for idx_valle1 in valle1_opts:
                    precio_valle1 = close[idx_valle1]
                    if not invertido and precio_valle1 >= min(precio_hombro1, precio_cabeza):
                        continue
                    if invertido and precio_valle1 <= max(precio_hombro1, precio_cabeza):
                        continue
                    for idx_valle2 in valle2_opts:
                        precio_valle2 = close[idx_valle2]
                        if not invertido and precio_valle2 >= min(precio_cabeza, precio_hombro2):
                            continue
                        if invertido and precio_valle2 <= max(precio_cabeza, precio_hombro2):
                            continue

                        media_hombros = (precio_hombro1 + precio_hombro2) / 2
                        diferencia_hombros_pct = abs(precio_hombro1 - precio_hombro2) / media_hombros * 100
                        hombro_extremo = (max(precio_hombro1, precio_hombro2) if not invertido
                                           else min(precio_hombro1, precio_hombro2))
                        if not invertido:
                            dominancia_cabeza_pct = (precio_cabeza - hombro_extremo) / hombro_extremo * 100
                        else:
                            dominancia_cabeza_pct = (hombro_extremo - precio_cabeza) / hombro_extremo * 100
                        media_cuello = (precio_valle1 + precio_valle2) / 2
                        diferencia_cuello_pct = abs(precio_valle1 - precio_valle2) / media_cuello * 100

                        if not invertido:
                            caida1_pct = (max(precio_hombro1, precio_cabeza) - precio_valle1) \
                                / max(precio_hombro1, precio_cabeza) * 100
                            caida2_pct = (max(precio_cabeza, precio_hombro2) - precio_valle2) \
                                / max(precio_cabeza, precio_hombro2) * 100
                        else:
                            caida1_pct = (precio_valle1 - min(precio_hombro1, precio_cabeza)) \
                                / min(precio_hombro1, precio_cabeza) * 100
                            caida2_pct = (precio_valle2 - min(precio_cabeza, precio_hombro2)) \
                                / min(precio_cabeza, precio_hombro2) * 100

                        score_simetria_hombros = max(0.0, 1 - diferencia_hombros_pct / tolerancia_hombros_pct)
                        if dominancia_cabeza_pct <= dominancia_ideal_pct:
                            score_dominancia_cabeza = max(0.0, dominancia_cabeza_pct / dominancia_ideal_pct)
                        else:
                            exceso = dominancia_cabeza_pct - dominancia_ideal_pct
                            score_dominancia_cabeza = float(np.exp(-exceso / dominancia_tolerancia_exceso_pct))
                        score_nivel_cuello = max(0.0, 1 - diferencia_cuello_pct / tolerancia_cuello_pct)
                        score_caida1 = min(max(caida1_pct, 0.0) / caida_ideal_pct, 1.0)
                        score_caida2 = min(max(caida2_pct, 0.0) / caida_ideal_pct, 1.0)
                        caida_menor_pct = min(caida1_pct, caida2_pct)
                        score_altura = min(max(caida_menor_pct, 0.0) / altura_ideal_pct, 1.0)
                        score_tiempo = 1.0

                        score_simetria_safe = max(score_simetria_hombros, 1e-3)
                        score_dominancia_safe = max(score_dominancia_cabeza, 1e-3)
                        score_cuello_safe = max(score_nivel_cuello, 1e-3)
                        score_caida1_safe = max(score_caida1, 1e-3)
                        score_caida2_safe = max(score_caida2, 1e-3)
                        score_altura_safe = max(score_altura, 1e-3)
                        score_tiempo_safe = max(score_tiempo, 1e-3)
                        probabilidad_forma = (score_simetria_safe ** peso_simetria_hombros
                                               * score_dominancia_safe ** peso_dominancia_cabeza
                                               * score_cuello_safe ** peso_nivel_cuello
                                               * score_caida1_safe ** peso_caida1
                                               * score_caida2_safe ** peso_caida2
                                               * score_altura_safe ** peso_altura
                                               * score_tiempo_safe ** peso_tiempo)

                        opcion = (idx_hombro1, idx_valle1, idx_cabeza, idx_valle2, idx_hombro2,
                                  diferencia_hombros_pct, dominancia_cabeza_pct, diferencia_cuello_pct,
                                  caida1_pct, caida2_pct, probabilidad_forma)
                        por_hombro2.setdefault(idx_hombro2, []).append(opcion)

    candidatos: list[CandidatoHCH] = []
    for idx_hombro2, opciones in por_hombro2.items():
        opciones.sort(key=lambda o: o[10], reverse=True)
        (idx_hombro1, idx_valle1, idx_cabeza, idx_valle2, _idx_hombro2,
         diferencia_hombros_pct, dominancia_cabeza_pct, diferencia_cuello_pct,
         caida1_pct, caida2_pct, probabilidad_forma) = opciones[0]
        n_decentes = sum(1 for o in opciones if o[10] >= 0.3) - 1

        volumen_ratio = 0.0
        if volume is not None:
            fin_v = min(idx_hombro2 + dias_ventana_volumen, n)
            tramo_vol = volume[idx_hombro2:fin_v]
            tramo_media = vol_media[idx_hombro2:fin_v]
            validos = ~np.isnan(tramo_media) & (tramo_media > 0)
            if validos.any():
                volumen_ratio = float((tramo_vol[validos] / tramo_media[validos]).max())
        score_volumen = min(volumen_ratio / vol_mult_ideal, 1.0)

        candidatos.append(CandidatoHCH(
            tipo="hch_invertido" if invertido else "hch",
            idx_hombro1=idx_hombro1, idx_valle1=idx_valle1, idx_cabeza=idx_cabeza,
            idx_valle2=idx_valle2, idx_hombro2=idx_hombro2,
            probabilidad_forma=round(probabilidad_forma, 3),
            diferencia_hombros_pct=round(diferencia_hombros_pct, 2),
            dominancia_cabeza_pct=round(dominancia_cabeza_pct, 2),
            diferencia_cuello_pct=round(diferencia_cuello_pct, 2),
            caida1_pct=round(caida1_pct, 2), caida2_pct=round(caida2_pct, 2),
            dias_total=idx_hombro2 - idx_hombro1, n_alternativas_decentes=n_decentes,
            volumen_ratio=round(volumen_ratio, 3), score_volumen=round(score_volumen, 3),
        ))

    return candidatos


def detectar(df: pd.DataFrame, **kwargs) -> list[CandidatoHCH]:
    """H-C-H normal -- patron de TECHO (cabeza mas alta que los hombros)."""
    return _detectar(df, invertido=False, **kwargs)


def detectar_invertido(df: pd.DataFrame, **kwargs) -> list[CandidatoHCH]:
    """H-C-H invertido -- patron de SUELO (cabeza mas baja que los hombros)."""
    return _detectar(df, invertido=True, **kwargs)


# (peso_simetria_hombros, peso_dominancia_cabeza, peso_nivel_cuello,
#  peso_caida1, peso_caida2, peso_altura, peso_tiempo) -- suman 1.0.
PESOS_FORMA = [
    (0.20, 0.20, 0.15, 0.10, 0.10, 0.20, 0.05),  # equilibrado -- default
    (0.55, 0.10, 0.10, 0.05, 0.05, 0.10, 0.05),  # simetria de hombros dominante
    (0.10, 0.55, 0.10, 0.05, 0.05, 0.10, 0.05),  # dominancia de cabeza dominante
    (0.10, 0.10, 0.55, 0.05, 0.05, 0.10, 0.05),  # nivel de cuello dominante
    (0.05, 0.05, 0.05, 0.10, 0.10, 0.60, 0.05),  # altura casi absoluta
]
