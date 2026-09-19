"""
Exporta a JSON los datos para el artefacto HTML de revision visual de
`prueba_cambio_candidato_fuerte.py` -- ETH y BTC, escenario base (sin
switch) y escenario con switch (umbral=0.0, el ganador validado en
cartera/README.md). Un solo fichero de export, no modifica la prueba
original.
"""
import json
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, R_FIJO, RIESGO_BASE_PCT, candidatos_2024, señales_racha,
)
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

UMBRAL_GANADOR = 0.0


def _simular_con_switch(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, umbral_switch):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    trades = []
    eventos = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
        if t is None:
            return None
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob, "t": t,
                "unidades": pos.unidades, "riesgo_dinero_eur": pos.riesgo_dinero}

    def _cerrar(pos, idx_cierre, precio_cierre, motivo):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_cierre - pos["t"].precio_entrada) * signo
        capital_antes = capital
        capital += pnl
        retorno_pct_precio = (precio_cierre / pos["t"].precio_entrada - 1) * 100 * signo
        eventos.append({
            "tipo": "ejecutado",
            "idx_entrada": pos["idx_entrada"], "idx_salida": idx_cierre,
            "fecha_entrada": str(fechas.iloc[pos["idx_entrada"]].date()),
            "fecha_salida": str(fechas.iloc[idx_cierre].date()),
            "direccion": pos["direccion"], "probabilidad": round(pos["probabilidad"], 3),
            "precio_entrada": round(pos["t"].precio_entrada, 2), "precio_salida": round(precio_cierre, 2),
            "motivo_salida": motivo, "retorno_pct_precio": round(retorno_pct_precio, 2),
            "riesgo_dinero_eur": round(pos["riesgo_dinero_eur"], 2),
            "pnl_eur": round(pnl, 2), "capital_antes": round(capital_antes, 2), "capital_despues": round(capital, 2),
        })
        trades.append({"pnl_eur": round(pnl, 2)})

    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        if abierta is not None and idx > abierta["t"].idx_salida:
            _cerrar(abierta, abierta["t"].idx_salida, abierta["t"].precio_salida, abierta["t"].motivo)
            abierta = None
        if abierta is None:
            nueva = _abrir(idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
            continue
        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= umbral_switch:
            _cerrar(abierta, idx, close[idx], "cambio_candidato_fuerte")
            nueva = _abrir(idx, direccion, prob)
            abierta = nueva
        else:
            eventos.append({
                "tipo": "descartado", "motivo_descarte": "ya_habia_posicion_abierta",
                "idx": idx, "fecha": str(fechas.iloc[idx].date()),
                "direccion": direccion, "probabilidad": round(prob, 3), "precio": round(close[idx], 2),
            })

    if abierta is not None:
        _cerrar(abierta, abierta["t"].idx_salida, abierta["t"].precio_salida, abierta["t"].motivo)

    eventos.sort(key=lambda e: e.get("idx_entrada", e.get("idx", 0)))
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, eventos, len(trades), ganadoras


def _serie_precio(df):
    return [{"fecha": str(f.date()), "precio": round(c, 2)}
            for f, c in zip(df["open_time"], df["close"].to_numpy())]


def main():
    out = {}
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="exportar_cambio_candidato_html")
        atr = atr_absoluto(df)
        cand = candidatos_2024(df)
        racha_rota_techo, racha_rota_suelo = señales_racha(df)

        cap_base, ev_base, n_base, gan_base = _simular_con_switch(
            df, cand, atr, racha_rota_techo, racha_rota_suelo, umbral_switch=999)
        cap_sw, ev_sw, n_sw, gan_sw = _simular_con_switch(
            df, cand, atr, racha_rota_techo, racha_rota_suelo, umbral_switch=UMBRAL_GANADOR)

        # recortar la serie de precio a 2024 (con margen de 5 dias antes por si un evento cae el 1-ene)
        fechas = df["open_time"]
        idxs_2024 = [i for i, f in enumerate(fechas) if f.year == 2024]
        i0, i1 = max(0, idxs_2024[0] - 3), idxs_2024[-1]

        out[moneda] = {
            "capital_inicial": CAPITAL_INICIAL,
            "base": {"capital_final": round(cap_base, 2), "n_trades": n_base, "ganadoras": gan_base, "eventos": ev_base},
            "switch": {"capital_final": round(cap_sw, 2), "n_trades": n_sw, "ganadoras": gan_sw, "eventos": ev_sw},
            "precio_serie": _serie_precio(df)[i0:i1 + 1],
        }
        print(f"{moneda}: base {cap_base:.2f}€ ({n_base}/{gan_base}) -- switch {cap_sw:.2f}€ ({n_sw}/{gan_sw})")

    with open("/tmp/cambio_candidato_datos.json", "w") as f:
        json.dump(out, f)
    print("guardado en /tmp/cambio_candidato_datos.json")


if __name__ == "__main__":
    main()
