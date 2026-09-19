"""
15-sept-2026, variante de prueba_racha_filtrada_por_pendiente.py: el
usuario propuso una forma distinta de medir "sigue siendo una tendencia
sana" -- en vez de la pendiente (ATR sobre una ventana fija), mirar la
ESTRUCTURA de maximos/minimos: mientras el retroceso desde el maximo mas
reciente de la propia operacion se mantenga por debajo de un porcentaje
(estructura de "minimos cada vez mas altos" intacta), ignorar el aviso de
racha rota: unicamente se corta cuando el retroceso desde el maximo
favorable ya alcanzado supera ese porcentaje. El usuario reconoce
explicitamente que en el otro lado (una posicion CONTRARIA a la tendencia,
ej. un corto abierto en pleno rally) SI tiene sentido que racha rota corte
enseguida -- este filtro solo se aplica al lado que va a favor de la
tendencia detectada por la propia racha.

Esto es una version "trailing" (depende del recorrido de CADA operacion
desde su entrada, no de un array global precalculado como pendiente o
racha rota), asi que no se puede montar con `senal_externa` de
`simular_trade` -- se reimplementa el bucle dia a dia aqui, igual que en
prueba_toma_beneficio_pct.py.

Barrido del umbral de retroceso (%), no un numero fijo a ojo -- 0.0 =
cualquier retroceso ya corta (equivalente a la racha rota original).
Ajuste SOLO en ETH 2024, confirmacion sin tocar nada en BTC 2024, y
despues multi-anio si supera la confirmacion.
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
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0
UMBRAL_RETROCESO_GRID = [0.0, 0.02, 0.03, 0.05, 0.07, 0.10, 0.13, 0.16, 0.20]


def _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                           senal_externa, umbral_retroceso):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    extremo_favorable = precio_entrada
    for i in range(idx_entrada + 1, fin + 1):
        if direccion == "largo":
            toca_stop = low[i] <= niveles.stop
            toca_objetivo = high[i] >= niveles.objetivo
            extremo_favorable = max(extremo_favorable, high[i])
            retroceso = (extremo_favorable - close[i]) / extremo_favorable
        else:
            toca_stop = high[i] >= niveles.stop
            toca_objetivo = low[i] <= niveles.objetivo
            extremo_favorable = min(extremo_favorable, low[i])
            retroceso = (close[i] - extremo_favorable) / extremo_favorable
        if toca_stop:
            return i, niveles.stop, "stop"
        if toca_objetivo:
            return i, niveles.objetivo, "objetivo"
        if senal_externa is not None and senal_externa[i] and retroceso >= umbral_retroceso:
            return i, close[i], "senal_externa"
    return fin, close[fin], "tiempo_maximo"


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, umbral_switch, umbral_retroceso):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, umbral_retroceso)
        if r is None:
            return None
        idx_salida, precio_salida, motivo = r
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob,
                "idx_salida": idx_salida, "precio_entrada": close[idx], "precio_salida": precio_salida,
                "unidades": pos.unidades}

    def _cerrar(pos, idx_cierre, precio_cierre):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_cierre - pos["precio_entrada"]) * signo
        capital += pnl
        curva.append((fechas.iloc[idx_cierre], capital))
        trades.append({"pnl_eur": pnl})

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

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, len(trades), ganadoras, drawdown_max_pct


def _cargar(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_racha_filtrada_por_retroceso")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    return df, atr, racha_rota_techo, racha_rota_suelo


def ajuste_eth_2024():
    print("=== Ajuste del umbral de retroceso (%% desde el maximo favorable de cada operacion) -- SOLO ETH 2024 ===")
    df, atr, rt, rs = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    mejor = None
    for umbral in UMBRAL_RETROCESO_GRID:
        cap, n, gan, dd = _simular(df, cand, atr, rt, rs, UMBRAL_SWITCH, umbral)
        print(f"  umbral_retroceso={umbral:.0%}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
              f"{n} trades, {gan} ganadoras, dd {dd:.2f}%")
        if mejor is None or cap > mejor[1]:
            mejor = (umbral, cap)
    print(f"  -> mejor umbral en ETH 2024: {mejor[0]:.0%} ({mejor[1]:.2f}€)")
    return mejor[0]


def confirmar_y_multi_anio(umbral_elegido):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con umbral={umbral_elegido:.0%} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, rt, rs, UMBRAL_SWITCH, 0.0)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, rt, rs, UMBRAL_SWITCH, umbral_elegido)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"con filtro retroceso {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append(gana)
    print(f"\nResultado: gana en {sum(resultados)} de {len(resultados)} combinaciones")


if __name__ == "__main__":
    umbral = ajuste_eth_2024()
    confirmar_y_multi_anio(umbral)
