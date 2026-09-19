"""
15-sept-2026: idea del usuario tras revisar el trade largo del 02-abr-2024
(entra a 3278.96, sube a 3694.61 el 08-abr -- +12.7% -- y racha rota no
reacciona porque el "techo" del 08-abr sigue formando parte de la racha
ASCENDENTE, no la rompe; termina perdiendo -5.38% el 03-may). El usuario
propuso: si la operacion ya va ganando y aparece un candidato de patron
CONTRARIO (un techo, estando largo), cerrar ahi aunque no rompa ninguna
racha -- exigiendo menos confianza en el candidato que si la operacion
fuera plana o perdiendo, porque ya hay beneficio que proteger.

Este mecanismo YA EXISTE como pieza generica en `salidas/stop_objetivo.py`
(`prob_contraria` + `umbral_contraria` + `umbral_contraria_en_ganancia`,
anadido el 14-sept-2026 por la misma idea del usuario) pero nunca se
conecto a la cuenta de "cambio de candidato" que se ha estado usando en
las pruebas de esta sesion -- solo se usaba `senal_externa` (racha rota).
Aqui se conecta y se barre el umbral en ganancia (no un numero fijo a
ojo), manteniendo racha rota como esta y el umbral normal (fuera de
ganancia) desactivado (1.1, nunca se cumple) para aislar el efecto de
"proteger cuando ya se gana" sin cambiar nada del comportamiento fuera de
esa situacion. Ajuste SOLO en ETH 2024, confirmacion sin tocar nada en
BTC 2024, y despues los 4 años (2021-2024) si el ajuste supera la
confirmacion.
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
UMBRAL_CONTRARIA_NORMAL = 1.1  # nunca se cumple -- fuera de ganancia, comportamiento actual sin cambios
UMBRAL_EN_GANANCIA_GRID = [1.1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]  # 1.1 = desactivado (baseline)


def _series_prob_contraria(df):
    """prob_techo_dia[i] = probabilidad del candidato de techo confirmado ese dia (0 si no hay).
    prob_suelo_dia[i] = lo mismo para suelo. Usados como `prob_contraria` segun direccion:
    largo -> vigila techos, corto -> vigila suelos."""
    n = len(df)
    close = df["close"].to_numpy()
    prob_techo_dia = np.zeros(n)
    prob_suelo_dia = np.zeros(n)
    for idx in maximos_aparentes(close):
        r = en_vivo_techo(df, idx, dia_transcurrido=0)
        if r is not None:
            prob_techo_dia[idx] = r.probabilidad_total_si_confirma
    for idx in minimos_aparentes(close):
        r = en_vivo_suelo(df, idx, dia_transcurrido=0)
        if r is not None:
            prob_suelo_dia[idx] = r.probabilidad_total_si_confirma
    return prob_techo_dia, prob_suelo_dia


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, prob_techo_dia, prob_suelo_dia,
             umbral_switch, umbral_en_ganancia):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        prob_contraria = prob_techo_dia if direccion == "largo" else prob_suelo_dia
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal_externa=senal,
                           prob_contraria=prob_contraria, umbral_contraria=UMBRAL_CONTRARIA_NORMAL,
                           umbral_contraria_en_ganancia=umbral_en_ganancia)
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


def _cargar(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_toma_beneficio_contraria")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    prob_techo_dia, prob_suelo_dia = _series_prob_contraria(df)
    return df, atr, racha_rota_techo, racha_rota_suelo, prob_techo_dia, prob_suelo_dia


def ajuste_eth_2024():
    print("=== Ajuste del umbral 'en ganancia' -- SOLO ETH 2024 ===")
    df, atr, rt, rs, pt, ps = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    mejor = None
    for umbral in UMBRAL_EN_GANANCIA_GRID:
        cap, n, gan, dd = _simular(df, cand, atr, rt, rs, pt, ps, UMBRAL_SWITCH, umbral)
        etiqueta = "desactivado (baseline)" if umbral >= 1.0 else f"{umbral:.1f}"
        print(f"  umbral_en_ganancia={etiqueta}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
              f"{n} trades, {gan} ganadoras, dd {dd:.2f}%")
        if mejor is None or cap > mejor[1]:
            mejor = (umbral, cap)
    print(f"  -> mejor umbral en ETH 2024: {mejor[0]:.1f} ({mejor[1]:.2f}€)")
    return mejor[0]


def confirmar_btc_2024(umbral_elegido):
    print(f"\n=== Confirmacion en BTC 2024 con umbral={umbral_elegido:.1f} (congelado) ===")
    df, atr, rt, rs, pt, ps = _cargar("BTCUSDT")
    cand = candidatos_por_año(df, 2024)
    cap_base, n_b, gan_b, dd_b = _simular(df, cand, atr, rt, rs, pt, ps, UMBRAL_SWITCH, 1.1)
    cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, rt, rs, pt, ps, UMBRAL_SWITCH, umbral_elegido)
    print(f"  sin toma de beneficio: {cap_base:.2f}€ ({n_b} trades, {gan_b} ganadoras, dd {dd_b:.2f}%)")
    print(f"  con toma de beneficio: {cap_nuevo:.2f}€ ({n_n} trades, {gan_n} ganadoras, dd {dd_n:.2f}%)")
    return cap_nuevo > cap_base


def multi_anio(umbral_elegido):
    print(f"\n=== Validacion multi-anio con umbral={umbral_elegido:.1f} (congelado, sin retocar) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pt, ps = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, rt, rs, pt, ps, UMBRAL_SWITCH, 1.1)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, rt, rs, pt, ps, UMBRAL_SWITCH, umbral_elegido)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"con toma beneficio {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) "
                  f"-- {'GANA' if gana else 'pierde'}")
            resultados.append({"moneda": moneda, "año": año, "capital_actual": round(cap_actual, 2),
                                "capital_nuevo": round(cap_nuevo, 2), "gana": gana})
    n_gana = sum(1 for r in resultados if r["gana"])
    print(f"\nResultado: gana en {n_gana} de {len(resultados)} combinaciones")
    return resultados


if __name__ == "__main__":
    umbral = ajuste_eth_2024()
    if umbral < 1.0:
        ok = confirmar_btc_2024(umbral)
        print(f"\n¿Confirma en BTC 2024 sin retocar? {'SI' if ok else 'NO'}")
        multi_anio(umbral)
    else:
        print("\nEl mejor umbral encontrado es 'desactivado' -- la idea no aporta en ETH 2024, no se prueba mas.")
