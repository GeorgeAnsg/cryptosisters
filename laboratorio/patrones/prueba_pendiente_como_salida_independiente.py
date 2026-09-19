"""
14-sept-2026: los 3 trades perdedores de la variante "caida relativa de
pendiente" (prueba_racha_filtrada_por_caida_pendiente.py) tienen un patron
comun confirmado dato a dato: suben rapido y limpio (3-13 dias) hasta un
techo, y luego bajan LENTO en zigzag (0.7-0.9%/dia) durante 18-25 dias. En
2 de los 3, `racha_rota_techo` NUNCA se activa durante todo el trade (el
detector de doble techo no llega a confirmar un patron con una bajada tan
serrada) -- por eso ninguna variante que ES UN FILTRO sobre la señal de
racha rota (pendiente fija, retroceso, caida relativa) puede arreglarlos:
la señal de la que dependen no llega nunca.

Esta variante prueba la idea obvia: usar la caida relativa de pendiente
como señal de salida INDEPENDIENTE, sin esperar a racha_rota. Se abre con
el mismo motor de siempre y se cierra en cuanto la pendiente (favorable)
cae un % relativo desde su propio maximo alcanzado en la operacion -- YA
NO hace falta que racha_rota se haya disparado.

Riesgo obvio: sin la exigencia de racha_rota, este disparador puede ser
mucho mas sensible y cortar operaciones sanas en su fase normal de
respiracion. Por eso se barre el umbral igual que las variantes
anteriores, ajuste SOLO en ETH 2024, confirmacion en BTC 2024 sin tocar
nada, y despues multi-anio.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0
UMBRAL_CAIDA_RELATIVA_GRID = [999, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
# 999 = nunca corta por esta via (equivale al motor actual, sin este disparador)
DIAS_GRACIA = 3
# no evaluar el disparador hasta pasados N dias -- si no, corta en la
# propia respiracion normal de los primeros dias de cualquier operacion


def _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                           pendiente, umbral_caida_relativa):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    pendiente_extremo = 0.0
    for i in range(idx_entrada + 1, fin + 1):
        if direccion == "largo":
            toca_stop = low[i] <= niveles.stop
            toca_objetivo = high[i] >= niveles.objetivo
        else:
            toca_stop = high[i] >= niveles.stop
            toca_objetivo = low[i] <= niveles.objetivo
        if toca_stop:
            return i, niveles.stop, "stop"
        if toca_objetivo:
            return i, niveles.objetivo, "objetivo"
        p = pendiente[i]
        if not np.isnan(p):
            if direccion == "largo":
                pendiente_extremo = max(pendiente_extremo, p)
            else:
                pendiente_extremo = min(pendiente_extremo, p)
            if i - idx_entrada > DIAS_GRACIA and umbral_caida_relativa < 999:
                if direccion == "largo":
                    listón = pendiente_extremo * (1 - umbral_caida_relativa)
                    honra_corte = pendiente_extremo > 0 and p <= listón
                else:
                    listón = pendiente_extremo * (1 - umbral_caida_relativa)
                    honra_corte = pendiente_extremo < 0 and p >= listón
                if honra_corte:
                    return i, close[i], "caida_pendiente_independiente"
    return fin, close[fin], "tiempo_maximo"


def _simular(df, candidatos, atr, pendiente, umbral_switch, umbral_caida):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, pendiente, umbral_caida)
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
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_pendiente_como_salida_independiente")
    atr = atr_absoluto(df)
    pendiente = _pendiente_atr(df, atr)
    return df, atr, pendiente


def ajuste_eth_2024():
    print("=== Ajuste: caida relativa de pendiente como SALIDA INDEPENDIENTE -- SOLO ETH 2024 ===")
    df, atr, pendiente = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    mejor = None
    for umbral in UMBRAL_CAIDA_RELATIVA_GRID:
        cap, n, gan, dd = _simular(df, cand, atr, pendiente, UMBRAL_SWITCH, umbral)
        etiqueta = "sin disparador (actual)" if umbral >= 999 else f"{umbral:.0%}"
        print(f"  umbral={etiqueta}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
              f"{n} trades, {gan} ganadoras, dd {dd:.2f}%")
        if mejor is None or cap > mejor[1]:
            mejor = (umbral, cap)
    print(f"  -> mejor umbral en ETH 2024: {mejor[0]} ({mejor[1]:.2f}€)")
    return mejor[0]


def confirmar_y_multi_anio(umbral_elegido):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con umbral={umbral_elegido} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, pendiente = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, pendiente, UMBRAL_SWITCH, 999)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, pendiente, UMBRAL_SWITCH, umbral_elegido)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"salida independiente {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append(gana)
    print(f"\nResultado: gana en {sum(resultados)} de {len(resultados)} combinaciones")


if __name__ == "__main__":
    umbral = ajuste_eth_2024()
    confirmar_y_multi_anio(umbral)
