"""
Espejo bajista exacto de `caida_recuperacion.py` (ver ese archivo para la
explicacion completa de cada dimension) -- idea del usuario (11-sept-2026):
"subida brusca y correccion", lo contrario de "caida brusca y recuperacion".

Aqui SOLO se construye el detector -- estamos en la fase de DETECTAR
patrones, no en la de decidir si son rentables en solitario (esa pregunta
es de una fase posterior, combinando varios detectores a la vez -- ver
correccion de fase anotada en la memoria del proyecto el 11-sept-2026).

Que dice la señal, en palabras normales:
- Un maximo local (el "techo" de la subida, deteccion causal).
- El valle mas alto... mas bajo, razonable, antes de ese techo, dentro de
  una ventana de dias -- eso define "la subida" (magnitud y velocidad).
- Cuanto se ha corregido el precio (bajado) en los dias posteriores al
  techo, como fraccion de lo subido -- eso define "la correccion".
- Mismas 4 dimensiones fisicas añadidas a caida_recuperacion.py, en
  espejo: mecha (vela tipo estrella fugaz -- mecha superior, cierre por
  debajo del maximo del dia), desaceleracion de la subida (se frena antes
  de tocar techo), redondeo de la correccion (la bajada posterior pierde
  fuerza en vez de mantenerse -- techo redondeado), arranque brusco
  (subida inicial mas rapida que la media, tipo euforia/noticia).

Volumen separado desde el arranque, mismo mecanismo que el resto de
detectores del proyecto.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CandidatoSubidaCorreccion:
    idx_valle: int
    idx_techo: int
    precio_valle: float
    probabilidad_forma: float  # 7 dimensiones de forma -- sin volumen
    subida_pct: float
    velocidad_pct_dia: float
    correccion_pct_del_tramo: float
    mecha_pct: float
    desaceleracion_subida_pct: float
    redondeo_correccion_pct: float
    arranque_brusco_pct: float
    dias_subida: int
    n_valles_alternativos_decentes: int
    volumen_ratio: float
    score_volumen: float


def _detectar_techos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Maximos locales causales -- identico a doble_techo_flexible.py."""
    n = len(close)
    techos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.max():
            techos.append(i)
    return techos


def _detectar_valles_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Minimos locales causales -- usado para marcar el INICIO de la subida."""
    n = len(close)
    valles = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.min():
            valles.append(i)
    return valles


def detectar(
    df: pd.DataFrame,
    ventana_min_dias: int = 3,
    ventana_max_dias: int = 20,
    subida_ideal_pct: float = 15.0,
    velocidad_ideal_pct_dia: float = 3.0,
    dias_ventana_correccion: int = 10,
    correccion_ideal_pct: float = 50.0,
    mecha_ideal_pct: float = 60.0,
    desaceleracion_ideal_pct: float = 50.0,
    redondeo_ideal_pct: float = 50.0,
    arranque_ideal_pct: float = 50.0,
    peso_subida: float = 0.20,
    peso_velocidad: float = 0.20,
    peso_correccion: float = 0.20,
    peso_mecha: float = 0.15,
    peso_desaceleracion: float = 0.10,
    peso_redondeo: float = 0.10,
    peso_arranque: float = 0.05,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoSubidaCorreccion]:
    close = df["close"].to_numpy()
    high = df["high"].to_numpy() if "high" in df.columns else close
    low = df["low"].to_numpy() if "low" in df.columns else close
    volume = df["volume"].to_numpy() if "volume" in df.columns else None
    vol_media = df["volume"].rolling(30).mean().to_numpy() if volume is not None else None

    techos = _detectar_techos_simple(close)
    valles = _detectar_valles_simple(close)

    n = len(close)
    candidatos: list[CandidatoSubidaCorreccion] = []
    for idx_techo in techos:
        precio_techo = close[idx_techo]

        # correccion (cuanto, en total) y redondeo (como, con que forma de
        # velocidad) -- ventana fija hacia adelante, espejo de recuperacion.
        fin_corr = min(idx_techo + dias_ventana_correccion, n)
        tramo_corr = close[idx_techo:fin_corr]
        precio_min_tras = tramo_corr.min()

        dias_corr_reales = fin_corr - idx_techo
        redondeo_correccion_pct = 0.0
        if dias_corr_reales >= 4:
            mitad = dias_corr_reales // 2
            precio_medio_corr = close[idx_techo + mitad]
            precio_final_corr = close[fin_corr - 1]
            vel1_corr = max(0.0, (precio_techo - precio_medio_corr) / precio_techo / mitad * 100)
            resto = dias_corr_reales - mitad
            vel2_corr = max(0.0, (precio_medio_corr - precio_final_corr) / precio_medio_corr / resto * 100) if resto > 0 else 0.0
            # positivo = la correccion pierde fuerza (techo redondeado)
            redondeo_correccion_pct = max(0.0, vel1_corr - vel2_corr)

        # mecha: vela tipo estrella fugaz -- mecha superior, cierre por
        # debajo del maximo del dia (espejo del martillo).
        rango_dia = high[idx_techo] - low[idx_techo]
        mecha_pct = ((high[idx_techo] - close[idx_techo]) / rango_dia * 100) if rango_dia > 0 else 0.0

        # valles candidatos: dentro de la ventana de dias permitida, antes del techo
        candidatos_valle = [v for v in valles if ventana_min_dias <= idx_techo - v <= ventana_max_dias]
        if not candidatos_valle:
            continue

        opciones = []
        for idx_valle in candidatos_valle:
            precio_valle = close[idx_valle]
            if precio_valle >= precio_techo:
                continue
            subida_pct = (precio_techo - precio_valle) / precio_valle * 100
            dias_subida = idx_techo - idx_valle
            velocidad_pct_dia = subida_pct / dias_subida
            correccion_pct_del_tramo = max(0.0, (precio_techo - precio_min_tras) / (precio_techo - precio_valle) * 100)

            # desaceleracion de la subida: velocidad en la 1a mitad del
            # tramo vs la 2a mitad -- positivo = se frena antes de tocar techo.
            desaceleracion_subida_pct = 0.0
            if dias_subida >= 4:
                mitad = dias_subida // 2
                precio_medio_subida = close[idx_valle + mitad]
                vel1_subida = max(0.0, (precio_medio_subida - precio_valle) / precio_valle / mitad * 100)
                resto = dias_subida - mitad
                vel2_subida = max(0.0, (precio_techo - precio_medio_subida) / precio_medio_subida / resto * 100) if resto > 0 else 0.0
                desaceleracion_subida_pct = max(0.0, vel1_subida - vel2_subida)

            # arranque brusco: velocidad del primer tercio de la subida
            # frente a la velocidad media total -- euforia/noticia al inicio.
            arranque_brusco_pct = 0.0
            if dias_subida >= 3:
                primer_tercio = max(1, dias_subida // 3)
                precio_tras_tercio = close[idx_valle + primer_tercio]
                velocidad_inicial = (precio_tras_tercio - precio_valle) / precio_valle / primer_tercio * 100
                arranque_brusco_pct = max(0.0, velocidad_inicial - velocidad_pct_dia)

            score_subida = min(subida_pct / subida_ideal_pct, 1.0)
            score_velocidad = min(velocidad_pct_dia / velocidad_ideal_pct_dia, 1.0)
            score_correccion = min(correccion_pct_del_tramo / correccion_ideal_pct, 1.0)
            score_mecha = min(mecha_pct / mecha_ideal_pct, 1.0)
            score_desaceleracion = min(desaceleracion_subida_pct / desaceleracion_ideal_pct, 1.0)
            score_redondeo = min(redondeo_correccion_pct / redondeo_ideal_pct, 1.0)
            score_arranque = min(arranque_brusco_pct / arranque_ideal_pct, 1.0)

            prob_forma = (peso_subida * score_subida + peso_velocidad * score_velocidad
                          + peso_correccion * score_correccion + peso_mecha * score_mecha
                          + peso_desaceleracion * score_desaceleracion + peso_redondeo * score_redondeo
                          + peso_arranque * score_arranque)
            opciones.append((idx_valle, precio_valle, subida_pct, velocidad_pct_dia, dias_subida,
                              correccion_pct_del_tramo, desaceleracion_subida_pct, arranque_brusco_pct,
                              prob_forma))

        if not opciones:
            continue

        opciones.sort(key=lambda o: o[8], reverse=True)
        (idx_valle, precio_valle, subida_pct, velocidad_pct_dia, dias_subida,
         correccion_pct_del_tramo, desaceleracion_subida_pct, arranque_brusco_pct,
         probabilidad_forma) = opciones[0]
        n_decentes = sum(1 for o in opciones if o[8] >= 0.3) - 1

        # volumen: mismo mecanismo exacto que el resto de detectores.
        volumen_ratio = 0.0
        if volume is not None:
            fin_v = min(idx_techo + dias_ventana_volumen, n)
            tramo_vol = volume[idx_techo:fin_v]
            tramo_media = vol_media[idx_techo:fin_v]
            validos = ~np.isnan(tramo_media) & (tramo_media > 0)
            if validos.any():
                volumen_ratio = float((tramo_vol[validos] / tramo_media[validos]).max())
        score_volumen = min(volumen_ratio / vol_mult_ideal, 1.0)

        candidatos.append(CandidatoSubidaCorreccion(
            idx_valle=idx_valle, idx_techo=idx_techo, precio_valle=round(float(precio_valle), 6),
            probabilidad_forma=round(probabilidad_forma, 3), subida_pct=round(subida_pct, 2),
            velocidad_pct_dia=round(velocidad_pct_dia, 3), correccion_pct_del_tramo=round(correccion_pct_del_tramo, 2),
            mecha_pct=round(mecha_pct, 2), desaceleracion_subida_pct=round(desaceleracion_subida_pct, 3),
            redondeo_correccion_pct=round(redondeo_correccion_pct, 3), arranque_brusco_pct=round(arranque_brusco_pct, 3),
            dias_subida=dias_subida, n_valles_alternativos_decentes=n_decentes,
            volumen_ratio=round(volumen_ratio, 3), score_volumen=round(score_volumen, 3),
        ))

    return candidatos


# Mismos 6 configs que caida_recuperacion.py, en espejo.
PESOS_FORMA = [
    (0.20, 0.20, 0.20, 0.15, 0.10, 0.10, 0.05),  # equilibrado, todas presentes
    (0.15, 0.15, 0.15, 0.40, 0.05, 0.05, 0.05),  # mecha dominante -- estrella fugaz
    (0.15, 0.15, 0.15, 0.05, 0.10, 0.35, 0.05),  # redondeo dominante -- techo redondeado
    (0.15, 0.15, 0.15, 0.05, 0.35, 0.10, 0.05),  # desaceleracion de la subida dominante
    (0.30, 0.30, 0.30, 0.03, 0.03, 0.02, 0.02),  # casi como la version original (sin las 4 nuevas)
    (0.10, 0.10, 0.10, 0.20, 0.15, 0.15, 0.20),  # arranque brusco + resto de las nuevas
]
