import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import json
import numpy as np
from laboratorio.patrones.canal_sobre_sistema_completo import cargar, simular_cuenta_con_canal
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada, UMBRAL_PENDIENTE
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp

CAPITAL_INICIAL = 1000.0

MONEDAS = {
    "ETH": lambda: cargar("ETHUSDT"),
    "BTC": lambda: cargar("BTCUSDT"),
    "XRP": cargar_xrp,
}

salida = {}
for nombre, cargador in MONEDAS.items():
    df, atr, rt, rs, pend, cl, cc = cargador()
    fechas = df["open_time"]
    close = df["close"].to_numpy()
    sin_filtro = np.zeros(len(df), dtype=bool)  # pendiente_acelerada SIN ningun filtro de contexto (los 8 probados fallaron)
    años_validos = [a for a in AÑOS if (fechas.dt.year == a).sum() > 300]

    precios = [{"f": fechas.iloc[i].strftime("%Y-%m-%d"), "c": round(float(close[i]), 4)} for i in range(len(df))]

    por_año = {}
    for año in años_validos:
        cand = candidatos_por_año(df, año)
        cap_base, tr_base, _, _ = simular_cuenta_con_canal(df, cand, atr, rt, rs, pend, cl, cc, fechas, usar_canal=False)
        cap_pend, tr_pend = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, sin_filtro)

        def _con_meta(trades):
            out, anterior = [], CAPITAL_INICIAL
            for t in trades:
                t = dict(t)
                t["ganancia"] = t["pnl_eur"] > 0
                anterior = t["capital_tras"]
                out.append(t)
            return out

        por_año[año] = {
            "base": {"capital_final": round(cap_base, 2), "trades": _con_meta(tr_base)},
            "pendiente": {"capital_final": round(cap_pend, 2), "trades": _con_meta(tr_pend)},
        }
        print(f"{nombre} {año}: BASE={cap_base:.2f} ({len(tr_base)} trades)  +pendiente_acelerada={cap_pend:.2f} ({len(tr_pend)} trades)")

    salida[nombre] = {"precios": precios, "anios": por_año}

out_path = "/private/tmp/claude-501/-Users-jorgeansotegui-Desktop-tr/e3884417-1986-415a-bdd2-35a04103dd15/scratchpad/dashboard_data.json"
with open(out_path, "w") as f:
    json.dump(salida, f)
print(f"\nGuardado en {out_path}")
