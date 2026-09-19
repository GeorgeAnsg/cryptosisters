"""18-sept-2026: primera pieza de la estructura del mecanismo de noticias
-- ver memoria persistente project_corvus4_mecanismo_noticias. Usa el
unico año con datos completos en ambas monedas (2021) para montar el
pipeline entero de punta a punta: noticias crudas -> categorizar ->
señal de ráfaga -> cruzar con las operaciones reales de la cuenta de
referencia. Puramente descriptivo -- NO fija ningun umbral todavia, solo
comprueba que el cruce funciona y muestra los numeros para decidir el
siguiente paso.

ETH es la moneda de calibracion (ver feedback_validacion_cruzada_solo_eth)
-- BTC se mira aqui solo de forma descriptiva/exploratoria, no para fijar
nada. Cuando lleguen los años que faltan, este mismo script se reusa
pasando el año como parametro en vez de reescribirlo desde cero."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from ejecucion.cuenta_referencia import cargar, candidatos_por_año, simular_cuenta
from laboratorio.patrones.noticias_senal_rafaga import construir_señal

AÑO = 2021
RUTA_NOTICIAS = {
    "ETHUSDT": "datos/crudo/noticias_gdelt/noticias_eth_2021.json",
    "BTCUSDT": "datos/crudo/noticias_gdelt/noticias_btc_2021.json",
}


def _tabla_trades_con_señal(moneda: str, ruta_noticias: str) -> None:
    datos = cargar(moneda)
    df = datos["df"]
    candidatos = candidatos_por_año(df, AÑO)
    _, trades, _, _ = simular_cuenta(datos, candidatos)

    with open(ruta_noticias) as f:
        noticias = json.load(f)
    señal = construir_señal(noticias, fecha_ini=f"{AÑO}-01-01", fecha_fin=f"{AÑO}-12-31")

    print(f"\n=== {moneda} {AÑO}: {len(trades)} operaciones, {len(noticias)} noticias de alto impacto ===")
    print(f"{'entrada':<12}{'salida':<12}{'dir':<7}{'motivo':<16}{'pnl_eur':>10}{'percentil_max_rafaga':>22}")
    for t in trades:
        fecha_entrada = df["open_time"].iloc[t["idx_entrada"]].date()
        fecha_salida = df["open_time"].iloc[t["idx_salida"]].date()
        ventana = señal.loc[str(fecha_entrada):str(fecha_salida), "percentil_causal"]
        pctl_max = ventana.max() if not ventana.empty and ventana.notna().any() else float("nan")
        print(f"{str(fecha_entrada):<12}{str(fecha_salida):<12}{t['direccion']:<7}{t['motivo']:<16}"
              f"{t['pnl_eur']:>10.2f}{pctl_max:>22.1f}")


for moneda, ruta in RUTA_NOTICIAS.items():
    _tabla_trades_con_señal(moneda, ruta)
