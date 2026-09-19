"""18-sept-2026: segunda pieza del mecanismo de noticias -- ver memoria
persistente project_corvus4_mecanismo_noticias. Repite el cruce de
explorar_noticias_2021.py pero con la señal de ráfaga construida de forma
CONTINUA sobre varios años seguidos (en vez de año a año suelto), que era
la limitación ya detectada: con solo 1 año casi cualquier día con alguna
noticia grave sacaba un percentil artificialmente alto porque el 71% de
los días no tenían ninguna. Con varios años seguidos el percentil de cada
año compara contra el historial real de los anteriores, no contra una
ventana casi vacía.

18-sept-2026: extendido de 2021-2022 a 2021-2023 en cuanto llegó la
descarga de ETH 2023 -- solo hay que añadir el año a AÑOS y su ruta de
noticias, tal como estaba previsto desde el principio de este fichero.

ETH es la moneda de calibracion (ver feedback_validacion_cruzada_solo_eth)
-- BTC se mira aqui solo de forma descriptiva/exploratoria, y de momento
solo con 2021-2022 hasta que termine su descarga de 2023-2024."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from ejecucion.cuenta_referencia import cargar, candidatos_por_año, simular_cuenta
from laboratorio.patrones.noticias_senal_rafaga import construir_señal

AÑOS_ETH = (2021, 2022, 2023)
AÑOS_BTC = (2021, 2022)  # BTC 2023-2024 todavia en descarga
RUTA_NOTICIAS = {
    "ETHUSDT": [f"datos/crudo/noticias_gdelt/noticias_eth_{a}.json" for a in AÑOS_ETH],
    "BTCUSDT": [f"datos/crudo/noticias_gdelt/noticias_btc_{a}.json" for a in AÑOS_BTC],
}
AÑOS_POR_MONEDA = {"ETHUSDT": AÑOS_ETH, "BTCUSDT": AÑOS_BTC}


def _tabla_trades_con_señal(moneda: str, rutas_noticias: list[str]) -> None:
    años = AÑOS_POR_MONEDA[moneda]
    datos = cargar(moneda)
    df = datos["df"]
    candidatos = []
    for año in años:
        candidatos.extend(candidatos_por_año(df, año))
    candidatos.sort(key=lambda c: c[0])
    _, trades, _, _ = simular_cuenta(datos, candidatos)

    noticias = []
    for ruta in rutas_noticias:
        with open(ruta) as f:
            noticias.extend(json.load(f))

    señal = construir_señal(noticias, fecha_ini=f"{años[0]}-01-01", fecha_fin=f"{años[-1]}-12-31")

    print(f"\n=== {moneda} {años[0]}-{años[-1]}: {len(trades)} operaciones, {len(noticias)} noticias de alto impacto ===")
    print(f"{'entrada':<12}{'salida':<12}{'dir':<7}{'motivo':<16}{'pnl_eur':>10}{'percentil_max_rafaga':>22}")
    percentiles_validos = []
    for t in trades:
        fecha_entrada = df["open_time"].iloc[t["idx_entrada"]].date()
        fecha_salida = df["open_time"].iloc[t["idx_salida"]].date()
        ventana = señal.loc[str(fecha_entrada):str(fecha_salida), "percentil_causal"]
        pctl_max = ventana.max() if not ventana.empty and ventana.notna().any() else float("nan")
        if pctl_max == pctl_max:  # not NaN
            percentiles_validos.append(pctl_max)
        print(f"{str(fecha_entrada):<12}{str(fecha_salida):<12}{t['direccion']:<7}{t['motivo']:<16}"
              f"{t['pnl_eur']:>10.2f}{pctl_max:>22.1f}")

    if percentiles_validos:
        import statistics
        print(f"\n  -> {len(percentiles_validos)}/{len(trades)} con percentil válido. "
              f"media={statistics.mean(percentiles_validos):.1f} "
              f"mediana={statistics.median(percentiles_validos):.1f} "
              f"min={min(percentiles_validos):.1f} max={max(percentiles_validos):.1f}")
        cortes = [0, 50, 80, 95, 101]
        etiquetas = ["<50", "50-80", "80-95", ">=95"]
        conteo = [0, 0, 0, 0]
        for p in percentiles_validos:
            for i in range(4):
                if cortes[i] <= p < cortes[i + 1]:
                    conteo[i] += 1
                    break
        print("  distribución: " + ", ".join(f"{e}: {c}" for e, c in zip(etiquetas, conteo)))


for moneda, rutas in RUTA_NOTICIAS.items():
    _tabla_trades_con_señal(moneda, rutas)
