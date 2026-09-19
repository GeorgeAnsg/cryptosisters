"""
Diagnostico (15-sept-2026): ¿por que el veto por canal ascendente/
descendente empeora ETH ligeramente (10390 vs 10662 sin filtro), a
diferencia de BTC donde ayuda mucho? Comparar, entrada por entrada, los
casos donde el canal vetó un corte que pendiente_acelerada sola SI habria
hecho -- y ver que paso despues con esa posicion en cada año.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada, UMBRAL_PENDIENTE
from laboratorio.patrones.pendiente_veto_canal import _en_tendencia_confirmada, simular_cuenta_veto_canal

df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
fechas = df["open_time"]
en_largo = _en_tendencia_confirmada(df, "largo")
en_corto = _en_tendencia_confirmada(df, "corto")
sin_filtro = np.zeros(len(df), dtype=bool)

for año in AÑOS:
    cand = candidatos_por_año(df, año)
    _, trades_sin = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, sin_filtro)
    cap_veto = simular_cuenta_veto_canal(df, cand, atr, rt, rs, pend, fechas, en_largo, en_corto)

    cortes_sin = [t for t in trades_sin if t["motivo"] == "pendiente_acelerada"]
    print(f"\n=== ETH {año}: sin_filtro cortes por pendiente_acelerada = {len(cortes_sin)} ===")
    for t in cortes_sin:
        idx_match = np.flatnonzero(fechas.dt.strftime("%Y-%m-%d").to_numpy() == t["fecha_salida"])
        if len(idx_match) == 0:
            continue
        i = int(idx_match[0])
        direccion = t["direccion"]
        vetado = en_largo[i] if direccion == "largo" else en_corto[i]
        if not vetado:
            continue
        # ¿que hizo el precio 10 dias despues del punto donde SIN_FILTRO habria cortado?
        close = df["close"].to_numpy()
        fin = min(i + 10, len(close) - 1)
        cambio_10d = (close[fin] / close[i] - 1) * 100
        siguio_favor = cambio_10d > 0 if direccion == "largo" else cambio_10d < 0
        print(f"  {t['fecha_entrada']}->{t['fecha_salida']} {direccion:5s} sin_filtro habria cortado con pnl={t['pnl_eur']:+7.2f}€  "
              f"VETADO por canal -- precio a 10d desde el corte: {cambio_10d:+.1f}%  "
              f"{'(el canal acerto -- la tendencia siguio)' if siguio_favor else '(el canal FALLO -- fue una reversion real)'}")
