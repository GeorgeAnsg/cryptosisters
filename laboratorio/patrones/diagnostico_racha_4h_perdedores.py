"""
18-sept-2026: ni el gating por tamaño de ganancia (`racha_confirmacion_4h_condicional_por_ganancia`,
3/8) ni el gating por regimen de volatilidad (`racha_confirmacion_regimen.py`, 4/8) mejoran el
5/8 del racha_confirmacion_4h simple (velas_persistencia=6, siempre activo). Ambos eran hipotesis
sobre CUAL podia ser la variable que separa los combos que ganan de los que pierden -- ninguna se
sostuvo. En vez de seguir adivinando una tercera variable, este script mira operacion por
operacion los TRES combos que pierden en holdout (ETH-2024, BTC-2023, BTC-2024) comparando
exactamente que trade difiere entre el mecanismo actual y el racha_4h (velas=6), y por que motivo/
pnl, para encontrar la variable real en vez de proponerla a ciegas.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año
from laboratorio.patrones.racha_confirmacion_4h import _cargar_4h, _simular_trade_manual_racha_4h
from laboratorio.patrones.trailing_retroceso_alto import (
    UMBRAL_CAIDA_FILTRO, UMBRAL_SWITCH, _simular_trade_manual,
)

# Mismos valores que usa `confirmar_holdout_4h` (racha_confirmacion_4h.py) para "actual":
# activacion_pct=0.10, retroceso_pct=999 neutraliza el trailing propio de
# trailing_retroceso_alto.py, aislando el mecanismo de confirmacion de racha_rota que es
# lo que se esta comparando aqui.
ACTIVACION_ACTUAL = 0.10
RETROCESO_ACTUAL = 999
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

VELAS_PERSISTENCIA = 6


def _simular_con_trades(df, df4h, inicio4h, fin4h, candidatos, atr, racha_rota_techo, racha_rota_suelo,
                         pendiente, pendiente4h, umbral_switch, modo):
    """modo='actual' usa _simular_trade_manual (mecanismo hoy en produccion);
    modo='4h' usa _simular_trade_manual_racha_4h (velas_persistencia=6).
    Devuelve la lista de trades con fecha de entrada/salida, motivo y pnl."""
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        if modo == "actual":
            r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                                       senal, pendiente, UMBRAL_CAIDA_FILTRO, ACTIVACION_ACTUAL,
                                       RETROCESO_ACTUAL)
        else:
            r = _simular_trade_manual_racha_4h(df, df4h, inicio4h, fin4h, idx, direccion, close[idx], niveles,
                                                DIAS_MAXIMO, senal, pendiente4h, UMBRAL_CAIDA_FILTRO,
                                                VELAS_PERSISTENCIA)
        if r is None:
            return None
        idx_salida, precio_salida, motivo = r
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob,
                "idx_salida": idx_salida, "precio_entrada": close[idx], "precio_salida": precio_salida,
                "unidades": pos.unidades, "motivo": motivo}

    def _cerrar(pos, idx_cierre, precio_cierre):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_cierre - pos["precio_entrada"]) * signo
        capital += pnl
        trades.append({
            "fecha_entrada": str(fechas.iloc[pos["idx_entrada"]])[:10],
            "fecha_salida": str(fechas.iloc[idx_cierre])[:10],
            "direccion": pos["direccion"], "motivo": pos.get("motivo"),
            "pnl_eur": pnl, "pnl_pct": (precio_cierre / pos["precio_entrada"] - 1) * signo * 100,
        })

    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        if abierta is not None and idx > abierta["idx_salida"]:
            _cerrar(abierta, abierta["idx_salida"], abierta["precio_salida"])
            abierta = None
        if abierta is None:
            nueva = _abrir(idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
            continue
        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= umbral_switch:
            _cerrar(abierta, idx, close[idx])
            nueva = _abrir(idx, direccion, prob)
            abierta = nueva

    if abierta is not None:
        _cerrar(abierta, abierta["idx_salida"], abierta["precio_salida"])
    return trades, capital


def comparar(moneda, año):
    df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente, pendiente4h = _cargar_4h(moneda)
    cand = candidatos_por_año(df, año)
    t_actual, cap_actual = _simular_con_trades(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente,
                                                pendiente4h, UMBRAL_SWITCH, "actual")
    t_4h, cap_4h = _simular_con_trades(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente,
                                        pendiente4h, UMBRAL_SWITCH, "4h")
    print(f"\n{'='*90}\n{moneda} {año}: actual {cap_actual:.2f}€ ({len(t_actual)} trades) vs "
          f"4h {cap_4h:.2f}€ ({len(t_4h)} trades)\n{'='*90}")
    n = min(len(t_actual), len(t_4h))
    for i in range(n):
        a, b = t_actual[i], t_4h[i]
        marca = "  " if (a["fecha_entrada"] == b["fecha_entrada"] and a["motivo"] == b["motivo"]) else ">>"
        print(f"{marca} #{i+1} {a['direccion']:>5} entra {a['fecha_entrada']} | "
              f"ACTUAL sale {a['fecha_salida']} {a['motivo']:<14} {a['pnl_pct']:+7.2f}% "
              f"| 4H sale {b['fecha_salida']} {b['motivo']:<14} {b['pnl_pct']:+7.2f}%  "
              f"(dif entrada 4h: {b['fecha_entrada']})")
    if len(t_actual) != len(t_4h):
        print(f"  [!] numero de trades distinto ({len(t_actual)} vs {len(t_4h)}) a partir de aqui, "
              f"la comparacion 1-a-1 deja de ser exacta")
        resto = t_actual[n:] if len(t_actual) > n else t_4h[n:]
        for t in resto:
            print(f"      extra: {t['fecha_entrada']} -> {t['fecha_salida']} {t['motivo']} {t['pnl_pct']:+.2f}%")


if __name__ == "__main__":
    for moneda, año in [("ETHUSDT", 2024), ("BTCUSDT", 2023), ("BTCUSDT", 2024)]:
        comparar(moneda, año)
