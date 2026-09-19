"""
Doble suelo con MUCHO margen, version probabilidad (a diferencia de
doble_suelo.py, que exige un nivel casi identico y una ventana fija).
Idea del usuario: en vez de decir "esto ES un doble suelo" con reglas
estrictas, probar muchas combinaciones posibles -- el segundo suelo puede
quedar mas alto, mas bajo o igual que el primero; la separacion en el
tiempo puede ser mas corta o mas larga; puede incluso haber un pequeño
rebote doble en medio -- y que cada combinacion salga con su propia
probabilidad de "esto se parece a un doble suelo", en vez de descartar
todo lo que no encaje en un molde fijo.

Para cada fondo candidato (deteccion causal, igual que el resto de
detectores de esta carpeta), busca hacia atras TODOS los fondos previos
razonables dentro de una ventana ancha, y calcula una probabilidad para
cada posible pareja (fondo1, fondo2=candidato). Se queda con la mejor
pareja, pero guarda tambien cuantas parejas decentes habia (mas parejas
con probabilidad decente = forma menos "limpia", con mas ambiguedad).

11-sept-2026: `probabilidad` se separa en dos puntuaciones INDEPENDIENTES,
`probabilidad_forma` (nivel, rebote, tiempo, altura -- pura geometria del
patron, nada de mercado) y `score_volumen` (participacion/confirmacion).
Motivo: mezcladas en un solo numero compuesto no se podia aislar si el
volumen aporta algo o no (ver `volumen_en_rotura.py` -- probado y
descartado esa noche, pero mezclado con la forma no se sabia si el
resultado negativo era del volumen o se diluia con la forma). Separarlas
permite testear cada una por su cuenta y, mas adelante, su combinacion --
sin volver a caer en un filtro binario duro (prohibido por la skill,
`altura_minima_pct` ya emperoro los resultados en su dia)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class CandidatoDobleSuelo:
    idx_fondo1: int
    idx_fondo2: int
    probabilidad_forma: float  # SOLO geometria: nivel, rebote, tiempo, altura -- sin volumen
    diferencia_nivel_pct: float  # + si fondo2 esta mas alto que fondo1, - si mas bajo
    rebote_intermedio_pct: float
    dias_entre_fondos: int
    n_parejas_alternativas_decentes: int  # cuantas otras parejas (fondo1', fondo2) superaban 0.3 de probabilidad_forma
    volumen_ratio: float  # pico de volumen tras fondo2, relativo a su media reciente
    score_volumen: float  # volumen_ratio normalizado 0-1, INDEPENDIENTE de probabilidad_forma


def _detectar_fondos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Minimos locales causales simples (ventana de confirmacion corta) --
    version ligera, reutilizada como candidatos a 'fondo' para esta
    busqueda flexible (no exige la confirmacion de rebote mas estricta de
    motor_rebote_minimo.py, aqui interesa capturar mas candidatos, no
    menos)."""
    n = len(close)
    fondos = []
    for i in range(ventana, n - ventana):
        ventana_precios = close[i - ventana: i + ventana + 1]
        if close[i] == ventana_precios.min():
            fondos.append(i)
    return fondos


def detectar(
    df: pd.DataFrame,
    ventana_min_dias: int = 4,
    ventana_max_dias: int = 45,
    tolerancia_nivel_pct: float = 15.0,
    rebote_ideal_pct: float = 8.0,
    peso_nivel: float = 0.15,
    peso_rebote: float = 0.15,
    peso_tiempo: float = 0.10,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
    peso_altura: float = 0.60,
    altura_ideal_pct: float = 20.0,
) -> list[CandidatoDobleSuelo]:
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy() if "volume" in df.columns else None
    vol_media = df["volume"].rolling(30).mean().to_numpy() if volume is not None else None
    fondos = _detectar_fondos_simple(close)

    n = len(close)
    candidatos: list[CandidatoDobleSuelo] = []
    for pos2, idx2 in enumerate(fondos):
        precio2 = close[idx2]

        # volumen: pico de volumen en los dias posteriores a fondo2 (donde
        # ocurriria la ruptura), relativo a su media de 30 velas -- igual
        # que exige doble_suelo.py estricto (volumen > 1.5x media en la
        # ruptura), pero medido de forma continua en vez de sí/no.
        volumen_ratio = 0.0
        if volume is not None:
            fin_ventana_vol = min(idx2 + dias_ventana_volumen, n)
            tramo_vol = volume[idx2:fin_ventana_vol]
            tramo_media = vol_media[idx2:fin_ventana_vol]
            validos = ~np.isnan(tramo_media) & (tramo_media > 0)
            if validos.any():
                volumen_ratio = float((tramo_vol[validos] / tramo_media[validos]).max())
        score_volumen = min(volumen_ratio / vol_mult_ideal, 1.0)

        parejas = []
        for idx1 in fondos[:pos2]:
            dias = idx2 - idx1
            if dias < ventana_min_dias or dias > ventana_max_dias:
                continue
            precio1 = close[idx1]
            diferencia_nivel_pct = (precio2 - precio1) / precio1 * 100
            maximo_intermedio = close[idx1:idx2 + 1].max()
            rebote_intermedio_pct = (maximo_intermedio - min(precio1, precio2)) / min(precio1, precio2) * 100

            # cuanto mas parecidos los niveles, mejor -- pero con margen amplio, no exige igualdad
            score_nivel = max(0.0, 1 - abs(diferencia_nivel_pct) / tolerancia_nivel_pct)
            # rebote intermedio: satura en rebote_ideal_pct (un rebote MODESTO ya
            # puntua bien aqui -- esto mide "hubo un rebote real", no "es grande")
            score_rebote = min(rebote_intermedio_pct / rebote_ideal_pct, 1.0)
            # altura: dimension SEPARADA de rebote, con un ideal mas alto --
            # mide "es un patron GRANDE", sin descartar nunca a los pequeños
            # (a diferencia del filtro duro altura_minima_pct que probamos y
            # empeoro los resultados). Un patron pequeño simplemente saca poca
            # nota aqui, no queda fuera.
            score_altura = min(rebote_intermedio_pct / altura_ideal_pct, 1.0)
            # tiempo: sin penalizar dentro del rango permitido (margen amplio == plano)
            score_tiempo = 1.0

            probabilidad_forma = (peso_nivel * score_nivel + peso_rebote * score_rebote
                                   + peso_tiempo * score_tiempo + peso_altura * score_altura)
            parejas.append((idx1, probabilidad_forma, diferencia_nivel_pct, rebote_intermedio_pct, dias))

        if not parejas:
            continue

        parejas.sort(key=lambda p: p[1], reverse=True)
        mejor = parejas[0]
        n_decentes = sum(1 for p in parejas if p[1] >= 0.3) - 1  # sin contar la mejor misma

        candidatos.append(CandidatoDobleSuelo(
            idx_fondo1=mejor[0], idx_fondo2=idx2, probabilidad_forma=round(mejor[1], 3),
            diferencia_nivel_pct=round(mejor[2], 2), rebote_intermedio_pct=round(mejor[3], 2),
            dias_entre_fondos=mejor[4], n_parejas_alternativas_decentes=n_decentes,
            volumen_ratio=round(volumen_ratio, 3), score_volumen=round(score_volumen, 3),
        ))

    return candidatos
