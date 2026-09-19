import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
import pandas as pd
from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada

# regimen_mercado.py deja escrito que DIST_MEDIA200_IDEAL_PCT=10.0 y
# PENDIENTE_MEDIA200_IDEAL_PCT=5.0 estan heredados sin calibrar. En vez de un
# numero fijo compartido por todos los activos, se deriva el "ideal" de
# saturacion de un PERCENTIL de la propia distribucion historica del activo,
# calculado de forma causal (solo con datos hasta el dia i, ventana expansiva
# -- nunca mirando al futuro). Misma formula para cualquier moneda; lo que
# cambia es el numero que la propia moneda genera con su historia.
WARMUP = 220  # SMA200 + 20 dias de pendiente, igual que exige el motor


def _dist_y_pendiente(df):
    close = df["close"].to_numpy()
    sma200 = df["close"].rolling(200).mean()
    n = len(df)
    dist_pct = np.full(n, np.nan)
    pendiente_pct = np.full(n, np.nan)
    for i in range(200, n):
        media = sma200.iloc[i]
        media_20 = sma200.iloc[i - 20] if i >= 220 else np.nan
        if media != media:
            continue
        dist_pct[i] = (media - close[i]) / media * 100
        if media_20 == media_20:
            pendiente_pct[i] = (media_20 - media) / media_20 * 100
    return dist_pct, pendiente_pct


def _en_neutro_adaptativo(df, percentil):
    dist_pct, pendiente_pct = _dist_y_pendiente(df)
    n = len(df)
    activo = np.zeros(n, dtype=bool)
    for i in range(WARMUP, n):
        hist_dist = np.abs(dist_pct[WARMUP:i])
        hist_pend = np.abs(pendiente_pct[WARMUP:i])
        hist_dist = hist_dist[~np.isnan(hist_dist)]
        hist_pend = hist_pend[~np.isnan(hist_pend)]
        if len(hist_dist) < 30 or len(hist_pend) < 30:
            continue  # muy poca historia causal todavia -- no clasifica, no cuenta como neutro
        dist_ideal = np.percentile(hist_dist, percentil)
        pendiente_ideal = np.percentile(hist_pend, percentil)
        d, p = dist_pct[i], pendiente_pct[i]
        if d != d or p != p:
            continue
        debajo, cayendo = d > 0, p > 0
        encima, subiendo = d < 0, p < 0
        marcado_bajista = debajo and cayendo and (abs(d) >= dist_ideal * 0.5 or abs(p) >= pendiente_ideal * 0.5)
        marcado_alcista = encima and subiendo and (abs(d) >= dist_ideal * 0.5 or abs(p) >= pendiente_ideal * 0.5)
        if not marcado_bajista and not marcado_alcista:
            activo[i] = True
    return activo


if __name__ == "__main__":
    PERCENTIL_GRID = [50, 60, 70, 75, 80, 90]
    UMBRAL_PENDIENTE = 1.5

    print("=== AJUSTE en ETH: grid de percentil ===")
    df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
    fechas = df["open_time"]
    mejor = None
    for pct in PERCENTIL_GRID:
        en_neu = _en_neutro_adaptativo(df, pct)
        total = 0.0
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap, tr = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, en_neu)
            total += cap
        print(f"  percentil={pct}: total={total:.2f}  (dias neutro: {en_neu.sum()}/{len(df)})")
        if mejor is None or total > mejor[0]:
            mejor = (total, pct)
    print(f"GANADOR ETH: percentil={mejor[1]} -> {mejor[0]:.2f}")
    print("  (ref ETH: BASE=9490.02, pendiente sin filtro=10662.53, regimen NEUTRO fijo=10440.01)")

    pct_ganador = mejor[1]
    print(f"\n=== CONFIRMACIÓN congelada (percentil={pct_ganador}) en BTC ===")
    dfb, atrb, rtb, rsb, pendb, clb, ccb = cargar("BTCUSDT")
    fechasb = dfb["open_time"]
    en_neu_b = _en_neutro_adaptativo(dfb, pct_ganador)
    totalb = 0.0
    for año in AÑOS:
        cand = candidatos_por_año(dfb, año)
        cap, tr = simular_cuenta_filtrada(dfb, cand, atrb, rtb, rsb, pendb, fechasb, UMBRAL_PENDIENTE, en_neu_b)
        totalb += cap
        print(f"  {año}: {cap:.2f}")
    print(f"  BTC TOTAL={totalb:.2f}  (ref BASE=8863.09, pendiente sin filtro=8882.40, regimen NEUTRO fijo=8951.12)")
