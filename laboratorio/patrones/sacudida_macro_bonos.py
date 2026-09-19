"""18-sept-2026: sacudida macro de bonos (calibracion), derivada de
calendario_macro_completo.py (ver /private/tmp/.../scratchpad -- ese script
probo 6 series FRED; de las 6, solo la subida de tipos en bonos paso el
chequeo de significancia (z-score contra el baseline de cualquier dia con
el SE real de cada grupo, no solo "parece distinto"). VIX y dolar salieron
z<1 en ambas direcciones -- ruido, no señal, descartados. Peiroleo y S&P500
quedaron en zona "sugerente pero no concluyente" (|z| 1.2-1.7) y no se
gradua todavia por falta de mas historia.

Calibracion por bandas de percentil causal (mismo "no absolutos" de
deteccion-flexible-patrones: nunca un unico umbral fijo, siempre un rango
de configuraciones/bandas compitiendo) de la VARIACION DIARIA de cada
serie, medida contra el retorno de ETH a 7 dias, con z-score real vs el
baseline de cualquier dia (1.22%, n=1445, 2021-2024):

  y2 (tipo a 2 años, DGS2 en FRED) -- gradiente limpio y monotono:
    percentil 90-95   n=79   media_7d=-0.20%  z=-1.18  (NO significativo)
    percentil 95-99   n=91   media_7d=-1.03%  z=-2.05  (real)
    percentil >=99    n=30   media_7d=-3.27%  z=-2.13  (real, mas fuerte)
  y10 (tipo a 10 años, DGS10) -- se rompe en el extremo (n=20, ruido):
    percentil 90-95   n=73   media_7d=-1.06%  z=-1.75  (rozando)
    percentil 95-99   n=66   media_7d=-1.91%  z=-2.32  (real)
    percentil >=99    n=20   media_7d=+0.99%  z=-0.10  (NO usar, invierte)

Por eso: y2 se gradua en 2 niveles utiles (fuerte/extrema; "leve" no pasa el
umbral de significancia y se trata como sin sacudida). y10 se usa binario
(fuerte = percentil>=95), sin nivel extremo.
"""
import bisect


def percentil_causal_serie(valores, minimo_historia=60):
    """Percentil causal (mean rank, expanding window), O(n log n) con
    bisect -- misma formula que el resto del proyecto."""
    out = [None] * len(valores)
    ordenados = []
    for i, v in enumerate(valores):
        if i >= minimo_historia and len(ordenados) > 0:
            nn = len(ordenados)
            estricto = bisect.bisect_left(ordenados, v) / nn
            debil = bisect.bisect_right(ordenados, v) / nn
            out[i] = (debil + estricto) / 2 * 100
        bisect.insort(ordenados, v)
    return out


def severidad_sacudida_y2(percentil_causal_variacion_diaria):
    """Solo direccion SUBIDA (subida de tipos a 2 años); la bajada no
    paso el chequeo de significancia (z=0.95) y no se gradua."""
    p = percentil_causal_variacion_diaria
    if p is None:
        return None
    if p >= 99:
        return "extrema"
    if p >= 95:
        return "fuerte"
    return None  # percentil 90-95 no es distinguible del baseline (z=-1.18)


def severidad_sacudida_y10(percentil_causal_variacion_diaria):
    """Solo direccion SUBIDA; binario, sin nivel extremo (n=20 invierte
    el patron, no es de fiar)."""
    p = percentil_causal_variacion_diaria
    if p is None:
        return None
    if p >= 95:
        return "fuerte"
    return None
