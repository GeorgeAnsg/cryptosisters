"""
19-sept-2026: primera mirada a la particion de VALIDACION (2025) para el
sistema completo -- motores (doble suelo/techo) + entrada en vivo + salidas
(stop/take-profit + racha rota) + cambio de candidato + riesgo global. Todo
esto se calibro y valido SOLO con datos de Desarrollo (2017-2024, ver
`laboratorio/README.md` y `laboratorio/datos_lab.py`) -- 2025 no se habia
mirado nunca antes de este script, es la primera prueba genuinamente fuera
de muestra.

Mismo codigo que `prueba_multi_anio_riesgo_global.py` (no se reimplementa
nada, solo se restringe el año y se pide el acceso explicito que exige
`cargar_ohlcv_lab` para la particion de Validacion -- queda registrado
automaticamente en `registro/accesos_validacion_reserva.jsonl`).
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año
from laboratorio.patrones.prueba_multi_anio_riesgo_global import _simular_con_switch_y_riesgo_global
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from cartera.riesgo_global import multiplicador_por_volatilidad
from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import CAPITAL_INICIAL, N_LEN, M_DIAS
from motores.volatilidad import atr_absoluto

AÑO = 2025
MOTIVO = ("Probar el sistema completo (motores+switch+riesgo_global) en 2025, "
          "primera vez que se mira la particion de Validacion, pedido explicito del usuario 19-sept-2026")


def main():
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_2025_validacion",
                               acceso_validacion=True, motivo=MOTIVO)
        atr = atr_absoluto(df)
        mult_riesgo = multiplicador_por_volatilidad(df).to_numpy()
        n = len(df)
        puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
        puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
        racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
        racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")

        cand = candidatos_por_año(df, AÑO)
        cap_sw, n_sw, gan_sw, dd_sw, _ = _simular_con_switch_y_riesgo_global(
            df, cand, atr, mult_riesgo, racha_rota_techo, racha_rota_suelo, umbral_switch=999)
        cap_rg, n_rg, gan_rg, dd_rg, mult_medio = _simular_con_switch_y_riesgo_global(
            df, cand, atr, mult_riesgo, racha_rota_techo, racha_rota_suelo, umbral_switch=0.0)

        idxs = [i for i, f in enumerate(df["open_time"]) if f.year == AÑO]
        precio_ini, precio_fin = df["close"].iloc[idxs[0]], df["close"].iloc[idxs[-1]]
        retorno_hold = (precio_fin / precio_ini - 1) * 100

        print(f"\n=== {moneda} -- 2025 (buy&hold {retorno_hold:+.1f}%, {len(cand)} candidatos) ===")
        print(f"  sin cambio de candidato:      {cap_sw:.2f}€ ({(cap_sw/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
              f"{n_sw} trades, {gan_sw} ganadoras, dd {dd_sw:.2f}%")
        print(f"  con cambio + riesgo global:   {cap_rg:.2f}€ ({(cap_rg/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
              f"{n_rg} trades, {gan_rg} ganadoras, dd {dd_rg:.2f}%, mult.riesgo medio={mult_medio:.2f}")


if __name__ == "__main__":
    main()
