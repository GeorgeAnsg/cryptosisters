"""
Patron "canal" (subida y bajada), idea del usuario (11-sept-2026):
secuencia alternada minimo-maximo-minimo-maximo (ascendente) o
maximo-minimo-maximo-minimo (descendente), donde cada minimo/maximo va
en la misma direccion que el anterior -- dos lineas (soporte y
resistencia) razonablemente paralelas, con un margen (ancho) mas o
menos constante entre ellas.

Confirmado con el usuario que las DOS dimensiones que de verdad importan
son **pendiente** (que tan inclinadas van las dos lineas, y que tan
parecidas son entre si -- paralelismo) y **ancho** (la distancia entre
soporte y resistencia, y si se mantiene estable a lo largo del canal) --
se descarto explicitamente una dimension de "bondad de ajuste" (R^2) por
separado, queda repartida entre estas dos.

Solo se construye el DETECTOR (fase de deteccion, ver correccion de fase
en la memoria del proyecto, 11-sept-2026) -- ninguna prueba de
rentabilidad en solitario todavia.

Estructura minima: 2 fondos crecientes (o decrecientes) + 2 picos
crecientes (o decrecientes) alternados en el tiempo -- fondo1 < pico1 <
fondo2 < pico2. Es un requisito ESTRUCTURAL (define que es un canal, no
un filtro de calidad) -- igual que doble_suelo exige dos toques.

Volumen separado desde el arranque, mismo mecanismo que el resto de
detectores del proyecto.

Pendiente para mas adelante, NO decidido todavia: dimension de contexto
(el usuario senalo que los canales de subida suelen aparecer tras una
caida brusca) -- no incluida como requisito ni como bonus por ahora,
mencionada aqui para no perderla. Confirmado con el usuario (11-sept-2026)
que esta fase es solo "detectar canales a lo bruto, un motor solo" --
cruzar con otros motores (doble_suelo, caida_recuperacion, etc.) es una
idea valida pero de la fase posterior de combinacion, no de aqui.

**Bug real corregido el 11-sept-2026, encontrado al visualizar en BTC 2022:**
la puntuacion de ancho (`score_ancho`) solo funcionaba como SUELO -- un
canal de 8% de ancho puntuaba igual (1.0) que uno de 40%, porque la formula
era "cuanto mas ancho, mejor, hasta el ideal, luego se queda plano". Eso es
justo lo contrario de lo que es un canal real: si el ancho crece sin
limite, deja de ser un canal contenido y pasa a ser solo la tendencia
general disfrazada de canal (visible en BTC 2022: un "abanico" de
supuestos canales descendentes que en realidad trazaban TODA la caida de
$42k a $16k). Corregido con una puntuacion en PICO: premia acercarse al
ancho ideal y PENALIZA pasarse de largo, en vez de solo premiar alcanzarlo.

**Tercer bug real corregido el 11-sept-2026, encontrado por el usuario al
revisar BTC 2022 tras los dos fixes anteriores:** los 4 puntos de anclaje
(fondo1, pico1, fondo2, pico2) podian estar muy juntos (ancho pequeño, bien
puntuado) mientras el precio REAL entre esas fechas se salia por completo
del canal -- ejemplo real encontrado: fondo1=$41.566 (7-ene), pico1=$43.903
(12-ene), fondo2=$42.054 (13-feb), pico2=$44.545 (15-feb), ancho=5.5% (muy
bueno), pero el precio real llego a bajar hasta $35.071 entre medias -- una
caida de $10k que ninguna de las 4 dimensiones anteriores detectaba, porque
todas se calculan solo en los 4 puntos de anclaje, nunca en el camino real
entre ellos. Se añade una 5a dimension, `score_contencion`: recorre TODAS
las velas entre fondo1 y pico2, mide cuanto se sale el precio de la banda
(soporte-resistencia) en el peor dia, y penaliza esa dimension de forma
continua (mismo mecanismo que el resto -- nunca descarta el candidato).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CandidatoCanal:
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
    ancho_medio_pct: float
    consistencia_ancho: float  # 1.0 = ancho perfectamente constante
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


def _score_forma(
    idx_fondo1: int, idx_pico1: int, idx_fondo2: int, idx_pico2: int,
    precio_fondo1: float, precio_pico1: float, precio_fondo2: float, precio_pico2: float,
    close: np.ndarray, lateral: bool,
    pendiente_ideal_pct_dia: float,
    paralelismo_tolerancia_pct_dia: float,
    ancho_ideal_pct: float,
    ancho_tolerancia_exceso_pct: float,
    consistencia_tolerancia: float,
    contencion_tolerancia_pct: float,
    peso_pendiente: float,
    peso_paralelismo: float,
    peso_ancho: float,
    peso_consistencia: float,
    peso_contencion: float,
) -> dict | None:
    """Puntuacion de forma de un candidato de canal ya anclado en sus 4
    puntos. Extraida de `_detectar()` el 15-sept-2026 para que
    `entradas/canal.py` (version en vivo) pueda llamar exactamente a esta
    misma formula en vez de reimplementarla -- mismo motivo que la
    correccion de arquitectura de `entradas/doble_techo.py` (12-sept-2026,
    obs. 0007 del log de task-observer): dos copias de una formula se
    desincronizan en silencio. Devuelve None si las lineas se cruzan (canal
    invalido)."""
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
        return None  # las lineas se cruzan -- no es un canal valido

    precio_medio = float(np.mean([precio_fondo1, precio_pico1, precio_fondo2, precio_pico2]))
    ancho_medio_pct = float(np.mean(gaps)) / precio_medio * 100
    cv_ancho = float(np.std(gaps) / np.mean(gaps))
    consistencia_ancho = float(np.exp(-cv_ancho / consistencia_tolerancia))

    xs = np.arange(idx_fondo1, idx_pico2 + 1)
    banda_baja = precio_fondo1 + slope_soporte_abs * (xs - idx_fondo1)
    banda_alta = precio_pico1 + slope_resistencia_abs * (xs - idx_pico1)
    precios_tramo = close[idx_fondo1:idx_pico2 + 1]
    excursion_baja = np.maximum(0.0, banda_baja - precios_tramo)
    excursion_alta = np.maximum(0.0, precios_tramo - banda_alta)
    peor_excursion_pct = float(np.max(excursion_baja + excursion_alta)) / precio_medio * 100

    pendiente_media_abs = (abs(pend_soporte) + abs(pend_resistencia)) / 2
    if lateral:
        score_pendiente = float(np.exp(-pendiente_media_abs / pendiente_ideal_pct_dia))
    else:
        score_pendiente = min(pendiente_media_abs / pendiente_ideal_pct_dia, 1.0)

    diff_pendientes = abs(pend_soporte - pend_resistencia)
    score_paralelismo = float(np.exp(-diff_pendientes / paralelismo_tolerancia_pct_dia))

    if ancho_medio_pct <= ancho_ideal_pct:
        score_ancho = ancho_medio_pct / ancho_ideal_pct
    else:
        exceso = ancho_medio_pct - ancho_ideal_pct
        score_ancho = float(np.exp(-exceso / ancho_tolerancia_exceso_pct))
    score_consistencia = consistencia_ancho
    score_contencion = float(np.exp(-peor_excursion_pct / contencion_tolerancia_pct))

    score_pendiente_safe = max(score_pendiente, 1e-3)
    score_paralelismo_safe = max(score_paralelismo, 1e-3)
    score_ancho_safe = max(score_ancho, 1e-3)
    score_consistencia_safe = max(score_consistencia, 1e-3)
    score_contencion_safe = max(score_contencion, 1e-3)
    prob_forma = (score_pendiente_safe ** peso_pendiente
                  * score_paralelismo_safe ** peso_paralelismo
                  * score_ancho_safe ** peso_ancho
                  * score_consistencia_safe ** peso_consistencia
                  * score_contencion_safe ** peso_contencion)

    return dict(
        pend_soporte=pend_soporte, pend_resistencia=pend_resistencia,
        ancho_medio_pct=ancho_medio_pct, consistencia_ancho=consistencia_ancho,
        peor_excursion_pct=peor_excursion_pct, probabilidad_forma=prob_forma,
    )


def _detectar(
    df: pd.DataFrame,
    direccion: str,
    dias_min_tramo: int,
    dias_max_tramo: int,
    pendiente_ideal_pct_dia: float,
    paralelismo_tolerancia_pct_dia: float,
    ancho_ideal_pct: float,
    ancho_tolerancia_exceso_pct: float,
    consistencia_tolerancia: float,
    contencion_tolerancia_pct: float,
    peso_pendiente: float,
    peso_paralelismo: float,
    peso_ancho: float,
    peso_consistencia: float,
    peso_contencion: float,
    vol_mult_ideal: float,
    dias_ventana_volumen: int,
) -> list[CandidatoCanal]:
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy() if "volume" in df.columns else None
    vol_media = df["volume"].rolling(30).mean().to_numpy() if volume is not None else None

    fondos = _detectar_fondos_simple(close)
    picos = _detectar_picos_simple(close)
    n = len(close)

    ascendente = direccion == "subida"
    lateral = direccion == "lateral"

    # Todas las combinaciones (fondo1, fondo2) validas casi siempre se
    # solapan entre si en una tendencia sostenida (fondo1=A,fondo2=B y
    # fondo1=A,fondo2=C y fondo1=B,fondo2=C valen a la vez para el mismo
    # tramo de tendencia) -- mostrarlas todas produce un canal "duplicado"
    # por cada sub-ventana posible, no canales realmente distintos.
    # Se agrupan por idx_pico2 (el punto de finalizacion del canal) y solo
    # se conserva la mejor combinacion por cada punto de finalizacion --
    # mismo principio que "un candidato por idx_fondo" en caida_recuperacion.py.
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
            # requisito estructural: fondos en la misma direccion que el canal.
            # En modo lateral no se exige direccion -- un lateral admite que el
            # segundo fondo/pico quede un poco mas arriba O mas abajo, es la
            # puntuacion de pendiente (centrada en CASI CERO) la que discrimina,
            # no un requisito de orden.
            if not lateral:
                if ascendente and precio_fondo2 <= precio_fondo1:
                    continue
                if not ascendente and precio_fondo2 >= precio_fondo1:
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
                    if not lateral:
                        if ascendente and precio_pico2 <= precio_pico1:
                            continue
                        if not ascendente and precio_pico2 >= precio_pico1:
                            continue

                    r = _score_forma(
                        idx_fondo1, idx_pico1, idx_fondo2, idx_pico2,
                        precio_fondo1, precio_pico1, precio_fondo2, precio_pico2,
                        close, lateral, pendiente_ideal_pct_dia, paralelismo_tolerancia_pct_dia,
                        ancho_ideal_pct, ancho_tolerancia_exceso_pct, consistencia_tolerancia,
                        contencion_tolerancia_pct, peso_pendiente, peso_paralelismo,
                        peso_ancho, peso_consistencia, peso_contencion,
                    )
                    if r is None:
                        continue  # las lineas se cruzan -- no es un canal valido

                    opciones.append((idx_fondo1, idx_pico1, idx_fondo2, idx_pico2,
                                      precio_fondo1, precio_pico1, precio_fondo2, precio_pico2,
                                      r["pend_soporte"], r["pend_resistencia"], r["ancho_medio_pct"],
                                      r["consistencia_ancho"], r["peor_excursion_pct"], r["probabilidad_forma"]))

            for o in opciones:
                por_pico2.setdefault(o[3], []).append(o)

    candidatos: list[CandidatoCanal] = []
    for idx_pico2, opciones in por_pico2.items():
        opciones.sort(key=lambda o: o[13], reverse=True)
        (idx_fondo1, idx_pico1, idx_fondo2, _idx_pico2, precio_fondo1, precio_pico1,
         precio_fondo2, precio_pico2, pend_soporte, pend_resistencia, ancho_medio_pct,
         consistencia_ancho, peor_excursion_pct, probabilidad_forma) = opciones[0]
        n_decentes = sum(1 for o in opciones if o[13] >= 0.3) - 1

        volumen_ratio = 0.0
        if volume is not None:
            fin_v = min(idx_pico2 + dias_ventana_volumen, n)
            tramo_vol = volume[idx_pico2:fin_v]
            tramo_media = vol_media[idx_pico2:fin_v]
            validos = ~np.isnan(tramo_media) & (tramo_media > 0)
            if validos.any():
                volumen_ratio = float((tramo_vol[validos] / tramo_media[validos]).max())
        score_volumen = min(volumen_ratio / vol_mult_ideal, 1.0)

        candidatos.append(CandidatoCanal(
            idx_fondo1=idx_fondo1, idx_pico1=idx_pico1, idx_fondo2=idx_fondo2, idx_pico2=idx_pico2,
            precio_fondo1=round(float(precio_fondo1), 6), precio_pico1=round(float(precio_pico1), 6),
            precio_fondo2=round(float(precio_fondo2), 6), precio_pico2=round(float(precio_pico2), 6),
            probabilidad_forma=round(probabilidad_forma, 3),
            pendiente_soporte_pct_dia=round(pend_soporte, 3),
            pendiente_resistencia_pct_dia=round(pend_resistencia, 3),
            ancho_medio_pct=round(ancho_medio_pct, 2), consistencia_ancho=round(consistencia_ancho, 3),
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
    paralelismo_tolerancia_pct_dia: float = 0.5,
    ancho_ideal_pct: float = 8.0,
    ancho_tolerancia_exceso_pct: float = 10.0,
    consistencia_tolerancia: float = 0.5,
    contencion_tolerancia_pct: float = 10.0,
    peso_pendiente: float = 0.05,
    peso_paralelismo: float = 0.20,
    peso_ancho: float = 0.30,
    peso_consistencia: float = 0.10,
    peso_contencion: float = 0.35,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoCanal]:
    return _detectar(df, "subida", dias_min_tramo, dias_max_tramo, pendiente_ideal_pct_dia,
                      paralelismo_tolerancia_pct_dia, ancho_ideal_pct, ancho_tolerancia_exceso_pct,
                      consistencia_tolerancia, contencion_tolerancia_pct, peso_pendiente, peso_paralelismo,
                      peso_ancho, peso_consistencia, peso_contencion, vol_mult_ideal, dias_ventana_volumen)


def detectar_descendente(
    df: pd.DataFrame,
    dias_min_tramo: int = 10,
    dias_max_tramo: int = 60,
    pendiente_ideal_pct_dia: float = 1.0,
    paralelismo_tolerancia_pct_dia: float = 0.5,
    ancho_ideal_pct: float = 8.0,
    ancho_tolerancia_exceso_pct: float = 10.0,
    consistencia_tolerancia: float = 0.5,
    contencion_tolerancia_pct: float = 10.0,
    peso_pendiente: float = 0.05,
    peso_paralelismo: float = 0.20,
    peso_ancho: float = 0.30,
    peso_consistencia: float = 0.10,
    peso_contencion: float = 0.35,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoCanal]:
    return _detectar(df, "bajada", dias_min_tramo, dias_max_tramo, pendiente_ideal_pct_dia,
                      paralelismo_tolerancia_pct_dia, ancho_ideal_pct, ancho_tolerancia_exceso_pct,
                      consistencia_tolerancia, contencion_tolerancia_pct, peso_pendiente, peso_paralelismo,
                      peso_ancho, peso_consistencia, peso_contencion, vol_mult_ideal, dias_ventana_volumen)


def detectar_lateral(
    df: pd.DataFrame,
    dias_min_tramo: int = 10,
    dias_max_tramo: int = 60,
    pendiente_ideal_pct_dia: float = 0.3,
    paralelismo_tolerancia_pct_dia: float = 0.5,
    ancho_ideal_pct: float = 8.0,
    ancho_tolerancia_exceso_pct: float = 10.0,
    consistencia_tolerancia: float = 0.5,
    contencion_tolerancia_pct: float = 10.0,
    peso_pendiente: float = 0.05,
    peso_paralelismo: float = 0.20,
    peso_ancho: float = 0.30,
    peso_consistencia: float = 0.10,
    peso_contencion: float = 0.35,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoCanal]:
    """Mercado lateral -- lo contrario de un canal: sin requisito de
    direccion (fondo2/pico2 puede quedar un poco mas arriba o mas abajo),
    y `pendiente_ideal_pct_dia` aqui es una TOLERANCIA (cuanto se puede
    inclinar antes de dejar de ser "plano"), no un objetivo a alcanzar --
    ver la rama `if lateral` en `_detectar` para la formula invertida."""
    return _detectar(df, "lateral", dias_min_tramo, dias_max_tramo, pendiente_ideal_pct_dia,
                      paralelismo_tolerancia_pct_dia, ancho_ideal_pct, ancho_tolerancia_exceso_pct,
                      consistencia_tolerancia, contencion_tolerancia_pct, peso_pendiente, peso_paralelismo,
                      peso_ancho, peso_consistencia, peso_contencion, vol_mult_ideal, dias_ventana_volumen)


# (peso_pendiente, peso_paralelismo, peso_ancho, peso_consistencia, peso_contencion) -- suman 1.0.
# Mismo mecanismo que el resto de detectores: varias configs con distinta
# dominancia para comprobar que el grid de pesos SI cambia que candidato gana.
PESOS_FORMA = [
    (0.05, 0.20, 0.30, 0.10, 0.35),  # equilibrado -- default, ancho+contencion+paralelismo dominantes (ver nota abajo)
    (0.55, 0.10, 0.15, 0.10, 0.10),  # pendiente dominante -- "que suba/baje claro" importa mas
    (0.10, 0.55, 0.10, 0.10, 0.15),  # paralelismo dominante -- dos lineas muy parecidas
    (0.10, 0.10, 0.55, 0.10, 0.15),  # ancho dominante -- canal amplio
    (0.10, 0.10, 0.10, 0.55, 0.15),  # consistencia de ancho dominante -- canal muy regular
    (0.10, 0.10, 0.10, 0.10, 0.60),  # contencion casi absoluta -- el precio no puede salirse de la banda
]

# Nota (11-sept-2026): el "equilibrado" ya NO reparte los pesos por igual.
# Se encontro que en una tendencia larga y suave (BTC 2022),
# pendiente+paralelismo+consistencia salen casi perfectos (>0.9) precisamente
# PORQUE la tendencia es larga y limpia -- promediar sobre mas dias reduce el
# ruido de esas 3 dimensiones. Eso permitia que un canal de 25% de ancho
# ganara a uno de 12% aunque su score_ancho fuera 0, porque solo pesaba 0.20
# del total. Ademas, el usuario encontro un fallo mas grave: los 4 puntos de
# anclaje pueden estar muy juntos (ancho pequeño) mientras el precio REAL
# entre ellos rompe el canal por completo (ejemplo real: BTC ene-feb 2022,
# ancho=5.5% en los 4 puntos, pero el precio real cayo un 24% entre medias).
# Se añadio `score_contencion` (5a dimension, recorre el camino real, no solo
# los 4 puntos) y se le da el peso mas alto (0.35) porque es la comprobacion
# mas fundamental de "esto es realmente un canal contenido".

# (ancho_ideal_pct, ancho_tolerancia_exceso_pct) -- ninguno de los dos es un
# numero fijo elegido a mano y ya esta: son un rango a probar, igual que
# caida_ideal_pct/velocidad_ideal_pct_dia en busqueda_grid_caida.py. Todavia
# NO se ha corrido el grid cruzado (ETH ajuste -> BTC/tiempo confirmacion)
# que decida cual generaliza mejor -- esto solo dispone el rango, pendiente
# de ese barrido como siguiente paso.
IDEALES_ANCHO = [
    (5.0, 5.0),    # canal estrecho, penaliza rapido pasarse
    (8.0, 10.0),   # el usado como default hasta ahora
    (12.0, 12.0),  # canal mas amplio, mas tolerante
    (15.0, 20.0),  # canal amplio, tolerancia laxa
]
