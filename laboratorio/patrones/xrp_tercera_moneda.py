import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
import pandas as pd

from datos.cargar import cargar_ohlcv
from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.canal_sobre_sistema_completo import simular_cuenta_con_canal, _canal_en_contra
from laboratorio.patrones.pendiente_filtro_regimen import _en_neutro
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada
from motores.volatilidad import atr_absoluto
import laboratorio.patrones.sistema_confirmado_switch_14sept2026 as sc

CORTE_DESARROLLO = pd.Timestamp("2025-01-01", tz="UTC")


def _resample_diario_desde_4h(par):
    df4h = cargar_ohlcv(par, "4h")
    df4h = df4h[df4h["open_time"] < CORTE_DESARROLLO].reset_index(drop=True)
    df4h = df4h.set_index("open_time")
    diario = df4h.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    diario = diario.dropna().reset_index()
    return diario


def cargar_xrp():
    df = _resample_diario_desde_4h("XRPUSDT")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    rt = _racha_rota(puntos_techo, sc.N_LEN, sc.M_DIAS, n, direccion_favorable="creciente")
    rs = _racha_rota(puntos_suelo, sc.N_LEN, sc.M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    canal_largo, canal_corto = _canal_en_contra(df)
    return df, atr, rt, rs, pendiente, canal_largo, canal_corto


print("=== XRP resample diario desde 4h (limpio, ya en el repo) ===")
df, atr, rt, rs, pend, cl, cc = cargar_xrp()
print(f"  {len(df)} velas diarias, {df['open_time'].min().date()} -> {df['open_time'].max().date()}")
fechas = df["open_time"]

AÑOS_XRP = [a for a in AÑOS if ((fechas.dt.year == a).sum() > 300)]
print(f"  años con cobertura completa: {AÑOS_XRP}")

print("\n=== BASE vs pendiente_acelerada (u=1.5) sin filtro, año a año ===")
sin_filtro = np.zeros(len(df), dtype=bool)
for año in AÑOS_XRP:
    cand = candidatos_por_año(df, año)
    cap_base, tr_base, _, _ = simular_cuenta_con_canal(df, cand, atr, rt, rs, pend, cl, cc, fechas, usar_canal=False)
    cap_pend, tr_pend = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, 1.5, sin_filtro)
    delta = (cap_pend - cap_base) / cap_base * 100
    print(f"  {año}: BASE={cap_base:.0f}  PEND={cap_pend:.0f}  delta={delta:+.1f}%  (trades base={len(tr_base)}, trades pend={len(tr_pend)})")

print("\n=== BASE vs pendiente+filtro régimen NEUTRO (congelado, sin retocar nada) ===")
en_neutro = _en_neutro(df)
print(f"  dias NEUTRO: {en_neutro.sum()}/{len(df)} ({en_neutro.sum()/len(df)*100:.1f}%)")
total_base, total_filtro = 0.0, 0.0
for año in AÑOS_XRP:
    cand = candidatos_por_año(df, año)
    cap_base, tr_base, _, _ = simular_cuenta_con_canal(df, cand, atr, rt, rs, pend, cl, cc, fechas, usar_canal=False)
    cap_filtro, tr_filtro = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, 1.5, en_neutro)
    total_base += cap_base
    total_filtro += cap_filtro
    print(f"  {año}: BASE={cap_base:.0f}  +regimen={cap_filtro:.0f}")
print(f"  TOTAL: BASE={total_base:.2f}  +regimen={total_filtro:.2f}")

print("\n=== Hit-rate de cortes reales por pendiente_acelerada (igual que en BTC/ETH) ===")
from laboratorio.patrones.pendiente_filtro_lateral import simular_trade_filtrado
from salidas.stop_objetivo import calcular_niveles_fijos
close = df["close"].to_numpy()
n = len(df)
HORIZONTE = 10
for año in AÑOS_XRP:
    cand = candidatos_por_año(df, año)
    buenos, malos = 0, 0
    abierta = None
    for idx, direccion, prob in cand:
        if np.isnan(atr[idx]):
            continue
        if abierta is not None and idx > abierta["idx_salida"]:
            abierta = None
        if abierta is None:
            niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, sc.K_ATR_STOP, sc.R_FIJO)
            senal = rt if direccion == "largo" else rs
            r = simular_trade_filtrado(df, idx, direccion, close[idx], niveles, 45, senal, pend, 1.5, sin_filtro)
            if r is None:
                continue
            abierta = dict(idx_entrada=idx, idx_salida=r["idx_salida"], motivo=r["motivo"], direccion=direccion)
            if r["motivo"] == "pendiente_acelerada":
                i_corte = r["idx_salida"]
                if i_corte + HORIZONTE < n:
                    precio_corte = close[i_corte]
                    precio_post = close[i_corte + HORIZONTE]
                    adverso = (precio_post < precio_corte) if direccion == "largo" else (precio_post > precio_corte)
                    if adverso:
                        buenos += 1
                    else:
                        malos += 1
    tot = buenos + malos
    if tot:
        print(f"  {año}: cortes={tot}  buenos={buenos} ({buenos/tot*100:.0f}%)  malos={malos} ({malos/tot*100:.0f}%)")

p = pend[~np.isnan(pend)]
frac_supera = (np.abs(p) >= 1.5).mean() * 100
print(f"\n  % dias con |pendiente|>=1.5 ATR en XRP: {frac_supera:.1f}%  (media={np.abs(p).mean():.2f})  -- ref ETH=28.8%/1.15, BTC=29.4%/1.17")
