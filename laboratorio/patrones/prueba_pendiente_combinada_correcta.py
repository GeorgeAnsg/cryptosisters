"""
14-sept-2026: correccion de prueba_pendiente_como_salida_independiente.py.
Aquella prueba comparaba contra un baseline SIN racha_rota (motor
desactivado del todo), lo que triplicaba el numero de operaciones al año
(13 -> 45) -- sintoma claro de sobreoperar, no de una mejora real.

Esta version SI usa el baseline correcto (el sistema real con racha_rota
+ caida relativa de pendiente como filtro, prueba_racha_filtrada_por_caida_pendiente.py,
umbral=30%, 1743.22€ -> 1920.90€ en ETH 2024) y AÑADE la caida de pendiente
como disparador independiente SOLO cuando racha_rota lleva mucho tiempo sin
dispararse (para no duplicar ni sustituir el mecanismo que ya funciona bien,
solo cubrir el hueco donde racha_rota nunca llega -- la "racha rota ciega").
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
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0
UMBRAL_CAIDA_FILTRO = 0.3  # el ya elegido y congelado para el filtro sobre racha_rota
DIAS_GRACIA = 3

# barremos el numero de dias sin racha_rota tras los que se activa el
# disparador independiente -- 999 = nunca (equivale al sistema actual)
DIAS_SIN_SENAL_GRID = [999, 25, 20, 15, 12, 10, 8]
UMBRAL_CAIDA_INDEPENDIENTE = 0.5  # umbral de caida relativa para el disparador de respaldo


def _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                           senal_externa, pendiente, umbral_caida_filtro,
                           dias_sin_senal_max, umbral_caida_independiente):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    pendiente_extremo = 0.0
    ultimo_dia_senal = idx_entrada  # ultima vez que racha_rota dio señal (para medir "cuanto lleva sin avisar")
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

        hay_senal = senal_externa is not None and senal_externa[i]
        if hay_senal:
            ultimo_dia_senal = i
            if not np.isnan(p):
                if direccion == "largo":
                    listón = pendiente_extremo * (1 - umbral_caida_filtro)
                    honra_corte = pendiente_extremo <= 0 or p <= listón
                else:
                    listón = pendiente_extremo * (1 - umbral_caida_filtro)
                    honra_corte = pendiente_extremo >= 0 or p >= listón
                if honra_corte:
                    return i, close[i], "senal_externa"
            else:
                return i, close[i], "senal_externa"
        else:
            # disparador de respaldo: si llevamos demasiado tiempo sin que
            # racha_rota avise NUNCA, y la pendiente ya se ha desplomado
            # desde su propio maximo, salir de todos modos
            dias_sin_senal = i - ultimo_dia_senal
            if (dias_sin_senal_max < 999 and dias_sin_senal >= dias_sin_senal_max
                    and i - idx_entrada > DIAS_GRACIA and not np.isnan(p)):
                if direccion == "largo":
                    listón = pendiente_extremo * (1 - umbral_caida_independiente)
                    honra_corte = pendiente_extremo > 0 and p <= listón
                else:
                    listón = pendiente_extremo * (1 - umbral_caida_independiente)
                    honra_corte = pendiente_extremo < 0 and p >= listón
                if honra_corte:
                    return i, close[i], "caida_pendiente_respaldo"
    return fin, close[fin], "tiempo_maximo"


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente,
             umbral_switch, umbral_caida_filtro, dias_sin_senal_max, umbral_caida_independiente):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, pendiente,
                                   umbral_caida_filtro, dias_sin_senal_max, umbral_caida_independiente)
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
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_pendiente_combinada_correcta")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    return df, atr, racha_rota_techo, racha_rota_suelo, pendiente


def ajuste_eth_2024():
    print("=== Ajuste: dias sin señal para activar el disparador de respaldo -- SOLO ETH 2024 ===")
    df, atr, rt, rs, pendiente = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    mejor = None
    for dias in DIAS_SIN_SENAL_GRID:
        cap, n, gan, dd = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                    UMBRAL_CAIDA_FILTRO, dias, UMBRAL_CAIDA_INDEPENDIENTE)
        etiqueta = "sin respaldo (actual)" if dias >= 999 else f"{dias} dias"
        print(f"  {etiqueta}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
              f"{n} trades, {gan} ganadoras, dd {dd:.2f}%")
        if mejor is None or cap > mejor[1]:
            mejor = (dias, cap)
    print(f"  -> mejor: {mejor[0]} dias ({mejor[1]:.2f}€)")
    return mejor[0]


def confirmar_y_multi_anio(dias_elegido):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con dias_sin_senal={dias_elegido} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                     UMBRAL_CAIDA_FILTRO, 999, UMBRAL_CAIDA_INDEPENDIENTE)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                    UMBRAL_CAIDA_FILTRO, dias_elegido, UMBRAL_CAIDA_INDEPENDIENTE)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"con respaldo {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append(gana)
    print(f"\nResultado: gana en {sum(resultados)} de {len(resultados)} combinaciones")


if __name__ == "__main__":
    dias = ajuste_eth_2024()
    confirmar_y_multi_anio(dias)
