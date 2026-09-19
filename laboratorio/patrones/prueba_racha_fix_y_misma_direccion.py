"""
Dos pruebas independientes, ambas validadas multi-año (2021-2024, ETH y
BTC) desde el principio -- lección del 15-sept-2026: ajustar y confirmar
solo en 2024 esconde sobreajuste al régimen de mercado de ese año.

1. ARREGLO DE RACHA ROTA. El diagnóstico real (15-sept-2026, revisión
   visual) encontró DOS fallos opuestos en la regla actual
   (N_LEN=4, M_DIAS=5, "el nuevo candidato debe ser ESTRICTAMENTE mas
   alto/bajo que el anterior"):
   - HIPERSENSIBLE: una racha de 11 techos ascendentes en 18 dias
     (ETH, 06-feb a 20-feb-2024) se rompio por un candidato apenas -0.7%
     mas bajo -- cierre prematuro.
   - CIEGA: una caida real del -14.6% (ETH, 08-abr a 20-abr-2024) no
     disparo nada porque la racha solo llevaba 3 puntos, por debajo del
     umbral N_LEN=4 necesario para que CUALQUIER ruptura cuente.
   Un primer intento de arreglo (consenso multi-config sobre N_LEN,
   M_DIAS, tolerancia -- `prueba_racha_consenso.py`) mejoro ETH pero
   empeoro BTC en 2024 -- no paso la validacion cruzada, se descarto.
   Aqui se prueba una redefinicion distinta: eliminar el umbral minimo de
   longitud de racha (N_LEN) -- CUALQUIER ruptura cuenta desde el primer
   punto, sin esperar a acumular una racha larga -- y sustituirlo por una
   TOLERANCIA continua (cuanto puede bajar el nuevo candidato sin contar
   como ruptura), barrida en vez de fija, con consenso de varias
   tolerancias y ventanas de dias a la vez.

2. CAMBIO EN LA MISMA DIRECCION. La regla ya validada
   (`prueba_cambio_candidato_fuerte.py`) solo cambia de posicion cuando el
   candidato nuevo es de direccion CONTRARIA. Aqui se prueba si tambien
   ayuda cambiar dentro de la MISMA direccion -- un long mejor sustituyendo
   a un long peor ya abierto -- con el mismo umbral_switch=0.0 ya ganador.
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
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

AÑOS = [2021, 2022, 2023, 2024]
UMBRAL_SWITCH = 0.0

# --- 1. racha rota sin umbral de longitud, con tolerancia continua ---
M_DIAS_GRID = [3, 5, 7, 10]
TOLERANCIA_GRID = [0.0, 0.01, 0.02, 0.03, 0.05]
FRACCION_MINIMA_GRID = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def _racha_rota_sin_longitud(puntos, m_dias, tolerancia, n_total, direccion_favorable):
    """Igual que _racha_rota pero SIN n_len -- cualquier ruptura cuenta
    desde el primer punto, y la tolerancia permite un pequeño retroceso
    sin contar como ruptura."""
    rota = np.zeros(n_total, dtype=bool)
    anterior = None
    for idx, precio in puntos:
        if anterior is not None:
            dias = idx - anterior[0]
            if direccion_favorable == "creciente":
                va_a_favor = precio >= anterior[1] * (1 - tolerancia)
            else:
                va_a_favor = precio <= anterior[1] * (1 + tolerancia)
            if not (va_a_favor and dias <= m_dias):
                rota[idx] = True
        anterior = (idx, precio)
    return rota


def _racha_rota_consenso_sin_longitud(puntos, n_total, direccion_favorable, fraccion_minima):
    configs = list(itertools.product(M_DIAS_GRID, TOLERANCIA_GRID))
    votos = np.zeros(n_total, dtype=float)
    for m_dias, tolerancia in configs:
        votos += _racha_rota_sin_longitud(puntos, m_dias, tolerancia, n_total, direccion_favorable)
    return (votos / len(configs)) >= fraccion_minima


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, umbral_switch, permitir_misma_direccion=False):
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
        misma_dir_ok = permitir_misma_direccion and direccion == abierta["direccion"]
        contraria_ok = direccion != abierta["direccion"]
        if (contraria_ok or misma_dir_ok) and prob - abierta["probabilidad"] >= umbral_switch:
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
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_racha_fix_y_misma_direccion")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    return df, atr, n, puntos_techo, puntos_suelo


def parte1_racha_fix():
    print("\n" + "=" * 70)
    print("PARTE 1 -- racha rota sin umbral de longitud, con tolerancia (consenso)")
    print("=" * 70)
    datos = {m: _cargar(m) for m in ["ETHUSDT", "BTCUSDT"]}
    df_eth, atr_eth, n_eth, pt_eth, ps_eth = datos["ETHUSDT"]

    racha_actual_eth = (
        _racha_rota(pt_eth, N_LEN, M_DIAS, n_eth, direccion_favorable="creciente"),
        _racha_rota(ps_eth, N_LEN, M_DIAS, n_eth, direccion_favorable="decreciente"),
    )

    print("\n--- ajuste en ETH 2024 (barrido de fraccion_minima) ---")
    resultados = []
    for fraccion in FRACCION_MINIMA_GRID:
        rt = _racha_rota_consenso_sin_longitud(pt_eth, n_eth, "creciente", fraccion)
        rs = _racha_rota_consenso_sin_longitud(ps_eth, n_eth, "decreciente", fraccion)
        cand = candidatos_por_año(df_eth, 2024)
        cap, n_tr, gan, dd = _simular(df_eth, cand, atr_eth, rt, rs, UMBRAL_SWITCH)
        r = {"fraccion_minima": fraccion, "capital_final": round(cap, 2), "n_trades": n_tr, "ganadoras": gan}
        resultados.append(r)
        print(" ", r)
    mejor = max(resultados, key=lambda r: r["capital_final"])
    en_borde = mejor["fraccion_minima"] in (min(FRACCION_MINIMA_GRID), max(FRACCION_MINIMA_GRID))
    print(f"mejor fraccion en ETH 2024: {mejor} -- {'EN EL BORDE' if en_borde else 'dentro del rango'}")
    fraccion_ganadora = mejor["fraccion_minima"]

    print(f"\n--- confirmación multi-año (fraccion={fraccion_ganadora}, sin retocar) vs racha actual ---")
    victorias, total = 0, 0
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, n, pt, ps = datos[moneda]
        racha_actual = (
            _racha_rota(pt, N_LEN, M_DIAS, n, direccion_favorable="creciente"),
            _racha_rota(ps, N_LEN, M_DIAS, n, direccion_favorable="decreciente"),
        )
        racha_fix = (
            _racha_rota_consenso_sin_longitud(pt, n, "creciente", fraccion_ganadora),
            _racha_rota_consenso_sin_longitud(ps, n, "decreciente", fraccion_ganadora),
        )
        print(f"\n  {moneda}:")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, g_a, dd_a = _simular(df, cand, atr, *racha_actual, UMBRAL_SWITCH)
            cap_fix, n_f, g_f, dd_f = _simular(df, cand, atr, *racha_fix, UMBRAL_SWITCH)
            gana = cap_fix > cap_actual
            victorias += int(gana); total += 1
            print(f"    {año}: racha actual {cap_actual:.2f}€ ({n_a} tr) -- racha fix {cap_fix:.2f}€ ({n_f} tr) "
                  f"-- {'GANA el fix' if gana else 'pierde el fix'}")
    print(f"\nfix de racha gana en {victorias}/{total} combinaciones año x moneda")


def parte2_misma_direccion():
    print("\n" + "=" * 70)
    print("PARTE 2 -- permitir cambio en la MISMA direccion")
    print("=" * 70)
    victorias, total = 0, 0
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, n, pt, ps = _cargar(moneda)
        racha_actual = (
            _racha_rota(pt, N_LEN, M_DIAS, n, direccion_favorable="creciente"),
            _racha_rota(ps, N_LEN, M_DIAS, n, direccion_favorable="decreciente"),
        )
        print(f"\n  {moneda}:")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_solo_contraria, n_c, g_c, dd_c = _simular(df, cand, atr, *racha_actual, UMBRAL_SWITCH, permitir_misma_direccion=False)
            cap_con_misma, n_m, g_m, dd_m = _simular(df, cand, atr, *racha_actual, UMBRAL_SWITCH, permitir_misma_direccion=True)
            gana = cap_con_misma > cap_solo_contraria
            victorias += int(gana); total += 1
            print(f"    {año}: solo contraria {cap_solo_contraria:.2f}€ ({n_c} tr) -- con misma dirección {cap_con_misma:.2f}€ ({n_m} tr) "
                  f"-- {'GANA con misma dirección' if gana else 'pierde con misma dirección'}")
    print(f"\npermitir misma dirección gana en {victorias}/{total} combinaciones año x moneda")


if __name__ == "__main__":
    parte1_racha_fix()
    parte2_misma_direccion()
