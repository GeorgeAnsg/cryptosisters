"""
Barrido combinado #2 sobre el grid adaptativo -- respuesta directa a "sigamos
buscando filtros o combinarlo con otro motor". Cruza de verdad varias
condiciones a la vez (no una por una):

  for cada combinación de {filtro_bear, espaciado_dinamico, interruptor_tendencia}
    for cada opción de refuerzo por Doble suelo (activado / desactivado)
      for cada opción de filtro de contexto M1 (activado / desactivado)
        si ... entonces se arma la máscara de bloqueo correspondiente

Dos ideas nuevas que no se habían probado juntas hasta ahora:

1. Refuerzo por Doble suelo (`senal_refuerzo`): cuando el grid compra un
   nivel cerca (±6 velas de 4h) de una señal de Doble suelo confirmada, se
   le da más margen para correr (mult_espaciado_reforzado) en vez de vender
   en el primer escalón -- la idea original del usuario ("si ha hecho doble
   suelo, que la compra sea más larga").

2. Filtro de contexto M1 (`mascara_bloqueo`): M1 (momentum de 50 días en
   BTC diario) ya se confirmó como filtro válido para Doble suelo -- aquí
   se prueba si también sirve para el grid: bloquear NUEVAS compras del
   grid cuando el precio está lejos (por debajo) de sus máximos diarios
   recientes, es decir, cuando no hay ningún contexto alcista de fondo que
   respalde "comprar la caída". La lógica: en un grid puro da igual el
   contexto porque se apuesta a la oscilación, pero en tendencia bajista de
   verdad esa caída no rebota -- ya lo cubre `filtro_bear`, así que aquí se
   prueba un filtro MÁS permisivo y MÁS temprano (basado en momentum diario,
   no en la MA200 de 4h) para ver si actúa antes que filtro_bear.

Métrica: capital final con `evaluar_capital` (peso decreciente por nivel),
caída máxima, nº de operaciones. Barrido sobre datos completos 2019-2026 en
4h de BTC.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

import pandas as pd

from datos.cargar import cargar_ohlcv
from laboratorio import grid_adaptativo as g
from laboratorio import doble_suelo
from laboratorio import momentum_atr


def construir_senal_refuerzo(df4h: pd.DataFrame) -> "pd.Series[bool]":
    ds = doble_suelo.calcular_indicadores(df4h)
    ds = doble_suelo.calcular_senales(ds)
    return ds["entra_largo"].fillna(False)


def construir_mascara_m1(df4h: pd.DataFrame, df1d: pd.DataFrame, umbral: float = 0.90) -> "pd.Series[bool]":
    """True quiere decir 'bloquear compras nuevas del grid' -- se activa
    cuando el cierre diario está por debajo de `umbral` veces su máximo de
    50 días (fuera de contexto alcista de fondo). Fusión causal (backward)
    del dato diario sobre las velas de 4h, igual que se hizo con funding."""
    m1 = momentum_atr.calcular_indicadores(df1d, n_entrada=50)
    m1["fecha"] = df1d["open_time"]
    fuera_de_contexto = (m1["close"] < m1["max_n"] * umbral).fillna(True)
    m1_diario = pd.DataFrame({"open_time": m1["fecha"], "bloquear_m1": fuera_de_contexto})

    fusion = pd.merge_asof(
        df4h[["open_time"]].sort_values("open_time"),
        m1_diario.sort_values("open_time"),
        on="open_time",
        direction="backward",
    )
    return fusion["bloquear_m1"].fillna(True).to_numpy()


def main():
    df4h = cargar_ohlcv("BTCUSDT", "4h")
    df1d = cargar_ohlcv("BTCUSDT", "1d")

    senal_refuerzo_arr = construir_senal_refuerzo(df4h).to_numpy()
    mascara_m1_arr = construir_mascara_m1(df4h, df1d)

    print(f"Velas 4h: {len(df4h)} | señales Doble suelo: {senal_refuerzo_arr.sum()} | "
          f"velas bloqueadas por M1: {mascara_m1_arr.sum()} ({mascara_m1_arr.mean()*100:.1f}%)")

    n_niveles = 3
    base_kwargs = dict(
        n_niveles=n_niveles, k_atr_espaciado=0.5, velas_recentrado=180,
        stop_bajo_rejilla=2.0,
    )

    filas = []
    for filtro_bear in (False, True):
        for espaciado_dinamico in (False, True):
            for interruptor_tendencia in (False, True):
                # interruptor_tendencia solo tiene sentido si hay tendencia
                # detectada -- lo dejamos correr igual con espaciado_dinamico
                # en False para ver si aporta algo por sí solo también.
                for usar_refuerzo in (False, True):
                    for usar_m1 in (False, True):
                        kwargs = dict(base_kwargs)
                        kwargs["filtro_bear"] = filtro_bear
                        kwargs["espaciado_dinamico"] = espaciado_dinamico
                        kwargs["interruptor_tendencia"] = interruptor_tendencia
                        if espaciado_dinamico:
                            kwargs["k_atr_espaciado_tendencia"] = 1.5
                        if usar_refuerzo:
                            kwargs["senal_refuerzo"] = senal_refuerzo_arr
                            kwargs["ventana_refuerzo"] = 6
                            kwargs["mult_espaciado_reforzado"] = 3.0
                        if usar_m1:
                            kwargs["mascara_bloqueo"] = mascara_m1_arr

                        res = g.simular(df4h, **kwargs)
                        if not res.trades:
                            continue
                        capital, caida = g.evaluar_capital(res, n_niveles)
                        calmar = (capital - 100) / abs(caida) if caida < 0 else float("inf")
                        filas.append({
                            "bear": filtro_bear, "din": espaciado_dinamico, "trend": interruptor_tendencia,
                            "refuerzo": usar_refuerzo, "m1": usar_m1,
                            "capital_final": round(capital, 1), "caida_max_pct": round(caida, 1),
                            "n_trades": len(res.trades), "calmar": round(calmar, 2),
                        })

    tabla = pd.DataFrame(filas).sort_values("capital_final", ascending=False)
    pd.set_option("display.width", 160)
    pd.set_option("display.max_rows", 100)
    print()
    print(tabla.to_string(index=False))

    tabla.to_csv("laboratorio/resultados_grid_combinaciones2.csv", index=False)


if __name__ == "__main__":
    main()
