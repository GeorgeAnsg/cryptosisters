"""18-sept-2026: señal de "ráfaga" de noticias graves -- ver memoria
persistente project_corvus4_mecanismo_noticias. Suma en ventana rodante
del recuento diario de noticias en categorias graves (colapso_quiebra +
hackeo_seguridad por defecto), comparada contra un percentil CAUSAL
(expanding window, solo con datos ya conocidos hasta ese dia) -- nunca un
umbral fijo a mano, ver feedback_no_absolutos_todo_el_codigo.

Validado en la sesion anterior (solo en conversacion, no en fichero --
ver noticias_categorias.py) contra dos eventos conocidos: Terra/Luna
(mayo 2022) y FTX (nov 2022), ambos cayendo en percentil 92-99.7%. Este
fichero reconstruye esa logica de forma persistente para poder aplicarla
sistematicamente a todos los años segun vayan llegando."""
from __future__ import annotations

import datetime

import pandas as pd

from laboratorio.patrones.noticias_categorias import categorizar_noticias

CATEGORIAS_GRAVES_DEFECTO = ("colapso_quiebra", "hackeo_seguridad")


def construir_serie_diaria(noticias: list[dict], categorias: tuple[str, ...] = CATEGORIAS_GRAVES_DEFECTO,
                            fecha_ini: str | None = None, fecha_fin: str | None = None) -> pd.Series:
    """Serie diaria (índice = fecha, valor = nº de noticias de esas
    categorias ese dia). Rellena con 0 los dias sin noticias, para que la
    ventana rodante no salte huecos."""
    categorizadas = categorizar_noticias(noticias)
    fechas = [pd.Timestamp(n["fecha"]) for n in categorizadas
              if any(c in n["categorias"] for c in categorias)]
    ini = pd.Timestamp(fecha_ini) if fecha_ini else (min(fechas) if fechas else pd.Timestamp.today())
    fin = pd.Timestamp(fecha_fin) if fecha_fin else (max(fechas) if fechas else pd.Timestamp.today())
    indice = pd.date_range(ini, fin, freq="D")
    serie = pd.Series(0, index=indice, dtype=int)
    for f in fechas:
        if ini <= f <= fin:
            serie[f] += 1
    return serie


def rafaga_rodante(serie_diaria: pd.Series, ventana_dias: int = 5) -> pd.Series:
    """Suma rodante causal (solo pasado + dia actual) de la serie diaria."""
    return serie_diaria.rolling(window=ventana_dias, min_periods=1).sum()


def percentil_causal(serie: pd.Series, minimo_historia_dias: int = 30) -> pd.Series:
    """Percentil de cada valor respecto a TODO el historial visto hasta
    ese dia (expanding, sin mirar al futuro). Los primeros
    `minimo_historia_dias` quedan en NaN por falta de historial fiable.

    18-sept-2026: corregido el sesgo de "empate por abajo". La serie tiene
    muchisimos dias en 0 (dias sin ninguna noticia grave reciente) -- con
    la definicion "cuantos dias del historial son <= hoy" (percentile
    "weak"), un dia en 0 ya cuenta TODOS los demas dias en 0 a su favor,
    asi que sale con percentil ~50-60 en vez de cerca de 0, aunque no haya
    pasado nada. Se promedia con la version estricta ("<", sin contar los
    empates), que es el percentil "mean rank" estandar y no tiene ese
    sesgo -- confirmado empiricamente el 18-sept-2026: con ETH 2021-2022,
    ningun dia bajaba de percentil 50 antes de este cambio."""
    out = pd.Series(index=serie.index, dtype=float)
    valores = serie.to_numpy()
    for i in range(len(serie)):
        if i < minimo_historia_dias:
            continue
        historial = valores[: i + 1]
        debil = (historial <= valores[i]).mean()
        estricto = (historial < valores[i]).mean()
        out.iloc[i] = (debil + estricto) / 2 * 100
    return out


def construir_señal(noticias: list[dict], categorias: tuple[str, ...] = CATEGORIAS_GRAVES_DEFECTO,
                     ventana_dias: int = 5, minimo_historia_dias: int = 30,
                     fecha_ini: str | None = None, fecha_fin: str | None = None) -> pd.DataFrame:
    """Pipeline completo: noticias crudas -> df con recuento diario,
    ráfaga rodante y percentil causal."""
    diaria = construir_serie_diaria(noticias, categorias, fecha_ini, fecha_fin)
    rafaga = rafaga_rodante(diaria, ventana_dias)
    percentil = percentil_causal(rafaga, minimo_historia_dias)
    return pd.DataFrame({"recuento_diario": diaria, "rafaga": rafaga, "percentil_causal": percentil})
