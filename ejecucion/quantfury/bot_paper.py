#!/usr/bin/env python3
"""
18-sept-2026: el "bot total" para la vertiente QuantFury -- une motores +
entradas (señal en vivo) + salidas (stop/take-profit + racha rota) +
tamano + cartera (arbitro + riesgo_global + riesgo_quantfury) +
alertas_telegram en un solo ciclo de paper trading. No ejecuta NINGUNA
orden real -- QuantFury no tiene API, todo lo hace el usuario a mano; esto
solo avisa por Telegram y lleva la contabilidad en papel.

Mismo patron de "descargar velas recientes + recalcular sobre todo el
historial acumulado" que `ejecucion/paper_trading/bot_grid_papel.py`
(pensado para correr por cron, ej. una vez al dia tras el cierre de la
vela diaria) -- no se reinventa esa parte.

**El contador interno, pedido explicitamente por el usuario el
18-sept-2026:** "una cosa es lo que yo le diga que tiene [el capital REAL
que reporta cada semana, ver `cartera/riesgo_quantfury.comparar_tramo_semanal`]
y otra cosa es su contador de lo que va ganando, va perdiendo [...] se va
actualizando cuando cierra o abre una operacion". Son DOS numeros
distintos, guardados por separado en `estado_paper.json`:

  - `capital_interno`: el propio bot lo actualiza SOLO cuando cierra una
    operacion (nunca lo toca el usuario) -- es la contabilidad de papel,
    la pregunta de "¿va ganando o perdiendo el sistema de verdad?".
  - `capital_real_usuario`: el usuario lo actualiza a mano cada semana
    (via `actualizar_capital_real()`) con el balance REAL de QuantFury --
    es el que decide el tramo/poder de trading (`riesgo_quantfury`), no
    tiene por que coincidir con `capital_interno` (el paper trading no
    arriesga dinero real, el balance real depende de que el usuario siga
    o no cada aviso).

Una sola cuenta compartida entre BTC y ETH (maximo 2 huecos a la vez, ver
`cartera/README.md`) porque la liquidacion de QuantFury es de TODA la
cuenta, no por activo -- por eso `capital_interno`/`capital_real_usuario`
son un unico numero, no uno por par.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import numpy as np
import pandas as pd

from cartera.arbitro import SenalCandidata, resolver
from cartera.riesgo_global import multiplicador_por_volatilidad
from cartera.riesgo_quantfury import capar_a_poder_trading, poder_de_trading
from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    M_DIAS, MULTIPLICADOR_MAX, MULTIPLICADOR_MIN, N_LEN,
)
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from salidas.pendiente_acelerada import calcular_pendiente_atr, señal_para_direccion, UMBRAL_PENDIENTE_ATR
from salidas.racha_rota import calcular_para_direccion as racha_rota_para_direccion, CAIDA_RELATIVA_CONFIRMACION
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

# Parametros confirmados: bug corregido 19-sept-2026 (segunda vez en el
# mismo dia). La primera correccion aqui importo K_ATR_STOP=1.2/R_FIJO=4.0
# de `sistema_confirmado_switch_14sept2026.py` (14-sept) creyendo que era
# la fuente de la verdad -- PERO esa sesion es tres dias mas vieja que
# `ejecucion/cuenta_referencia.py` (17/18-sept), que es el pipeline de
# referencia real y añade DOS mecanismos de salida que la version del
# 14-sept no tenia: pendiente acelerada como señal independiente
# (`salidas/pendiente_acelerada.py`) y trailing DIARIO por retroceso
# relativo (activacion 5%/retroceso 67.5%, protege ganancias flotantes
# grandes -- exactamente el mecanismo que falta para el caso de BTC que
# motivo esta correccion). Importar SIEMPRE desde `ejecucion.cuenta_referencia`
# de aqui en adelante: es, por definicion del propio proyecto, "el
# pipeline de referencia" -- si alguna vez deja de serlo, el fichero que
# lo sustituya debera decirlo explicitamente en su cabecera, igual que
# este lo dice de `sistema_confirmado_switch_14sept2026.py`.
from ejecucion.cuenta_referencia import (
    K_ATR_STOP, R_FIJO, DIAS_MAXIMO, VENTA_PARCIAL_UMBRAL, VENTA_PARCIAL_FRACCION,
    TRAILING_ACTIVACION_PCT, TRAILING_RETROCESO_PCT,
)

from ejecucion.quantfury.alertas_telegram import (
    AlertaCompra, avisar_error, avisar_inicio, avisar_latido, avisar_recordatorio_balance,
    enviar_telegram, leer_actualizaciones, mensaje_compra, mensaje_venta,
)

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
DIR_DATA_ROOT = os.environ.get("CORVUS4_DATA_ROOT", DIR_BASE)
DIR_DATOS_VIVOS = os.path.join(DIR_DATA_ROOT, "datos_vivos")
RUTA_ESTADO = os.path.join(DIR_DATA_ROOT, "estado_paper.json")
RUTA_REGISTRO = os.path.join(DIR_DATA_ROOT, "registro_paper.csv")

CAPITAL_INICIAL = 100.0  # arranca en el tramo de 100e (ver riesgo_quantfury.TABLA_TRAMOS_QUANTFURY)
UMBRAL_SWITCH = 0.0  # mismo umbral ya validado en prueba_multi_anio.py -- no retocar aqui
PARES = ["BTCUSDT", "ETHUSDT"]  # maximo 2 huecos simultaneos, ver cartera/README.md

# RIESGO_BASE_PCT: decision de NEGOCIO del usuario (19-sept-2026), NO un
# numero recalibrado -- distinto del 0.02 que usan `laboratorio/patrones/
# prueba_cuenta_1000e_v3_racha.py` y `ejecucion/cuenta_referencia.py`,
# con el que se valido toda la logica de entradas/salidas. Subir el riesgo por
# operacion no cambia CUANDO entra/sale el bot, solo CUANTO arriesga cada
# vez -- por eso es seguro desviarse aqui sin invalidar esa validacion.
# Elegido tras comparar 3.0%/3.5%/4.0% sobre 2021-2024 (Desarrollo) + 2025
# (Validacion), ver `laboratorio/patrones/prueba_barrido_riesgo_base.py`:
# peor drawdown observado en los 5 años a 4% fue -5.7% (ETH 2024) -- muy
# lejos de zona peligrosa. Si esto se vuelve a tocar, que quede en ese
# mismo fichero de prueba, no solo en esta constante.
RIESGO_BASE_PCT = 0.04


# =============================================================================
# Estado persistido (capital_interno / capital_real_usuario / posiciones)
# =============================================================================

def _estado_por_defecto() -> dict:
    return {
        "capital_interno": CAPITAL_INICIAL,
        "capital_real_usuario": CAPITAL_INICIAL,
        "posiciones": {par: None for par in PARES},
        "fecha_ultimo_balance_real": None,
        "fecha_ultimo_recordatorio_balance": None,
        "ultimo_update_id": 0,
    }


def cargar_estado() -> dict:
    if not os.path.exists(RUTA_ESTADO):
        return _estado_por_defecto()
    with open(RUTA_ESTADO) as f:
        estado = json.load(f)
    for par in PARES:
        estado["posiciones"].setdefault(par, None)
    estado.setdefault("fecha_ultimo_balance_real", None)
    estado.setdefault("fecha_ultimo_recordatorio_balance", None)
    estado.setdefault("ultimo_update_id", 0)
    return estado


def procesar_comandos_telegram(estado: dict) -> None:
    """Comprueba mensajes nuevos de Telegram desde el ultimo ciclo -- SOLO
    entiende `/balance <numero>`, y SOLO si viene del chat autorizado
    (`TELEGRAM_CHAT_ID`, el mismo que ya usa `enviar_telegram` para
    mandar). Pedido explicito del usuario (19-sept-2026): en otro
    proyecto (`v12/main.py`) esto es un listener en tiempo real corriendo
    en su propio hilo sin parar -- aqui NO, porque `bot_paper.py` sigue
    siendo un script de cron que se lanza una vez al dia y termina (ver
    docstring del modulo); esto solo mira "¿ha llegado algo desde la
    ultima vez?" al principio del ciclo, con un `timeout=0` que no
    bloquea. Muta `estado` in-place; quien llama es responsable de
    guardarlo (igual que el resto de `procesar_dia`).

    Bug corregido 19-sept-2026: la comprobacion de autorizacion era
    `if chat_autorizado and chat_id != chat_autorizado` -- si
    `TELEGRAM_CHAT_ID` no estaba configurado (`chat_autorizado=""`), la
    condicion se saltaba entera y CUALQUIER chat de Telegram que conociera
    el token del bot podia mandar `/balance` sin autenticarse. En la
    practica es dificil que pase (sin `TELEGRAM_CHAT_ID` tampoco se manda
    ningun aviso de salida, ver `enviar_telegram`), pero es una
    configuracion a medias plausible -- ahora, sin chat autorizado
    configurado, no se procesa NINGUN comando en vez de aceptarlos todos."""
    chat_autorizado = os.environ.get("TELEGRAM_CHAT_ID", "")
    for u in leer_actualizaciones(estado.get("ultimo_update_id", 0)):
        estado["ultimo_update_id"] = u["update_id"] + 1
        msg = u.get("message", {})
        texto = (msg.get("text") or "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if not chat_autorizado or chat_id != chat_autorizado:
            continue
        if not texto.lower().startswith("/balance"):
            continue
        partes = texto.split()
        try:
            valor = float(partes[1]) if len(partes) >= 2 else None
        except ValueError:
            valor = None
        if valor is None:
            enviar_telegram("❌ Formato incorrecto. Usa: <code>/balance 105.30</code>")
            continue
        estado["capital_real_usuario"] = valor
        estado["fecha_ultimo_balance_real"] = datetime.now(timezone.utc).date().isoformat()
        enviar_telegram(f"✅ <b>Balance actualizado: {valor:,.2f} €</b>")


def guardar_estado(estado: dict):
    os.makedirs(DIR_DATA_ROOT, exist_ok=True)
    with open(RUTA_ESTADO, "w") as f:
        json.dump(estado, f, indent=2)


def actualizar_capital_real(nuevo_capital_eur: float):
    """Lo llama el usuario a mano cada semana con su balance REAL de
    QuantFury -- NO toca `capital_interno` (esos son dos contadores
    distintos, ver docstring del modulo)."""
    estado = cargar_estado()
    estado["capital_real_usuario"] = nuevo_capital_eur
    estado["fecha_ultimo_balance_real"] = datetime.now(timezone.utc).date().isoformat()
    guardar_estado(estado)
    return estado


def _registrar(fila: dict):
    os.makedirs(DIR_DATA_ROOT, exist_ok=True)
    existe = os.path.exists(RUTA_REGISTRO)
    with open(RUTA_REGISTRO, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fila.keys()))
        if not existe:
            w.writeheader()
        w.writerow(fila)


# =============================================================================
# Datos (mismo mecanismo publico de Binance que bot_grid_papel.py)
# =============================================================================

def descargar_velas(par: str, intervalo: str = "1d", limite: int = 1000) -> pd.DataFrame:
    url = f"https://api.binance.com/api/v3/klines?symbol={par}&interval={intervalo}&limit={limite}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    filas = [(d[0], float(d[1]), float(d[2]), float(d[3]), float(d[4]), float(d[5])) for d in data]
    df = pd.DataFrame(filas, columns=["open_time", "open", "high", "low", "close", "volume"])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df


def descargar_velas_diarias(par: str, limite: int = 1000) -> pd.DataFrame:
    return descargar_velas(par, "1d", limite)


def cargar_o_actualizar_historial(par: str) -> pd.DataFrame:
    ruta = os.path.join(DIR_DATOS_VIVOS, f"{par}_1d.csv")
    nuevas = descargar_velas_diarias(par)
    if os.path.exists(ruta):
        historial = pd.read_csv(ruta)
        historial["open_time"] = pd.to_datetime(historial["open_time"], utc=True)
        # `nuevas` va DESPUES de `historial` y `keep="last"` -- bug corregido
        # 19-sept-2026: al reves (el orden por defecto, keep="first") se
        # quedaba con la fila VIEJA en cualquier fecha solapada. Eso congela
        # para siempre una vela que se llegara a capturar incompleta (ej. el
        # bot corriendo antes de que cierre la vela diaria en Binance) --
        # el dia siguiente Binance ya tiene el dato bueno, pero se descartaba
        # a favor del malo. Confirmado con una prueba antes de corregir.
        combinado = pd.concat([historial, nuevas]).drop_duplicates(subset="open_time", keep="last")
    else:
        combinado = nuevas
    combinado = combinado.sort_values("open_time").reset_index(drop=True)
    os.makedirs(DIR_DATOS_VIVOS, exist_ok=True)
    combinado.to_csv(ruta, index=False)
    return combinado


# =============================================================================
# Señal del dia (mismo motor+entrada+racha_rota que prueba_multi_anio.py,
# restringido al ULTIMO dia del historial -- eso es lo que lo hace "en
# vivo" en vez de un backtest)
# =============================================================================

def candidatos_en(df: pd.DataFrame, idx: int) -> list[SenalCandidata]:
    """Candidatos vivos en el dia `idx` (no necesariamente el ultimo del
    historial) -- separado de idx=len(df)-1 para que
    `laboratorio/patrones/generar_reporte_2025.py` pueda recorrer un año
    entero dia a dia con EXACTAMENTE esta misma logica, sin duplicarla."""
    out = []
    for c in techo_motor.detectar(df):
        if c.idx_techo2 != idx:
            continue
        r = en_vivo_techo(df, c.idx_techo2, dia_transcurrido=0)
        if r is not None:
            out.append(SenalCandidata(motor="doble_techo", direccion="corto", pronostico=r.probabilidad_total_si_confirma))
    for c in suelo_motor.detectar(df):
        if c.idx_fondo2 != idx:
            continue
        r = en_vivo_suelo(df, c.idx_fondo2, dia_transcurrido=0)
        if r is not None:
            out.append(SenalCandidata(motor="doble_suelo", direccion="largo", pronostico=r.probabilidad_total_si_confirma))
    return out


def candidatos_hoy(df: pd.DataFrame) -> list[SenalCandidata]:
    return candidatos_en(df, len(df) - 1)


def _mejor_candidato(candidatos: list[SenalCandidata]) -> SenalCandidata | None:
    resueltas = resolver(candidatos)
    return max(resueltas, key=lambda c: c.pronostico) if resueltas else None


def _motivo_racha_rota(direccion_posicion: str) -> str:
    # una posicion LARGA se cierra por señal BAJISTA (rompe racha del
    # suelo); una CORTA se cierra por señal ALCISTA (rompe racha del
    # techo) -- mismo mapeo que `_MOTIVOS_CIERRE` en alertas_telegram.py
    return "SENAL_BAJISTA" if direccion_posicion == "largo" else "SENAL_ALCISTA"


# =============================================================================
# Un dia, para un par (la pieza que se reutiliza tal cual dia a dia en el
# ciclo en vivo Y en el informe historico de `generar_reporte_2025.py`)
# =============================================================================

def precalcular_series(df: pd.DataFrame) -> dict:
    """`atr`, `mult_riesgo`, racha rota y pendiente acelerada NO dependen
    del dia -- son funcion de todo `df` de una vez. Se calculan aqui UNA
    vez y se pasan a `procesar_dia` en vez de recalcularse en cada llamada
    (365 veces por año en `generar_reporte_2025.py` seria impracticamente
    lento). 19-sept-2026: usa las funciones GRADUADAS de `salidas/`
    (`racha_rota.calcular_para_direccion`, `pendiente_acelerada.
    calcular_pendiente_atr`), las mismas que usa `ejecucion/cuenta_referencia.py`
    -- no una copia de laboratorio."""
    atr = atr_absoluto(df)
    mult_riesgo_serie = multiplicador_por_volatilidad(df).to_numpy()
    pendiente = calcular_pendiente_atr(df, atr)
    return {
        "atr": atr,
        "mult_riesgo_serie": mult_riesgo_serie,
        "racha_rota_techo": racha_rota_para_direccion(df, "largo"),
        "racha_rota_suelo": racha_rota_para_direccion(df, "corto"),
        "pendiente": pendiente,
        "señal_pendiente_largo": señal_para_direccion(pendiente, "largo", UMBRAL_PENDIENTE_ATR),
        "señal_pendiente_corto": señal_para_direccion(pendiente, "corto", UMBRAL_PENDIENTE_ATR),
    }


def procesar_dia(par: str, df: pd.DataFrame, idx: int, estado: dict, enviar: bool = True,
                  series: dict | None = None) -> list[dict]:
    """Aplica la logica de un ciclo a UN par en el dia `idx`, mutando
    `estado` in-place (abre/cierra posiciones, actualiza capital_interno) y
    devolviendo los eventos ocurridos (para registrar en CSV y, si
    `enviar=False`, para que el informe muestre el mensaje sin mandarlo de
    verdad por Telegram). `series` son las precalculadas por
    `precalcular_series(df)` -- si no se pasan (uso normal del ciclo en
    vivo, una sola llamada), se calculan aqui como antes."""
    close = df["close"].to_numpy()
    eventos = []
    if series is None:
        series = precalcular_series(df)
    atr = series["atr"]
    if np.isnan(atr[idx]):
        return eventos
    mult_riesgo_serie = series["mult_riesgo_serie"]
    mult_riesgo = 1.0 if np.isnan(mult_riesgo_serie[idx]) else float(mult_riesgo_serie[idx])
    racha_rota_techo = series["racha_rota_techo"]
    racha_rota_suelo = series["racha_rota_suelo"]
    pendiente = series["pendiente"]
    señal_pendiente_largo = series["señal_pendiente_largo"]
    señal_pendiente_corto = series["señal_pendiente_corto"]

    candidatos = candidatos_en(df, idx)
    mejor = _mejor_candidato(candidatos)
    pos = estado["posiciones"][par]
    fecha = df["open_time"].iloc[idx]

    # -- 1) posicion abierta: venta parcial, stop/take-profit y señales de salida --
    if pos is not None:
        hoy = df.iloc[idx]
        signo = 1 if pos["direccion"] == "largo" else -1

        # 1a) venta parcial confirmada 14-sept-2026: al +20% de ganancia
        # favorable se realiza el 50% de la posicion -- esto es lo que
        # evita que una operacion que llego a ganar mucho (ej. +12% en el
        # caso de BTC que motivo esta correccion, 19-sept-2026) devuelva
        # TODA la ganancia si luego el precio da la vuelta antes de que
        # racha rota confirme una salida.
        if not pos["venta_hecha"]:
            ganancia_pct = (hoy["high"] - pos["precio_entrada"]) / pos["precio_entrada"] if pos["direccion"] == "largo" \
                else (pos["precio_entrada"] - hoy["low"]) / pos["precio_entrada"]
            if ganancia_pct >= VENTA_PARCIAL_UMBRAL:
                precio_venta_parcial = pos["precio_entrada"] * (1 + VENTA_PARCIAL_UMBRAL) if pos["direccion"] == "largo" \
                    else pos["precio_entrada"] * (1 - VENTA_PARCIAL_UMBRAL)
                pnl_parcial_eur = VENTA_PARCIAL_FRACCION * pos["unidades"] * signo * (precio_venta_parcial - pos["precio_entrada"])
                estado["capital_interno"] += pnl_parcial_eur
                pos["venta_hecha"] = True
                pos["fraccion_restante"] = 1.0 - VENTA_PARCIAL_FRACCION
                pnl_pct_parcial = pnl_parcial_eur / (pos["tamano_eur"] * VENTA_PARCIAL_FRACCION) * 100 if pos["tamano_eur"] else 0.0
                texto = mensaje_venta(par, pos["direccion"], precio_venta_parcial, pnl_parcial_eur, pnl_pct_parcial,
                                       "VENTA_PARCIAL", estado["capital_interno"])
                if enviar:
                    enviar_telegram(texto)
                evento_parcial = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(), "fecha": fecha, "par": par,
                    "evento": "venta_parcial", "direccion": pos["direccion"], "precio_entrada": pos["precio_entrada"],
                    "precio": precio_venta_parcial, "pnl_eur": round(pnl_parcial_eur, 2), "motivo": "VENTA_PARCIAL",
                    "capital_interno_tras": round(estado["capital_interno"], 2), "texto": texto,
                }
                eventos.append(evento_parcial)
                if enviar:
                    _registrar({k: evento_parcial[k] for k in (
                        "timestamp_utc", "par", "evento", "direccion", "precio", "pnl_eur", "motivo", "capital_interno_tras")})

        # 1b) trailing DIARIO por retroceso relativo (confirmado
        # 18-sept-2026 en `ejecucion/cuenta_referencia.py`, activacion=5%/
        # retroceso=67.5%): protege ganancias flotantes GRANDES que ninguno
        # de los demas mecanismos cubre -- se comprueba ANTES del stop/take
        # profit, igual que en `salidas/stop_objetivo.simular_trade`. Esto
        # faltaba por completo en la primera correccion de hoy (19-sept) y
        # es, en concreto, el mecanismo pensado para el caso de BTC que
        # motivo la correccion (una operacion que llega a ganar mucho y
        # devuelve toda la ganancia sin que nada la proteja).
        precio_cierre, motivo = None, None
        if pos["direccion"] == "largo":
            ganancia_pico_pct = (hoy["high"] - pos["precio_entrada"]) / pos["precio_entrada"]
            ganancia_actual_pct = (hoy["close"] - pos["precio_entrada"]) / pos["precio_entrada"]
        else:
            ganancia_pico_pct = (pos["precio_entrada"] - hoy["low"]) / pos["precio_entrada"]
            ganancia_actual_pct = (pos["precio_entrada"] - hoy["close"]) / pos["precio_entrada"]
        pos["pico_ganancia_pct"] = max(pos["pico_ganancia_pct"], ganancia_pico_pct)
        if TRAILING_RETROCESO_PCT < 999 and pos["pico_ganancia_pct"] >= TRAILING_ACTIVACION_PCT:
            listón_trailing = pos["pico_ganancia_pct"] * (1 - TRAILING_RETROCESO_PCT)
            if ganancia_actual_pct <= listón_trailing:
                precio_cierre, motivo = float(hoy["close"]), "TRAILING_RETROCESO_ALTO"

        # 1c) stop-loss / take-profit fijos
        if precio_cierre is None:
            if pos["direccion"] == "largo":
                if hoy["low"] <= pos["stop_loss"]:
                    precio_cierre, motivo = pos["stop_loss"], "STOP_LOSS"
                elif hoy["high"] >= pos["take_profit"]:
                    precio_cierre, motivo = pos["take_profit"], "TAKE_PROFIT"
            else:
                if hoy["high"] >= pos["stop_loss"]:
                    precio_cierre, motivo = pos["stop_loss"], "STOP_LOSS"
                elif hoy["low"] <= pos["take_profit"]:
                    precio_cierre, motivo = pos["take_profit"], "TAKE_PROFIT"

        # 1d) pendiente acelerada como señal INDEPENDIENTE (confirmado
        # 15-sept-2026, `salidas/pendiente_acelerada.py`): cierra el MISMO
        # dia, sin esperar confirmacion -- cubre el hueco de racha rota
        # cuando no hay ningun pico/valle de patron confirmado cerca. Esto
        # tambien faltaba por completo en la primera correccion de hoy.
        if precio_cierre is None:
            señal_pendiente = señal_pendiente_largo if pos["direccion"] == "largo" else señal_pendiente_corto
            if señal_pendiente[idx]:
                precio_cierre, motivo = close[idx], "PENDIENTE_ACELERADA"

        # 1e) racha rota filtrada por caida relativa de pendiente (30%,
        # confirmado 14-sept-2026): ya NO corta al instante en cuanto el
        # detector de patron confirma una señal contraria -- solo cuando la
        # pendiente ATR-normalizada ha caido ese 30% desde el maximo propio
        # de ESTA operacion. `pendiente_extremo` se sigue actualizando dia a
        # dia aunque no haya señal, igual que en `salidas/stop_objetivo.
        # simular_trade`. Bug corregido en esta misma pasada (19-sept-2026):
        # la version anterior usaba `racha_rota_suelo` para cerrar un LARGO
        # y `racha_rota_techo` para un CORTO -- al reves. Un largo se
        # protege con la racha de TECHOS (maximos cada vez mas altos
        # rompiendose = señal bajista); un corto, con la racha de SUELOS
        # (minimos cada vez mas bajos rompiendose = señal alcista) -- misma
        # convencion que `ejecucion/cuenta_referencia.py`
        # (`racha_rota_largo`=techo, `racha_rota_corto`=suelo) y que
        # `sistema_confirmado_switch_14sept2026.py._abrir`.
        if precio_cierre is None:
            p = pendiente[idx]
            señal = racha_rota_techo[idx] if pos["direccion"] == "largo" else racha_rota_suelo[idx]
            if señal:
                if np.isnan(p):
                    precio_cierre, motivo = close[idx], _motivo_racha_rota(pos["direccion"])
                else:
                    if pos["direccion"] == "largo":
                        pos["pendiente_extremo"] = max(pos["pendiente_extremo"], p)
                        listón = pos["pendiente_extremo"] * (1 - CAIDA_RELATIVA_CONFIRMACION)
                        honra_corte = pos["pendiente_extremo"] <= 0 or p <= listón
                    else:
                        pos["pendiente_extremo"] = min(pos["pendiente_extremo"], p)
                        listón = pos["pendiente_extremo"] * (1 - CAIDA_RELATIVA_CONFIRMACION)
                        honra_corte = pos["pendiente_extremo"] >= 0 or p >= listón
                    if honra_corte:
                        precio_cierre, motivo = close[idx], _motivo_racha_rota(pos["direccion"])
            elif not np.isnan(p):
                if pos["direccion"] == "largo":
                    pos["pendiente_extremo"] = max(pos["pendiente_extremo"], p)
                else:
                    pos["pendiente_extremo"] = min(pos["pendiente_extremo"], p)

        # 1f) salida por tiempo (mecanica BASE de `salidas/stop_objetivo.py`,
        # anterior incluso a las confirmaciones del 14/15/18-sept): si en
        # DIAS_MAXIMO dias ninguna de las cinco anteriores ha cerrado la
        # operacion, se cierra al precio de ese dia -- faltaba tambien en
        # la primera correccion de hoy (`DIAS_MAXIMO` se importaba pero no
        # se usaba en ningun sitio).
        if precio_cierre is None and (idx - pos["idx_entrada"]) >= DIAS_MAXIMO:
            precio_cierre, motivo = close[idx], "TIEMPO_MAXIMO"

        # cambio de candidato: la misma regla ya validada en
        # prueba_multi_anio.py -- una señal contraria suficientemente
        # mas fuerte cierra y sustituye, aunque no haya saltado SL/TP
        if precio_cierre is None and mejor is not None and mejor.direccion != pos["direccion"] \
                and mejor.pronostico - pos["probabilidad"] >= UMBRAL_SWITCH:
            precio_cierre, motivo = close[idx], "CAMBIO_CANDIDATO"

        if precio_cierre is not None:
            pnl_eur = pos["fraccion_restante"] * pos["unidades"] * (precio_cierre - pos["precio_entrada"]) * signo
            pnl_pct = pnl_eur / (pos["tamano_eur"] * pos["fraccion_restante"]) * 100 if pos["tamano_eur"] and pos["fraccion_restante"] else 0.0
            estado["capital_interno"] += pnl_eur
            texto = mensaje_venta(par, pos["direccion"], precio_cierre, pnl_eur, pnl_pct,
                                   motivo, estado["capital_interno"])
            if enviar:
                enviar_telegram(texto)
            evento = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(), "fecha": fecha, "par": par,
                "evento": "cierra", "direccion": pos["direccion"], "precio_entrada": pos["precio_entrada"],
                "precio": precio_cierre, "pnl_eur": round(pnl_eur, 2), "motivo": motivo,
                "capital_interno_tras": round(estado["capital_interno"], 2), "texto": texto,
            }
            eventos.append(evento)
            if enviar:
                _registrar({k: evento[k] for k in (
                    "timestamp_utc", "par", "evento", "direccion", "precio", "pnl_eur", "motivo", "capital_interno_tras")})
            estado["posiciones"][par] = None
            pos = None

    # -- 2) sin posicion abierta: entrar si hay candidato tras el arbitro --
    if pos is None and mejor is not None:
        direccion = mejor.direccion
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        tam = calcular_tamano(estado["capital_interno"], niveles.riesgo, mejor.pronostico,
                               RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        unidades = tam.unidades * mult_riesgo
        tam_qf = capar_a_poder_trading(unidades, close[idx], tam.riesgo_dinero * mult_riesgo,
                                        estado["capital_real_usuario"])
        poder_actual, _ = poder_de_trading(estado["capital_real_usuario"])

        alerta = AlertaCompra(
            par=par, direccion=direccion, precio_entrada=close[idx],
            stop_loss=niveles.stop, take_profit=niveles.objetivo,
            tamano_eur=tam_qf.notional, poder_trading_actual=poder_actual,
        )
        texto = mensaje_compra(alerta)
        if enviar:
            enviar_telegram(texto)
        estado["posiciones"][par] = {
            "direccion": direccion, "precio_entrada": float(close[idx]), "idx_entrada": int(idx),
            "stop_loss": float(niveles.stop), "take_profit": float(niveles.objetivo),
            "unidades": float(tam_qf.unidades), "tamano_eur": float(tam_qf.notional),
            "probabilidad": mejor.pronostico,
            "pendiente_extremo": 0.0, "venta_hecha": False, "fraccion_restante": 1.0,
            "pico_ganancia_pct": 0.0,
        }
        evento = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(), "fecha": fecha, "par": par, "evento": "abre",
            "direccion": direccion, "precio": float(close[idx]), "pnl_eur": "",
            "motivo": "" if not tam_qf.capado_por_poder_trading else "CAPADO_PODER_TRADING",
            "capital_interno_tras": round(estado["capital_interno"], 2), "texto": texto,
        }
        eventos.append(evento)
        if enviar:
            _registrar({k: evento[k] for k in (
                "timestamp_utc", "par", "evento", "direccion", "precio", "pnl_eur", "motivo", "capital_interno_tras")})

    return eventos


# =============================================================================
# Un ciclo (pensado para cron, ej. diario tras el cierre de la vela UTC)
# =============================================================================

def ejecutar_ciclo():
    """Todo el cuerpo va dentro de un try/except -- añadido 19-sept-2026
    tras una auditoria completa antes de subir esto a produccion: sin
    esto, CUALQUIER excepcion (Binance caido, error de red, un bug) antes
    de llegar a `avisar_latido()` dejaba el ciclo sin mandar NADA -- un
    fallo real quedaba indistinguible de "todo va bien, no hay señal",
    justo lo que el latido se penso para evitar. En el fallo, intenta
    igualmente guardar lo que se haya avanzado (ej. si BTC ya se proceso
    bien y ETH fue el que fallo) antes de avisar y relanzar la excepcion
    -- relanzar es importante para que cron siga marcando el fallo en sus
    propios logs, esto no lo sustituye, solo deja de ser SILENCIOSO por
    Telegram."""
    estado = None
    try:
        es_primer_arranque = not os.path.exists(RUTA_ESTADO)
        estado = cargar_estado()
        if es_primer_arranque:
            avisar_inicio(PARES, CAPITAL_INICIAL, RIESGO_BASE_PCT)

        procesar_comandos_telegram(estado)  # /balance N, si ha llegado desde el ciclo anterior

        datos = {par: cargar_o_actualizar_historial(par) for par in PARES}

        for par in PARES:
            df = datos[par]
            procesar_dia(par, df, len(df) - 1, estado, enviar=True)

        # recordatorio semanal de balance real -- pedido explicito del usuario
        # (19-sept-2026): recuerda cada 7 dias desde el ultimo balance real
        # reportado (o desde el ultimo recordatorio, si nunca ha llegado a
        # reportarlo) hasta que se actualice via --capital-real.
        hoy = datetime.now(timezone.utc).date()
        referencia = estado["fecha_ultimo_balance_real"] or estado["fecha_ultimo_recordatorio_balance"]
        if referencia is None or (hoy - date.fromisoformat(referencia)).days >= 7:
            avisar_recordatorio_balance()
            estado["fecha_ultimo_recordatorio_balance"] = hoy.isoformat()

        guardar_estado(estado)
        avisar_latido()  # aviso de "sigo vivo" aunque no haya habido trade -- ver docstring en alertas_telegram.py
        print(f"[{datetime.now(timezone.utc).isoformat()}] ciclo ok -- "
              f"capital_interno={estado['capital_interno']:.2f}e, "
              f"posiciones abiertas={[p for p in PARES if estado['posiciones'][p]]}")
    except Exception as e:
        if estado is not None:
            try:
                guardar_estado(estado)
            except Exception:
                pass
        avisar_error(f"{type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--capital-real":
        actualizar_capital_real(float(sys.argv[2]))
        print(f"capital_real_usuario actualizado a {sys.argv[2]}e")
    else:
        ejecutar_ciclo()
