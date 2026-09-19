"""
15-sept-2026: al revisar una por una las 3 operaciones perdedoras de ETH
2024 en el escenario "cambio de candidato" (pedido explicito del usuario),
se encontro que una de las tres (11-ago-2024) se abrio con probabilidad
0.03 -- en ese tramo (fin de julio a septiembre 2024) el propio detector
puntua TODOS los candidatos, largos y cortos, en torno a 0.03: esta
diciendo "esto es ruido", no un patron real, y aun asi `_abrir()` la toma
porque la rama "abrir estando en plano" no exige ningun minimo de
probabilidad -- solo la rama "cambiar de posicion" compara `prob` contra
algo. Ver observacion 0016 en el workspace de task-observer.

Aqui se prueba anadir un piso minimo de probabilidad para CUALQUIER
apertura (en plano o tras un cambio), barrido -- no un numero fijo a ojo
-- siguiendo `deteccion-flexible-patrones`. Ajuste en ETH 2024 (unica
moneda que se toca para elegir el piso), confirmacion SIN RETOCAR NADA en
BTC 2024 y despues en los 4 anios (2021-2024) x 2 monedas, igual que
`prueba_multi_anio.py`.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0  # ganador ya validado, sin retocar
PISO_PROB_GRID = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]  # 0.0 = sin piso (comportamiento actual)


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, umbral_switch, piso_prob):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    descartados_por_piso = 0
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
            if prob < piso_prob:
                descartados_por_piso += 1
                continue
            nueva = _abrir(idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
            continue
        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= umbral_switch:
            if prob < piso_prob:
                descartados_por_piso += 1
                continue
            _cerrar(abierta, idx, close[idx])
            nueva = _abrir(idx, direccion, prob)
            abierta = nueva

    if abierta is not None:
        _cerrar(abierta, abierta["t"].idx_salida, abierta["t"].precio_salida)

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, len(trades), ganadoras, drawdown_max_pct, descartados_por_piso


def _cargar(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_piso_probabilidad")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    return df, atr, racha_rota_techo, racha_rota_suelo


def ajuste_eth_2024():
    print("=== Ajuste del piso de probabilidad -- SOLO ETH 2024 ===")
    df, atr, rt, rs = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    mejor = None
    for piso in PISO_PROB_GRID:
        cap, n, gan, dd, desc = _simular(df, cand, atr, rt, rs, UMBRAL_SWITCH, piso)
        print(f"  piso={piso:.1f}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
              f"{n} trades, {gan} ganadoras, dd {dd:.2f}%, {desc} descartados por piso")
        if mejor is None or cap > mejor[1]:
            mejor = (piso, cap)
    print(f"  -> mejor piso en ETH 2024: {mejor[0]:.1f} ({mejor[1]:.2f}€)")
    return mejor[0]


def multi_anio(piso_elegido):
    print(f"\n=== Validacion multi-anio con piso={piso_elegido:.1f} (congelado, sin retocar) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a, _ = _simular(df, cand, atr, rt, rs, UMBRAL_SWITCH, 0.0)
            cap_piso, n_p, gan_p, dd_p, desc_p = _simular(df, cand, atr, rt, rs, UMBRAL_SWITCH, piso_elegido)
            gana = cap_piso > cap_actual
            print(f"  {año}: sin piso {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"con piso {cap_piso:.2f}€ ({n_p}/{gan_p}, dd {dd_p:.2f}%, {desc_p} descartadas) "
                  f"-- {'GANA' if gana else 'pierde'}")
            resultados.append({"moneda": moneda, "año": año, "capital_actual": round(cap_actual, 2),
                                "capital_piso": round(cap_piso, 2), "gana": gana})
    n_gana = sum(1 for r in resultados if r["gana"])
    print(f"\nResultado: gana en {n_gana} de {len(resultados)} combinaciones")
    return resultados


if __name__ == "__main__":
    piso = ajuste_eth_2024()
    multi_anio(piso)
