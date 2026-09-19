"""
Validación formal del filtro régimen NEUTRO sobre pendiente_acelerada --
15-sept-2026. Cierre de la fase "afinado de la salida" como v1.

Aplica lo que faltaba, en orden:
  1. Puerta 1 (causalidad) y Puerta 5 (recursividad) sobre la señal
     `_en_neutro`, reutilizando los verificadores genéricos de tests/.
  2. Monte Carlo por permutación: barajar qué días están marcados NEUTRO
     (mismo recuento) y ver si el total real supera al de colocar el
     mismo número de días "en pausa" al azar. Esto es la pregunta que de
     verdad importa aquí -- no "hay patrón" (ya lo sabemos, es un motor
     graduado) sino "la pausa que aplica ayuda más que pausar al azar
     ese mismo número de días".
  3. Puerta 4 (DSR) sobre los retornos por operación del sistema
     filtrado, con el presupuesto de intentos real del proyecto.
  4. Sensibilidad a costes: ¿a partir de qué coste por operación
     desaparece la ventaja de régimen NEUTRO frente a BASE y frente a
     "sin filtro"?
  5. Comparación con una alternativa pedida por el usuario: doble
     techo/doble suelo como filtro de contexto, con la misma metodología
     de ajuste-solo-en-ETH y confirmación congelada en BTC/XRP.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada, UMBRAL_PENDIENTE
from laboratorio.patrones.pendiente_filtro_regimen import _en_neutro
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones import doble_techo_flexible as dtf
from laboratorio.patrones import doble_suelo_flexible as dsf
from tests.puerta1_causalidad import verificar_causalidad
from tests.puerta5_recursividad import verificar_recursividad
from tests.puerta4_dsr import evaluar as evaluar_dsr
from tests.puerta_presupuesto import verificar_presupuesto

MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}


def _candidatos_todos_los_años(df):
    """Precalcula UNA vez los candidatos por año -- evita recalcular la
    deteccion de patrones (cara) en cada una de las N permutaciones de
    Monte Carlo, que no cambian los candidatos, solo el filtro `activo`."""
    return {año: candidatos_por_año(df, año) for año in AÑOS}


def _total_y_trades(df, atr, rt, rs, pend, fechas, activo, cand_por_año):
    total, todos_trades = 0.0, []
    for año in AÑOS:
        cap, tr = simular_cuenta_filtrada(df, cand_por_año[año], atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, activo)
        total += cap
        todos_trades.extend(tr)
    return total, todos_trades


def _retorno_pct_trade(t):
    if t["direccion"] == "largo":
        return (t["precio_salida"] / t["precio_entrada"] - 1) * 100
    return (t["precio_entrada"] / t["precio_salida"] - 1) * 100


# ---------------------------------------------------------------------
print("=" * 70)
print("1) PUERTA 1 (causalidad) y PUERTA 5 (recursividad) sobre _en_neutro")
print("=" * 70)


def _fn_indicadores(df):
    return df


def _fn_senales(df):
    df = df.copy()
    df["en_neutro"] = _en_neutro(df)
    return df


df_eth, *_ = cargar("ETHUSDT")
r1 = verificar_causalidad(df_eth, _fn_indicadores, _fn_senales, ["en_neutro"], n_cortes=25, warmup_minimo=210)
print(r1.resumen())
r5 = verificar_recursividad(df_eth, _fn_indicadores, _fn_senales, ["en_neutro"], historia_disponible=400, n_puntos=25)
print(r5.resumen())

# ---------------------------------------------------------------------
print("\n" + "=" * 70)
print("2) MONTE CARLO por permutacion -- >=1 barajar dias NEUTRO al azar")
print("=" * 70)

SEMILLA = 42
N_PERM = {"ETH": 500, "BTC": 300, "XRP": 300}
resultados_mc = {}

for nombre, cargador in MONEDAS.items():
    df, atr, rt, rs, pend, cl, cc = cargador()
    fechas = df["open_time"]
    en_neu = _en_neutro(df)
    n_dias_neutro = int(en_neu.sum())
    cand_por_año = _candidatos_todos_los_años(df)
    total_real, _ = _total_y_trades(df, atr, rt, rs, pend, fechas, en_neu, cand_por_año)

    rng = np.random.default_rng(SEMILLA)
    n = len(df)
    idx_validos = np.arange(n)  # se permite marcar cualquier dia, igual que el real puede caer en cualquiera
    totales_azar = []
    for _ in range(N_PERM[nombre]):
        activo_azar = np.zeros(n, dtype=bool)
        elegidos = rng.choice(idx_validos, size=n_dias_neutro, replace=False)
        activo_azar[elegidos] = True
        total_azar, _ = _total_y_trades(df, atr, rt, rs, pend, fechas, activo_azar, cand_por_año)
        totales_azar.append(total_azar)
    totales_azar = np.array(totales_azar)
    p_valor = float(np.mean(totales_azar >= total_real))
    resultados_mc[nombre] = dict(total_real=total_real, dias_neutro=n_dias_neutro, n_dias=n,
                                  media_azar=float(totales_azar.mean()), p10=float(np.percentile(totales_azar, 10)),
                                  p90=float(np.percentile(totales_azar, 90)), p_valor=p_valor, n_perm=N_PERM[nombre])
    print(f"{nombre}: real={total_real:.2f}  media_azar={totales_azar.mean():.2f}  "
          f"[p10={np.percentile(totales_azar,10):.2f}, p90={np.percentile(totales_azar,90):.2f}]  "
          f"p-valor(azar>=real)={p_valor:.4f}  ({N_PERM[nombre]} permutaciones, {n_dias_neutro}/{n} dias)")

# ---------------------------------------------------------------------
print("\n" + "=" * 70)
print("3) PUERTA 4 (DSR) sobre retornos por operacion, sistema regimen NEUTRO")
print("=" * 70)

presupuesto = verificar_presupuesto()
n_intentos = presupuesto["n_intentos_distintos"] + 5  # + los 5 de esta sesion (ER, percentil, volumen, dominancia, regimen_neutro)
print(f"presupuesto: {presupuesto['n_intentos_distintos']} intentos ya registrados + 5 de esta sesion = {n_intentos} / {presupuesto['presupuesto_total']}")

todos_retornos = []
for nombre, cargador in MONEDAS.items():
    df, atr, rt, rs, pend, cl, cc = cargador()
    fechas = df["open_time"]
    en_neu = _en_neutro(df)
    cand_por_año = _candidatos_todos_los_años(df)
    _, trades = _total_y_trades(df, atr, rt, rs, pend, fechas, en_neu, cand_por_año)
    retornos = [_retorno_pct_trade(t) for t in trades]
    todos_retornos.extend(retornos)
    r_dsr = evaluar_dsr(np.array(retornos), n_intentos)
    print(r_dsr.resumen(nombre))

r_dsr_pool = evaluar_dsr(np.array(todos_retornos), n_intentos)
print(r_dsr_pool.resumen("POOL (3 monedas)"))

# ---------------------------------------------------------------------
print("\n" + "=" * 70)
print("4) SENSIBILIDAD A COSTES -- coste por operacion (%) hasta que desaparece la ventaja")
print("=" * 70)

COSTES_PCT = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]


def _capital_con_coste(trades, coste_pct):
    capital = 1000.0
    for t in trades:
        r = _retorno_pct_trade(t)
        peso_capital = t["pnl_eur"] / (r / 100) if r != 0 else 0.0
        # aproximacion: aplicar el coste como resta directa al pnl_eur en la
        # misma proporcion que el retorno de precio representa sobre el pnl real
        pnl_neto = t["pnl_eur"] - abs(peso_capital) * (coste_pct / 100) if peso_capital else t["pnl_eur"]
        capital += pnl_neto
    return capital


for nombre, cargador in MONEDAS.items():
    df, atr, rt, rs, pend, cl, cc = cargador()
    fechas = df["open_time"]
    en_neu = _en_neutro(df)
    sin_filtro = np.zeros(len(df), dtype=bool)
    cand_por_año = _candidatos_todos_los_años(df)
    _, trades_reg = _total_y_trades(df, atr, rt, rs, pend, fechas, en_neu, cand_por_año)
    _, trades_sin = _total_y_trades(df, atr, rt, rs, pend, fechas, sin_filtro, cand_por_año)
    print(f"\n{nombre}:")
    for c in COSTES_PCT:
        cap_reg = _capital_con_coste(trades_reg, c)
        cap_sin = _capital_con_coste(trades_sin, c)
        print(f"  coste={c:.1f}%/op: regimen={cap_reg:.2f}  sin_filtro={cap_sin:.2f}  "
              f"ventaja={'SI' if cap_reg > cap_sin else 'NO'}")

# ---------------------------------------------------------------------
print("\n" + "=" * 70)
print("5) ALTERNATIVA: doble techo/doble suelo como filtro de contexto")
print("=" * 70)

VENTANA_CONFIRMACION_DIAS = 4  # la misma que ventana_min_dias por defecto de los detectores


def _en_doble_extremo(df):
    n = len(df)
    activo = np.zeros(n, dtype=bool)
    for c in dtf.detectar(df):
        fin = min(c.idx_techo2 + VENTANA_CONFIRMACION_DIAS, n - 1)
        activo[c.idx_techo1:fin + 1] = True
    for c in dsf.detectar(df):
        fin = min(c.idx_fondo2 + VENTANA_CONFIRMACION_DIAS, n - 1)
        activo[c.idx_fondo1:fin + 1] = True
    return activo


df_eth2, atr_e, rt_e, rs_e, pend_e, cl_e, cc_e = cargar("ETHUSDT")
fechas_e = df_eth2["open_time"]
en_dext_eth = _en_doble_extremo(df_eth2)
cand_eth2 = _candidatos_todos_los_años(df_eth2)
total_dext_eth, _ = _total_y_trades(df_eth2, atr_e, rt_e, rs_e, pend_e, fechas_e, en_dext_eth, cand_eth2)
print(f"ETH: dias marcados doble-techo/suelo = {en_dext_eth.sum()}/{len(df_eth2)}  TOTAL={total_dext_eth:.2f}  "
      f"(ref: sin_filtro=10662.53, regimen_NEUTRO=10440.01)")

for nombre in ["BTC", "XRP"]:
    df, atr, rt, rs, pend, cl, cc = MONEDAS[nombre]()
    fechas = df["open_time"]
    en_dext = _en_doble_extremo(df)
    cand_por_año = _candidatos_todos_los_años(df)
    por_año = {}
    total_dext = 0.0
    for año in AÑOS:
        cap, tr = simular_cuenta_filtrada(df, cand_por_año[año], atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, en_dext)
        por_año[año] = round(cap, 2)
        total_dext += cap
    print(f"{nombre}: dias marcados = {en_dext.sum()}/{len(df)}  TOTAL={total_dext:.2f}  por_año={por_año}")

print("\nFIN", flush=True)
