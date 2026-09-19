"""
Patron "caida brusca y recuperacion", idea del usuario (11-sept-2026) --
distinto de doble suelo (que exige DOS toques a un nivel parecido). Aqui
solo hace falta UNA caida rapida seguida de un rebote real, sin repetir
nivel.

11-sept-2026 (tarde, ampliacion): el usuario señalo que el mecanismo
original (magnitud + velocidad total + % recuperado, como 3 numeros
estaticos) se le escapaba la FISICA del movimiento -- una caida no se
frena en seco, tiene una temporalidad de frenada, y hay al menos dos
formas distintas de tocar fondo: (a) un pico brusco con una vela tipo
martillo (mecha larga, recuperacion dentro del mismo dia) y rebote rapido
tipo V, o (b) una caida que se REDONDEA -- se desacelera gradualmente, se
estabiliza, y la subida posterior va perdiendo fuerza, forma en U. Se
añaden 4 dimensiones continuas nuevas para capturar esto, TODAS con su
propio "ideal" de saturacion, sin decidir de antemano que sean patrones
separados -- si el grid revela dos poblaciones claramente distintas
(mecha alta / redondeo alto, sin solapar), se separan en dos detectores
mas adelante, no antes.

Dimensiones de forma (7 en total, `probabilidad_forma`):
- caida_pct, velocidad_pct_dia: magnitud y velocidad total (ya existian)
- recuperacion_pct_del_tramo: cuanto se ha recuperado en total (ya existia)
- score_mecha: cuanto se recupera DENTRO del propio dia del fondo (close
  vs low de esa vela) -- firma de vela tipo martillo/pin bar
- score_desaceleracion_caida: si la velocidad de caida se reduce en la
  segunda mitad del tramo de bajada frente a la primera -- "se frena
  antes de pararse"
- score_redondeo_subida: si la velocidad de SUBIDA tras el fondo se
  reduce con el tiempo (pierde fuerza) en vez de mantenerse -- forma en U
- score_arranque_brusco: si el inicio de la caida fue mas rapido que su
  media (tipo shock/noticia) frente a una caida que se acelera poco a poco

Separacion forma/volumen desde el arranque (11-sept-2026, ver nota en
doble_suelo_flexible.py): `probabilidad_forma` nunca incluye volumen.
`score_volumen` es un campo aparte, mismo mecanismo que en doble_suelo.

No existe una version "estricta" previa de este patron en el proyecto,
asi que no hay comprobacion de cordura que hacer aqui.

CORRECCION DE CAUSALIDAD (15-sept-2026): `recuperacion_pct_del_tramo` y
`redondeo_subida_pct` se calculan sobre `close[idx_fondo : idx_fondo +
dias_ventana_recuperacion]` -- precio POSTERIOR al propio punto de
entrada (`idx_fondo`). Estaban incluidas en `probabilidad_forma`, lo que
significa que Capa 1 no era puramente causal: un candidato se puntuaba
(y se elegia, entre varios picos posibles, cual emparejar con un fondo)
en parte por cuanto YA se sabia que habia subido tras el fondo. Al probar
despues un factor de contexto de mercado (regimen+ATH) sobre esta
deteccion, el grupo de control sin ninguna hipotesis (regimen NEUTRO)
salio con el efecto MAS FUERTE de los tres grupos -- la señal de que el
propio candidato, no el contexto, cargaba el sesgo (ver observacion 0021
del log de task-observer). Corregido: `probabilidad_forma` (Capa 1) usa
ahora solo las 5 dimensiones puramente causales (caida, velocidad, mecha,
desaceleracion, arranque -- ninguna mira mas alla de `idx_fondo`).
`recuperacion_pct_del_tramo` y `redondeo_subida_pct` se siguen calculando
y guardando como campos informativos del candidato (igual que
`volumen_ratio`), pero ya NUNCA entran en la puntuacion ni en la eleccion
de que pico emparejar con un fondo. La confirmacion real de "hubo
recuperacion" vive en Etapa 2 (`_entradas_confirmadas_caida` en
`validacion_cruzada_pesos.py`), que ya media el retorno desde el dia real
de confirmacion, no desde idx_fondo -- ese mecanismo ya era correcto,
el problema estaba solo en Capa 1.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CandidatoCaidaRecuperacion:
    idx_pico: int
    idx_fondo: int
    precio_pico: float
    probabilidad_forma: float  # 7 dimensiones de forma -- sin volumen
    caida_pct: float
    velocidad_pct_dia: float
    recuperacion_pct_del_tramo: float
    mecha_pct: float
    desaceleracion_caida_pct: float
    redondeo_subida_pct: float
    arranque_brusco_pct: float
    dias_caida: int
    n_picos_alternativos_decentes: int
    volumen_ratio: float
    score_volumen: float


def _detectar_fondos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Minimos locales causales -- identico a doble_suelo_flexible.py."""
    n = len(close)
    fondos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.min():
            fondos.append(i)
    return fondos


def _detectar_picos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Maximos locales causales -- identico a _detectar_techos_simple en
    doble_techo_flexible.py, aqui usado para marcar el INICIO de la caida."""
    n = len(close)
    picos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.max():
            picos.append(i)
    return picos


def detectar(
    df: pd.DataFrame,
    ventana_min_dias: int = 3,
    ventana_max_dias: int = 20,
    caida_ideal_pct: float = 15.0,
    velocidad_ideal_pct_dia: float = 3.0,
    dias_ventana_recuperacion: int = 10,
    recuperacion_ideal_pct: float = 50.0,
    mecha_ideal_pct: float = 60.0,
    desaceleracion_ideal_pct: float = 50.0,
    redondeo_ideal_pct: float = 50.0,
    arranque_ideal_pct: float = 50.0,
    peso_caida: float = 0.30,
    peso_velocidad: float = 0.30,
    peso_mecha: float = 0.20,
    peso_desaceleracion: float = 0.15,
    peso_arranque: float = 0.05,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoCaidaRecuperacion]:
    close = df["close"].to_numpy()
    high = df["high"].to_numpy() if "high" in df.columns else close
    low = df["low"].to_numpy() if "low" in df.columns else close
    volume = df["volume"].to_numpy() if "volume" in df.columns else None
    vol_media = df["volume"].rolling(30).mean().to_numpy() if volume is not None else None

    fondos = _detectar_fondos_simple(close)
    picos = _detectar_picos_simple(close)

    n = len(close)
    candidatos: list[CandidatoCaidaRecuperacion] = []
    for idx_fondo in fondos:
        precio_fondo = close[idx_fondo]

        # recuperacion (cuanto, en total) y redondeo (como, con que forma
        # de velocidad) -- ventana fija hacia adelante, igual mecanismo
        # que el volumen. NO dependen del pico elegido salvo normalizacion.
        fin_rec = min(idx_fondo + dias_ventana_recuperacion, n)
        tramo_rec = close[idx_fondo:fin_rec]
        precio_max_tras = tramo_rec.max()

        dias_rec_reales = fin_rec - idx_fondo
        redondeo_subida_pct = 0.0
        if dias_rec_reales >= 4:
            mitad = dias_rec_reales // 2
            precio_medio_rec = close[idx_fondo + mitad]
            precio_final_rec = close[fin_rec - 1]
            vel1_subida = max(0.0, (precio_medio_rec - precio_fondo) / precio_fondo / mitad * 100)
            resto = dias_rec_reales - mitad
            vel2_subida = max(0.0, (precio_final_rec - precio_medio_rec) / precio_medio_rec / resto * 100) if resto > 0 else 0.0
            # positivo = la subida pierde fuerza (forma en U); negativo o
            # cero = mantiene o gana fuerza (mas cerca de V) -- se recorta
            # a 0 porque aqui solo puntuamos "cuanto redondeo hay", no su
            # ausencia (eso ya lo refleja recuperacion_pct_del_tramo).
            redondeo_subida_pct = max(0.0, vel1_subida - vel2_subida)

        # mecha: cuanto se recupera DENTRO del propio dia del fondo
        # (firma de vela tipo martillo/pin bar) -- causal, mismo dia.
        rango_dia = high[idx_fondo] - low[idx_fondo]
        mecha_pct = ((close[idx_fondo] - low[idx_fondo]) / rango_dia * 100) if rango_dia > 0 else 0.0

        # picos candidatos: dentro de la ventana de dias permitida, antes del fondo
        candidatos_pico = [p for p in picos if ventana_min_dias <= idx_fondo - p <= ventana_max_dias]
        if not candidatos_pico:
            continue

        opciones = []
        for idx_pico in candidatos_pico:
            precio_pico = close[idx_pico]
            if precio_pico <= precio_fondo:
                continue
            caida_pct = (precio_pico - precio_fondo) / precio_pico * 100
            dias_caida = idx_fondo - idx_pico
            velocidad_pct_dia = caida_pct / dias_caida
            recuperacion_pct_del_tramo = max(0.0, (precio_max_tras - precio_fondo) / (precio_pico - precio_fondo) * 100)

            # desaceleracion de la caida: velocidad en la 1a mitad del
            # tramo de bajada vs la 2a mitad -- positivo = se frena antes
            # de tocar fondo (causal, solo usa datos hasta idx_fondo).
            desaceleracion_caida_pct = 0.0
            if dias_caida >= 4:
                mitad = dias_caida // 2
                precio_medio_caida = close[idx_pico + mitad]
                vel1_caida = max(0.0, (precio_pico - precio_medio_caida) / precio_pico / mitad * 100)
                resto = dias_caida - mitad
                vel2_caida = max(0.0, (precio_medio_caida - precio_fondo) / precio_medio_caida / resto * 100) if resto > 0 else 0.0
                desaceleracion_caida_pct = max(0.0, vel1_caida - vel2_caida)

            # arranque brusco: velocidad del primer tercio de la caida
            # frente a la velocidad media total -- shock/noticia al inicio
            # (causal, solo usa datos hasta idx_fondo).
            arranque_brusco_pct = 0.0
            if dias_caida >= 3:
                primer_tercio = max(1, dias_caida // 3)
                precio_tras_tercio = close[idx_pico + primer_tercio]
                velocidad_inicial = (precio_pico - precio_tras_tercio) / precio_pico / primer_tercio * 100
                arranque_brusco_pct = max(0.0, velocidad_inicial - velocidad_pct_dia)

            score_caida = min(caida_pct / caida_ideal_pct, 1.0)
            score_velocidad = min(velocidad_pct_dia / velocidad_ideal_pct_dia, 1.0)
            score_mecha = min(mecha_pct / mecha_ideal_pct, 1.0)
            score_desaceleracion = min(desaceleracion_caida_pct / desaceleracion_ideal_pct, 1.0)
            score_arranque = min(arranque_brusco_pct / arranque_ideal_pct, 1.0)

            # la eleccion del pico usa los PESOS REALES pasados a la
            # funcion (bug ya corregido el 11-sept-2026: una formula fija
            # aqui haria que variar el grid nunca cambiara el candidato
            # elegido). SOLO dimensiones causales (caida/velocidad/mecha/
            # desaceleracion/arranque) -- recuperacion_pct_del_tramo y
            # redondeo_subida_pct miran dias posteriores a idx_fondo y ya
            # NO participan en la puntuacion (correccion 15-sept-2026, ver
            # docstring del modulo y observacion 0021).
            prob_forma = (peso_caida * score_caida + peso_velocidad * score_velocidad
                          + peso_mecha * score_mecha + peso_desaceleracion * score_desaceleracion
                          + peso_arranque * score_arranque)
            opciones.append((idx_pico, precio_pico, caida_pct, velocidad_pct_dia, dias_caida,
                              recuperacion_pct_del_tramo, desaceleracion_caida_pct, arranque_brusco_pct,
                              prob_forma))

        if not opciones:
            continue

        opciones.sort(key=lambda o: o[8], reverse=True)
        (idx_pico, precio_pico, caida_pct, velocidad_pct_dia, dias_caida,
         recuperacion_pct_del_tramo, desaceleracion_caida_pct, arranque_brusco_pct,
         probabilidad_forma) = opciones[0]
        n_decentes = sum(1 for o in opciones if o[8] >= 0.3) - 1

        # volumen: mismo mecanismo exacto que doble_suelo_flexible.py,
        # separado de probabilidad_forma desde el arranque.
        volumen_ratio = 0.0
        if volume is not None:
            fin_v = min(idx_fondo + dias_ventana_volumen, n)
            tramo_vol = volume[idx_fondo:fin_v]
            tramo_media = vol_media[idx_fondo:fin_v]
            validos = ~np.isnan(tramo_media) & (tramo_media > 0)
            if validos.any():
                volumen_ratio = float((tramo_vol[validos] / tramo_media[validos]).max())
        score_volumen = min(volumen_ratio / vol_mult_ideal, 1.0)

        candidatos.append(CandidatoCaidaRecuperacion(
            idx_pico=idx_pico, idx_fondo=idx_fondo, precio_pico=round(float(precio_pico), 6),
            probabilidad_forma=round(probabilidad_forma, 3), caida_pct=round(caida_pct, 2),
            velocidad_pct_dia=round(velocidad_pct_dia, 3), recuperacion_pct_del_tramo=round(recuperacion_pct_del_tramo, 2),
            mecha_pct=round(mecha_pct, 2), desaceleracion_caida_pct=round(desaceleracion_caida_pct, 3),
            redondeo_subida_pct=round(redondeo_subida_pct, 3), arranque_brusco_pct=round(arranque_brusco_pct, 3),
            dias_caida=dias_caida, n_picos_alternativos_decentes=n_decentes,
            volumen_ratio=round(volumen_ratio, 3), score_volumen=round(score_volumen, 3),
        ))

    return candidatos


# (peso_caida, peso_velocidad, peso_mecha, peso_desaceleracion,
#  peso_arranque) -- suman 1.0 cada una. Correccion 15-sept-2026:
# peso_recuperacion y peso_redondeo se retiraron del grid porque las
# dimensiones que puntuaban (recuperacion_pct_del_tramo,
# redondeo_subida_pct) miran dias posteriores a idx_fondo -- no son
# causales, ver docstring del modulo y observacion 0021. Los configs de
# abajo son un rediseño sobre las 5 dimensiones que SI son causales, no
# una renormalizacion mecanica de los pesos viejos (los dos configs
# viejos que apostaban por "redondeo dominante" ya no tienen sentido sin
# esa dimension).
PESOS_FORMA = [
    (0.30, 0.30, 0.20, 0.15, 0.05),  # equilibrado, caida/velocidad dominantes
    (0.20, 0.20, 0.50, 0.05, 0.05),  # mecha dominante -- apuesta por la V con pin bar
    (0.20, 0.20, 0.10, 0.45, 0.05),  # desaceleracion de la caida dominante
    (0.40, 0.40, 0.05, 0.05, 0.10),  # caida+velocidad puras, casi la version original
    (0.15, 0.15, 0.20, 0.20, 0.30),  # arranque brusco dominante
]
