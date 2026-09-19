"""
Puerta de regresion, 19-sept-2026: comprueba que la logica de salida
INCREMENTAL (dia a dia) de `ejecucion/quantfury/bot_paper.procesar_dia`
reproduce EXACTAMENTE, para cada candidato real de ETH/BTC 2021-2024,
el mismo dia/precio/motivo de cierre que la funcion graduada
`salidas/stop_objetivo.simular_trade` -- la misma que usa
`ejecucion/cuenta_referencia.py` (el pipeline de referencia real del
proyecto).

Por que existe: el 19-sept-2026 bot_paper.py se escribio reimplementando
a mano stop/take-profit/racha-rota/venta-parcial en vez de llamar a
`salidas/stop_objetivo.py` directamente (esa funcion recorre "hacia
adelante" desde la entrada y no es segura de llamar dia a dia con un `df`
que va creciendo -- devolveria un cierre por "tiempo_maximo" falso
cualquier dia en que a?n no haya pasado nada). Reimplementar a mano tiene
sentido arquitectonicamente, pero es exactamente el tipo de sitio donde
un numero o una direccion se puede colar mal sin que nada lo note --de
hecho, la primera version de esta correccion (mismo dia) tenia la racha
rota de techo/suelo cambiada de direccion. Este fichero es la prueba de
que, pese a estar reimplementada, la version incremental COINCIDE con la
graduada, candidato a candidato.

Aisla las SEIS mecanicas de salida (stop, objetivo, venta parcial,
trailing diario, pendiente acelerada, racha rota confirmada) del cambio
de candidato (`cartera`/arbitro, que no existe en `salidas/` ni en
`ejecucion/cuenta_referencia.py`) monkey-parcheando `candidatos_en` para
que no devuelva nunca candidatos durante la comprobacion -- si no, un
cambio de candidato real en mitad de una operacion de prueba cerraria la
posicion por un motivo que `simular_trade` no modela en absoluto, y la
comparacion no significaria nada.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

import ejecucion.quantfury.bot_paper as bp
from ejecucion.cuenta_referencia import (
    CAIDA_RELATIVA_CONFIRMACION, DIAS_MAXIMO, K_ATR_STOP, R_FIJO,
    TRAILING_ACTIVACION_PCT, TRAILING_RETROCESO_PCT, UMBRAL_PENDIENTE_ATR,
    VENTA_PARCIAL_FRACCION, VENTA_PARCIAL_UMBRAL, cargar, candidatos_por_año,
)
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

AÑOS = [2021, 2022, 2023, 2024]

_MOTIVO_EQUIV = {
    "STOP_LOSS": "stop",
    "TAKE_PROFIT": "objetivo",
    "TRAILING_RETROCESO_ALTO": "trailing_retroceso_alto",
    "PENDIENTE_ACELERADA": "senal_externa",
    "SENAL_BAJISTA": "senal_confirmada",
    "SENAL_ALCISTA": "senal_confirmada",
    "TIEMPO_MAXIMO": "tiempo_maximo",
}


def _simular_incremental(df, series, idx_entrada, direccion, prob, par="BTCUSDT"):
    """Reproduce SOLO la parte de `procesar_dia` relevante (apertura +
    cierre incremental), sin pasar por `candidatos_en`/cartera -- abre la
    posicion exactamente como lo haria `procesar_dia` y la deja evolucionar
    dia a dia hasta que se cierra o se acaba `DIAS_MAXIMO`."""
    close = df["close"].to_numpy()
    atr = series["atr"]
    niveles = calcular_niveles_fijos(close[idx_entrada], atr[idx_entrada], direccion, K_ATR_STOP, R_FIJO)
    estado = {
        "capital_interno": 100.0, "capital_real_usuario": 100.0,
        "posiciones": {par: {
            "direccion": direccion, "precio_entrada": float(close[idx_entrada]), "idx_entrada": int(idx_entrada),
            "stop_loss": float(niveles.stop), "take_profit": float(niveles.objetivo),
            "unidades": 1.0, "tamano_eur": float(close[idx_entrada]),
            "probabilidad": prob, "pendiente_extremo": 0.0, "venta_hecha": False,
            "fraccion_restante": 1.0, "pico_ganancia_pct": 0.0,
        }},
    }
    fin = min(idx_entrada + DIAS_MAXIMO, len(df) - 1)
    eventos_cierre = []
    eventos_parcial = []
    for idx in range(idx_entrada + 1, fin + 1):
        eventos = bp.procesar_dia(par, df, idx, estado, enviar=False, series=series)
        for e in eventos:
            if e["evento"] == "cierra":
                eventos_cierre.append((idx, e))
            elif e["evento"] == "venta_parcial":
                eventos_parcial.append((idx, e))
        if estado["posiciones"][par] is None:
            break
    return eventos_cierre, eventos_parcial, fin


def verificar():
    fallos = []
    total = 0
    candidatos_en_original = bp.candidatos_en
    bp.candidatos_en = lambda df, idx: []  # aisla del cambio de candidato (cartera)
    try:
        for moneda in ["ETHUSDT", "BTCUSDT"]:
            datos = cargar(moneda)
            df = datos["df"]
            series = {
                "atr": datos["atr"], "mult_riesgo_serie": np.ones(len(df)),
                "racha_rota_techo": datos["racha_rota_largo"], "racha_rota_suelo": datos["racha_rota_corto"],
                "pendiente": datos["pendiente"],
                "señal_pendiente_largo": datos["señal_pendiente_largo"],
                "señal_pendiente_corto": datos["señal_pendiente_corto"],
            }
            for año in AÑOS:
                for idx, direccion, prob in candidatos_por_año(df, año):
                    if np.isnan(datos["atr"][idx]):
                        continue
                    total += 1
                    close = df["close"].to_numpy()
                    niveles = calcular_niveles_fijos(close[idx], datos["atr"][idx], direccion, K_ATR_STOP, R_FIJO)
                    racha = datos["racha_rota_largo"] if direccion == "largo" else datos["racha_rota_corto"]
                    señal_pendiente = datos["señal_pendiente_largo"] if direccion == "largo" else datos["señal_pendiente_corto"]
                    ref = simular_trade(
                        df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                        senal_externa=señal_pendiente,
                        senal_con_confirmacion=racha, serie_confirmacion=datos["pendiente"],
                        caida_relativa_confirmacion=CAIDA_RELATIVA_CONFIRMACION,
                        venta_parcial_umbral=VENTA_PARCIAL_UMBRAL, venta_parcial_fraccion=VENTA_PARCIAL_FRACCION,
                        trailing_activacion_pct=TRAILING_ACTIVACION_PCT, trailing_retroceso_pct=TRAILING_RETROCESO_PCT,
                    )
                    cierres, parciales, fin = _simular_incremental(df, series, idx, direccion, prob, par=moneda)

                    if ref is None:
                        if not cierres:
                            continue
                        fallos.append(f"{moneda} {año} idx={idx}: graduado=None pero incremental cerro {cierres}")
                        continue
                    if ref.motivo == "tiempo_maximo" and ref.idx_salida == len(df) - 1:
                        # limite del HISTORICO disponible, no de DIAS_MAXIMO real --
                        # `simular_trade` fuerza un cierre porque no hay mas velas
                        # que mirar; un bot EN VIVO nunca tiene ese problema (siempre
                        # llega el dia siguiente), asi que no es comparable aqui.
                        continue
                    if not cierres:
                        fallos.append(f"{moneda} {año} idx={idx}: graduado cerro ({ref.idx_salida},{ref.motivo}) pero incremental no cerro nunca (fin={fin})")
                        continue

                    idx_inc, ev_inc = cierres[0]
                    motivo_esperado = _MOTIVO_EQUIV.get(ev_inc["motivo"], ev_inc["motivo"])
                    ok_motivo = motivo_esperado == ref.motivo
                    ok_idx = idx_inc == ref.idx_salida
                    ok_precio = abs(float(ev_inc["precio"]) - ref.precio_salida) < 0.01
                    if not (ok_motivo and ok_idx and ok_precio):
                        fallos.append(
                            f"{moneda} {año} idx={idx} {direccion}: graduado=(dia {ref.idx_salida},{ref.precio_salida:.4f},{ref.motivo}) "
                            f"incremental=(dia {idx_inc},{float(ev_inc['precio']):.4f},{ev_inc['motivo']}->{motivo_esperado})"
                        )
                        continue

                    hubo_parcial_ref = ref.idx_venta_parcial is not None
                    hubo_parcial_inc = len(parciales) > 0
                    if hubo_parcial_ref != hubo_parcial_inc:
                        fallos.append(f"{moneda} {año} idx={idx}: venta parcial graduado={hubo_parcial_ref} incremental={hubo_parcial_inc}")
                    elif hubo_parcial_ref:
                        idx_p_inc, ev_p = parciales[0]
                        if idx_p_inc != ref.idx_venta_parcial or abs(float(ev_p["precio"]) - ref.precio_venta_parcial) > 0.01:
                            fallos.append(
                                f"{moneda} {año} idx={idx}: venta parcial graduado=(dia {ref.idx_venta_parcial},{ref.precio_venta_parcial:.4f}) "
                                f"incremental=(dia {idx_p_inc},{float(ev_p['precio']):.4f})"
                            )
    finally:
        bp.candidatos_en = candidatos_en_original

    print(f"Total candidatos comparados: {total}")
    if fallos:
        print(f"\nFALLOS ({len(fallos)}):")
        for f in fallos[:40]:
            print(f"  {f}")
        if len(fallos) > 40:
            print(f"  ... y {len(fallos) - 40} mas")
        raise SystemExit(1)
    print("Coincide exactamente en todos los candidatos -- bot_paper.procesar_dia reproduce salidas/stop_objetivo.simular_trade.")


if __name__ == "__main__":
    verificar()
