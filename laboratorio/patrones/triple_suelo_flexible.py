"""
Triple suelo, extension directa de `doble_suelo_flexible.py` (11-sept-2026,
idea del usuario) -- mismo principio de deteccion flexible, pero con 3
toques en vez de 2: fondo1 -> pico1 -> fondo2 -> pico2 -> fondo3 (dos
rebotes intermedios, no uno).

Dimensiones (mismo espiritu que doble suelo, extendidas a 3 puntos):
- nivel: en vez de comparar solo 2 fondos, se compara la MAYOR diferencia
  entre cualquier par de los 3 -- si dos fondos son parecidos pero el
  tercero esta muy descolgado, no debe quedar tapado.
- rebote1 (fondo1->fondo2) y rebote2 (fondo2->fondo3): DOS dimensiones
  separadas, no una -- un triple suelo real tiene dos rebotes razonables,
  no solo uno bueno y el otro plano.
- altura: igual mecanismo que doble suelo (dimension separada del rebote,
  con un ideal mas alto -- mide "es un patron GRANDE"), aplicada al rebote
  mas pequeño de los dos (el patron es tan grande como su rebote mas
  debil, no como el mejor).
- tiempo: plano dentro del rango permitido, igual que doble suelo.
- volumen: igual mecanismo, en la ruptura tras fondo3.

**Mejora respecto a doble_suelo_flexible.py, no silenciosa**: alli las
dimensiones se combinan con media ARITMETICA ponderada. Aqui, igual que
en canal_flexible.py tras el bug 4 (una dimension pesima podia quedar
tapada por las demas con aritmetica), se usa media GEOMETRICA ponderada
desde el arranque -- un tercer fondo muy descolgado, o un rebote
practicamente inexistente, no puede quedar oculto por buena altura o buen
nivel en los otros dos. Fichero nuevo, no se toca doble_suelo_flexible.py
(ya validado con su propio mecanismo).

Solo se construye el DETECTOR -- ninguna prueba de rentabilidad todavia.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CandidatoTripleSuelo:
    idx_fondo1: int
    idx_pico1: int
    idx_fondo2: int
    idx_pico2: int
    idx_fondo3: int
    probabilidad_forma: float  # 5 dimensiones -- sin volumen
    diferencia_nivel_max_pct: float  # mayor diferencia entre cualquier par de los 3 fondos
    rebote1_pct: float
    rebote2_pct: float
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


def detectar(
    df: pd.DataFrame,
    dias_min_tramo: int = 8,
    dias_max_tramo: int = 90,
    tolerancia_nivel_pct: float = 15.0,
    rebote_ideal_pct: float = 8.0,
    rebote_tolerancia_exceso_pct: float = 15.0,
    altura_ideal_pct: float = 20.0,
    peso_nivel: float = 0.25,
    peso_rebote1: float = 0.15,
    peso_rebote2: float = 0.15,
    peso_altura: float = 0.35,
    peso_tiempo: float = 0.10,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoTripleSuelo]:
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy() if "volume" in df.columns else None
    vol_media = df["volume"].rolling(30).mean().to_numpy() if volume is not None else None

    fondos = _detectar_fondos_simple(close)
    picos = _detectar_picos_simple(close)
    n = len(close)

    por_fondo3: dict[int, list[tuple]] = {}
    for i, idx_fondo1 in enumerate(fondos):
        precio_fondo1 = close[idx_fondo1]
        for idx_fondo2 in fondos[i + 1:]:
            dias_12 = idx_fondo2 - idx_fondo1
            if dias_12 > dias_max_tramo:
                break
            if dias_12 < dias_min_tramo // 2:
                continue
            precio_fondo2 = close[idx_fondo2]

            pico1_opts = [p for p in picos if idx_fondo1 < p < idx_fondo2]
            if not pico1_opts:
                continue

            for idx_fondo3 in fondos:
                if idx_fondo3 <= idx_fondo2:
                    continue
                dias_total = idx_fondo3 - idx_fondo1
                if dias_total > dias_max_tramo:
                    break
                if dias_total < dias_min_tramo:
                    continue
                precio_fondo3 = close[idx_fondo3]

                pico2_opts = [p for p in picos if idx_fondo2 < p < idx_fondo3]
                if not pico2_opts:
                    continue

                for idx_pico1 in pico1_opts:
                    precio_pico1 = close[idx_pico1]
                    if precio_pico1 <= max(precio_fondo1, precio_fondo2):
                        continue
                    for idx_pico2 in pico2_opts:
                        precio_pico2 = close[idx_pico2]
                        if precio_pico2 <= max(precio_fondo2, precio_fondo3):
                            continue

                        niveles = [precio_fondo1, precio_fondo2, precio_fondo3]
                        nivel_medio = float(np.mean(niveles))
                        diferencia_nivel_max_pct = float(
                            (max(niveles) - min(niveles)) / nivel_medio * 100
                        )
                        rebote1_pct = (precio_pico1 - min(precio_fondo1, precio_fondo2)) \
                            / min(precio_fondo1, precio_fondo2) * 100
                        rebote2_pct = (precio_pico2 - min(precio_fondo2, precio_fondo3)) \
                            / min(precio_fondo2, precio_fondo3) * 100

                        # nivel: igual mecanismo que doble suelo, pero sobre
                        # la MAYOR diferencia de los 3 fondos, no solo un par
                        # -- un tercer fondo descolgado no puede esconderse
                        # detras de dos que sí coinciden.
                        score_nivel = max(0.0, 1 - diferencia_nivel_max_pct / tolerancia_nivel_pct)
                        # puntuacion en PICO, no en suelo (bug real encontrado
                        # el 11-sept-2026 durante la validacion ETH->BTC: un
                        # rebote intermedio del 89% puntuaba igual -- tope 1.0
                        # -- que uno del 10%, dejando que un movimiento en V
                        # aislado (no un triple suelo real) dominara el
                        # ranking. Mismo mecanismo ya aplicado a ancho en
                        # canal_flexible.py y magnitud en triangulo_flexible.py:
                        # premia acercarse al ideal, penaliza pasarse de largo.
                        if rebote1_pct <= rebote_ideal_pct:
                            score_rebote1 = max(0.0, rebote1_pct / rebote_ideal_pct)
                        else:
                            score_rebote1 = float(np.exp(-(rebote1_pct - rebote_ideal_pct) / rebote_tolerancia_exceso_pct))
                        if rebote2_pct <= rebote_ideal_pct:
                            score_rebote2 = max(0.0, rebote2_pct / rebote_ideal_pct)
                        else:
                            score_rebote2 = float(np.exp(-(rebote2_pct - rebote_ideal_pct) / rebote_tolerancia_exceso_pct))
                        # altura: sobre el rebote MAS PEQUEÑO de los dos --
                        # el patron es tan grande como su rebote mas debil,
                        # no como el mejor de los dos (mismo principio que
                        # "una dimension pesima no debe quedar tapada").
                        rebote_menor_pct = min(rebote1_pct, rebote2_pct)
                        score_altura = min(rebote_menor_pct / altura_ideal_pct, 1.0)
                        score_tiempo = 1.0

                        score_nivel_safe = max(score_nivel, 1e-3)
                        score_rebote1_safe = max(score_rebote1, 1e-3)
                        score_rebote2_safe = max(score_rebote2, 1e-3)
                        score_altura_safe = max(score_altura, 1e-3)
                        score_tiempo_safe = max(score_tiempo, 1e-3)
                        probabilidad_forma = (score_nivel_safe ** peso_nivel
                                               * score_rebote1_safe ** peso_rebote1
                                               * score_rebote2_safe ** peso_rebote2
                                               * score_altura_safe ** peso_altura
                                               * score_tiempo_safe ** peso_tiempo)

                        opcion = (idx_fondo1, idx_pico1, idx_fondo2, idx_pico2, idx_fondo3,
                                  diferencia_nivel_max_pct, rebote1_pct, rebote2_pct, probabilidad_forma)
                        por_fondo3.setdefault(idx_fondo3, []).append(opcion)

    candidatos: list[CandidatoTripleSuelo] = []
    for idx_fondo3, opciones in por_fondo3.items():
        opciones.sort(key=lambda o: o[8], reverse=True)
        (idx_fondo1, idx_pico1, idx_fondo2, idx_pico2, _idx_fondo3,
         diferencia_nivel_max_pct, rebote1_pct, rebote2_pct, probabilidad_forma) = opciones[0]
        n_decentes = sum(1 for o in opciones if o[8] >= 0.3) - 1

        volumen_ratio = 0.0
        if volume is not None:
            fin_v = min(idx_fondo3 + dias_ventana_volumen, n)
            tramo_vol = volume[idx_fondo3:fin_v]
            tramo_media = vol_media[idx_fondo3:fin_v]
            validos = ~np.isnan(tramo_media) & (tramo_media > 0)
            if validos.any():
                volumen_ratio = float((tramo_vol[validos] / tramo_media[validos]).max())
        score_volumen = min(volumen_ratio / vol_mult_ideal, 1.0)

        candidatos.append(CandidatoTripleSuelo(
            idx_fondo1=idx_fondo1, idx_pico1=idx_pico1, idx_fondo2=idx_fondo2,
            idx_pico2=idx_pico2, idx_fondo3=idx_fondo3,
            probabilidad_forma=round(probabilidad_forma, 3),
            diferencia_nivel_max_pct=round(diferencia_nivel_max_pct, 2),
            rebote1_pct=round(rebote1_pct, 2), rebote2_pct=round(rebote2_pct, 2),
            dias_total=idx_fondo3 - idx_fondo1, n_alternativas_decentes=n_decentes,
            volumen_ratio=round(volumen_ratio, 3), score_volumen=round(score_volumen, 3),
        ))

    return candidatos


# (peso_nivel, peso_rebote1, peso_rebote2, peso_altura, peso_tiempo) --
# suman 1.0. Mismo mecanismo que canal/triangulo: varias configs con
# distinta dominancia para comprobar que el grid de pesos SI discrimina.
PESOS_FORMA = [
    (0.25, 0.15, 0.15, 0.35, 0.10),  # equilibrado -- default
    (0.55, 0.10, 0.10, 0.15, 0.10),  # nivel dominante -- los 3 fondos muy parecidos
    (0.10, 0.35, 0.35, 0.10, 0.10),  # rebotes dominantes -- dos rebotes claros
    (0.10, 0.10, 0.10, 0.60, 0.10),  # altura casi absoluta -- patron grande
]
