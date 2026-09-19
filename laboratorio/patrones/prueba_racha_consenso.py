"""
Corrección al mecanismo de salida "racha rota" (motivada por revisión visual
15-sept-2026): con una sola combinación fija (N_LEN=4, M_DIAS=5, "el nuevo
candidato debe ser ESTRICTAMENTE más alto/bajo que el anterior o se rompe"),
se encontraron dos fallos reales y opuestos en la cuenta de 2024 de ETH:

1. HIPERSENSIBLE: una racha de 11 techos ascendentes durante 18 dias
   (06-feb a 20-feb-2024) se rompio por un candidato apenas -0.7% mas bajo
   el 24-feb -- cierre prematuro que se perdio una subida posterior del 40%.
2. CIEGA: una caida real del -14.6% entre el 08-abr y el 20-abr-2024 no
   disparo NADA, porque la racha en ese momento solo llevaba 3 puntos
   acumulados -- por debajo del umbral minimo N_LEN=4 que hace falta para
   que CUALQUIER ruptura cuente. La señal no se disparo hasta el 03-may,
   con el precio ya por debajo de la entrada.

Ambos fallos vienen del mismo defecto: una regla binaria de corte duro
sobre UNA sola combinacion de parametros -- exactamente el tipo de
"absoluto" que la metodologia de deteccion-flexible-patrones ya demostro
que degrada resultados quo se usa para DETECTAR patrones, aqui reaparecio
sin querer en la señal de SALIDA.

Idea a probar: aplicar la misma metodologia de consenso multi-configuracion
que ya funciono para doble suelo/techo -- varias combinaciones de
(N_LEN, M_DIAS, TOLERANCIA_PCT) corriendo a la vez, cada una vota si la
racha esta rota HOY; la señal real de salida solo se dispara cuando una
FRACCION suficiente de las configs coincide (fraccion tambien barrida, no
fijada a ojo). TOLERANCIA_PCT permite que el nuevo candidato sea hasta un
X% mas bajo/alto sin contar como ruptura (0% = comportamiento actual).

Validacion: se reutiliza integramente el mecanismo de cambio de candidato
fuerte ya validado (umbral_switch=0.0, cartera/README.md) -- aqui solo se
sustituye la señal_externa que usa, no se toca nada mas. Barrido en ETH,
confirmacion en BTC sin retocar el ganador.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import itertools

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, R_FIJO, RIESGO_BASE_PCT, candidatos_2024,
)
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

N_LEN_GRID = [2, 3, 4, 5, 6]
M_DIAS_GRID = [3, 5, 7, 10]
TOLERANCIA_GRID = [0.0, 0.01, 0.02, 0.03]
FRACCION_MINIMA_GRID = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
UMBRAL_SWITCH = 0.0  # ya validado en prueba_cambio_candidato_fuerte.py


def _racha_rota_una_config(puntos, n_len, m_dias, tolerancia, n_total, direccion_favorable):
    rota = np.zeros(n_total, dtype=bool)
    racha_len = 1
    anterior = None
    for idx, precio in puntos:
        if anterior is not None:
            dias = idx - anterior[0]
            if direccion_favorable == "creciente":
                va_a_favor = precio >= anterior[1] * (1 - tolerancia)
            else:
                va_a_favor = precio <= anterior[1] * (1 + tolerancia)
            if va_a_favor and dias <= m_dias:
                racha_len += 1
            else:
                if racha_len >= n_len:
                    rota[idx] = True
                racha_len = 1
        anterior = (idx, precio)
    return rota


def _racha_rota_consenso(puntos, n_total, direccion_favorable, fraccion_minima):
    configs = list(itertools.product(N_LEN_GRID, M_DIAS_GRID, TOLERANCIA_GRID))
    votos = np.zeros(n_total, dtype=float)
    for n_len, m_dias, tolerancia in configs:
        votos += _racha_rota_una_config(puntos, n_len, m_dias, tolerancia, n_total, direccion_favorable)
    return (votos / len(configs)) >= fraccion_minima


def _simular_con_switch(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, umbral_switch):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
        if t is None:
            return None
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob, "t": t, "unidades": pos.unidades}

    def _cerrar(pos, idx_cierre, precio_cierre):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_cierre - pos["t"].precio_entrada) * signo
        capital += pnl
        curva.append((fechas.iloc[idx_cierre], capital))
        trades.append({"pnl_eur": pnl})

    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        if abierta is not None and idx > abierta["t"].idx_salida:
            _cerrar(abierta, abierta["t"].idx_salida, abierta["t"].precio_salida)
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
        _cerrar(abierta, abierta["t"].idx_salida, abierta["t"].precio_salida)

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, len(trades), ganadoras, drawdown_max_pct


def main():
    resultados_por_moneda = {}
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_racha_consenso")
        atr = atr_absoluto(df)
        cand = candidatos_2024(df)
        n = len(df)
        puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
        puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
        resultados_por_moneda[moneda] = (df, cand, atr, n, puntos_techo, puntos_suelo)

    df_eth, cand_eth, atr_eth, n_eth, pt_eth, ps_eth = resultados_por_moneda["ETHUSDT"]
    print("=== ETH (ajuste de fraccion_minima, config grid fijo) ===")
    resultados = []
    for fraccion in FRACCION_MINIMA_GRID:
        rt = _racha_rota_consenso(pt_eth, n_eth, "creciente", fraccion)
        rs = _racha_rota_consenso(ps_eth, n_eth, "decreciente", fraccion)
        cap, n_tr, gan, dd = _simular_con_switch(df_eth, cand_eth, atr_eth, rt, rs, UMBRAL_SWITCH)
        r = {"fraccion_minima": fraccion, "capital_final": round(cap, 2),
             "retorno_pct": round((cap / CAPITAL_INICIAL - 1) * 100, 1),
             "n_trades": n_tr, "ganadoras": gan, "drawdown_max_pct": round(dd, 2)}
        resultados.append(r)
        print(" ", r)

    mejor = max(resultados, key=lambda r: r["capital_final"])
    en_borde = mejor["fraccion_minima"] in (min(FRACCION_MINIMA_GRID), max(FRACCION_MINIMA_GRID))
    print(f"mejor fraccion en ETH: {mejor} -- {'EN EL BORDE' if en_borde else 'dentro del rango'}")

    # baseline de referencia: config actual sin consenso (N_LEN=4,M_DIAS=5,tolerancia=0), ya conocido: 1743.22
    rt_actual = _racha_rota_una_config(pt_eth, 4, 5, 0.0, n_eth, "creciente")
    rs_actual = _racha_rota_una_config(ps_eth, 4, 5, 0.0, n_eth, "decreciente")
    cap_actual, n_actual, gan_actual, dd_actual = _simular_con_switch(df_eth, cand_eth, atr_eth, rt_actual, rs_actual, UMBRAL_SWITCH)
    print(f"baseline actual (N_LEN=4,M_DIAS=5,sin consenso) en ETH: capital {cap_actual:.2f} ({n_actual} trades, {gan_actual} ganadoras, dd {dd_actual:.2f}%)")

    df_btc, cand_btc, atr_btc, n_btc, pt_btc, ps_btc = resultados_por_moneda["BTCUSDT"]
    print("\n=== BTC (confirmación, sin retocar la fraccion ganadora) ===")
    rt_actual_btc = _racha_rota_una_config(pt_btc, 4, 5, 0.0, n_btc, "creciente")
    rs_actual_btc = _racha_rota_una_config(ps_btc, 4, 5, 0.0, n_btc, "decreciente")
    cap_actual_btc, n_actual_btc, gan_actual_btc, dd_actual_btc = _simular_con_switch(df_btc, cand_btc, atr_btc, rt_actual_btc, rs_actual_btc, UMBRAL_SWITCH)
    print(f"baseline actual en BTC: capital {cap_actual_btc:.2f} ({n_actual_btc} trades, {gan_actual_btc} ganadoras, dd {dd_actual_btc:.2f}%)")

    rt_btc = _racha_rota_consenso(pt_btc, n_btc, "creciente", mejor["fraccion_minima"])
    rs_btc = _racha_rota_consenso(ps_btc, n_btc, "decreciente", mejor["fraccion_minima"])
    cap_btc, n_btc_tr, gan_btc, dd_btc = _simular_con_switch(df_btc, cand_btc, atr_btc, rt_btc, rs_btc, UMBRAL_SWITCH)
    print(f"consenso fraccion={mejor['fraccion_minima']} en BTC: capital {cap_btc:.2f} ({n_btc_tr} trades, {gan_btc} ganadoras, dd {dd_btc:.2f}%)")


if __name__ == "__main__":
    main()
