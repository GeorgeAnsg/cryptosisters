"""
Analisis a peticion del usuario (15-sept-2026): ¿que diferencia BTC 2022
(pendiente_acelerada mejora +24%) de BTC 2023 (empeora -25%) y de XRP 2024
(empeora -8.3%)? Version 2: comparar, entrada por entrada, el PnL real
del corte de pendiente_acelerada contra lo que BASE (sin ese corte)
consiguio en la MISMA entrada -- eso aisla si el problema es "el corte en
si pierde dinero" o "el corte gana poco pero se deja mucho beneficio
sobre la mesa que BASE si cobra".
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada, UMBRAL_PENDIENTE

CASOS = [("BTC", 2022, lambda: cargar("BTCUSDT")), ("BTC", 2023, lambda: cargar("BTCUSDT")), ("XRP", 2024, cargar_xrp)]

for nombre, año, cargador in CASOS:
    df, atr, rt, rs, pend, cl, cc = cargador()
    fechas = df["open_time"]
    close = df["close"].to_numpy()
    mask_año = fechas.dt.year == año
    idx_año = np.flatnonzero(mask_año.to_numpy())
    precios_año = close[idx_año]
    ret_año = (precios_año[-1] / precios_año[0] - 1) * 100

    cand = candidatos_por_año(df, año)
    sin_filtro = np.zeros(len(df), dtype=bool)
    cap_base, trades_base = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, 999.0, sin_filtro)  # umbral imposible = nunca corta por pendiente = BASE real
    cap_pend, trades_pend = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, sin_filtro)

    base_por_entrada = {t["fecha_entrada"]: t for t in trades_base}

    print(f"\n{'='*78}\n{nombre} {año}: retorno del año {ret_año:+.1f}%  |  BASE={cap_base:.2f}  PEND={cap_pend:.2f}\n{'='*78}")
    cortes = [t for t in trades_pend if t["motivo"] == "pendiente_acelerada"]
    total_oportunidad_perdida = 0.0
    for t in cortes:
        gemelo = base_por_entrada.get(t["fecha_entrada"])
        if gemelo is None:
            print(f"  {t['fecha_entrada']} {t['direccion']:5s}: PEND corta con pnl={t['pnl_eur']:+7.2f}€  -- (sin gemelo exacto en BASE, la cuenta ya habia divergido antes)")
            continue
        diff = gemelo["pnl_eur"] - t["pnl_eur"]
        total_oportunidad_perdida += diff
        print(f"  {t['fecha_entrada']} {t['direccion']:5s}: PEND corta {t['fecha_salida']} pnl={t['pnl_eur']:+7.2f}€   "
              f"BASE (misma entrada) cierra {gemelo['fecha_salida']} via {gemelo['motivo']:18s} pnl={gemelo['pnl_eur']:+7.2f}€   "
              f"diferencia={diff:+7.2f}€")
    print(f"  TOTAL diferencia (BASE - PEND) en las entradas con gemelo exacto: {total_oportunidad_perdida:+.2f}€")
