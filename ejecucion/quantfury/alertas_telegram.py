"""
18-sept-2026: aviso de Telegram para la vertiente de ejecucion manual en
QuantFury (Fase 6-7 de `ejecucion/README.md`, hasta ahora vacia).

El usuario pidio explicitamente reutilizar tal cual el mecanismo de envio
que ya funcionaba en el bot viejo -- `enviar_telegram()` de aqui es una
copia literal de `v6/core/bot_core.py:send_telegram` (via
`ejecucion/paper_trading/notificar_resumen.py`, que ya la habia rescatado
antes), sin rediseñar nada. Lo unico que cambia respecto a esos bots
anteriores es el CONTENIDO de los tres mensajes, adaptado a como funciona
QuantFury de verdad (ver [[quantfury_balance]] y la conversacion del
18-sept-2026):
  - los importes son EUR (capital real depositado), no USDT -- QuantFury
    no es un exchange cripto normal.
  - el tamaño de posicion que se manda es el NOCIONAL en euros ya capado
    por `cartera/riesgo_quantfury.capar_a_poder_trading` (el limite fisico
    del tramo actual), no solo lo que pediria `tamano.calcular_tamano` en
    aislado.
  - el cierre puede venir por stop loss/take profit automatico O porque el
    bot detecta una señal de mercado (motor/salida) y pide vender a mano
    -- QuantFury no tiene ordenes automaticas, todo lo ejecuta el usuario.

No hay logica de trading aqui, solo construccion y envio de los tres
mensajes -- quien decide cuando avisar es el codigo que orquesta motores +
salidas + cartera + riesgo_quantfury.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass


def enviar_telegram(mensaje: str) -> bool:
    """Copia literal de `ejecucion/paper_trading/notificar_resumen.py:enviar_telegram`
    (a su vez rescatada de `v6/core/bot_core.py:send_telegram`) -- no
    redisenar, solo reutilizar."""
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[telegram] TELEGRAM_TOKEN/TELEGRAM_CHAT_ID no configurados -- no se envia nada")
        return False
    try:
        data = json.dumps({"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"}).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[telegram] fallo al enviar: {e}")
        return False


@dataclass
class AlertaCompra:
    par: str  # "BTCUSDT" / "ETHUSDT"
    direccion: str  # "largo" / "corto"
    precio_entrada: float
    stop_loss: float
    take_profit: float
    tamano_eur: float  # nocional ya capado a poder de trading (riesgo_quantfury.capar_a_poder_trading)
    poder_trading_actual: float  # poder de trading del tramo actual (riesgo_quantfury.poder_de_trading),
    # NO el capital real depositado -- bug corregido 19-sept-2026: el % que
    # importa es nocional/poder_de_trading (ej. 26e / 2000e = 1.3%), no
    # nocional/capital_real (26e / 100e = 26%, que es lo que se mandaba antes)


def mensaje_compra(a: AlertaCompra) -> str:
    """Construye el texto sin enviarlo -- separado de `avisar_compra` para
    que el generador de informes (`laboratorio/patrones/generar_reporte_2025.py`)
    pueda reutilizar EXACTAMENTE el mismo mensaje que mandaria el bot en
    vivo, sin duplicar el formato."""
    emoji = "📈" if a.direccion == "largo" else "📉"
    dir_es = "LONG (compra)" if a.direccion == "largo" else "SHORT (venta)"
    return (
        f"{emoji} <b>SEÑAL {dir_es}</b>\n"
        f"Par: <b>{a.par}</b>\n"
        f"Precio entrada: <b>{a.precio_entrada:,.2f}</b>\n"
        f"Tamaño posición: <b>{a.tamano_eur:,.2f} €</b> ({a.tamano_eur/a.poder_trading_actual*100:.1f}% del poder de trading usado)\n"
        f"Stop Loss:   {a.stop_loss:,.2f}  ({abs(a.precio_entrada-a.stop_loss)/a.precio_entrada*100:.2f}%)\n"
        f"Take Profit: {a.take_profit:,.2f}  ({abs(a.take_profit-a.precio_entrada)/a.precio_entrada*100:.2f}%)"
    )


def avisar_compra(a: AlertaCompra) -> bool:
    return enviar_telegram(mensaje_compra(a))


def mensaje_actualizacion(par: str, direccion: str, motivo: str, nuevo_sl: float, nuevo_tp: float) -> str:
    dir_es = "LONG" if direccion == "largo" else "SHORT"
    return (
        f"⚙️ <b>ACTUALIZACIÓN {dir_es} {par}</b>\n"
        f"{motivo}\n"
        f"Nuevo SL: {nuevo_sl:,.2f}\n"
        f"Nuevo TP: {nuevo_tp:,.2f}"
    )


def avisar_actualizacion(par: str, direccion: str, motivo: str, nuevo_sl: float, nuevo_tp: float) -> bool:
    return enviar_telegram(mensaje_actualizacion(par, direccion, motivo, nuevo_sl, nuevo_tp))


_MOTIVOS_CIERRE = {
    "TAKE_PROFIT":   "Take Profit alcanzado",
    "STOP_LOSS":     "Stop Loss tocado",
    "SENAL_BAJISTA": "Señal bajista detectada -- vender a mano",
    "SENAL_ALCISTA": "Señal alcista detectada -- vender a mano",
    "CAMBIO_CANDIDATO": "Candidato contrario más fuerte -- cambio de posición",
    "VENTA_PARCIAL": "Venta parcial de ganancias (50% @ +20%) -- resto de la posición sigue abierta",
    "TRAILING_RETROCESO_ALTO": "Trailing -- retroceso del 67,5% desde el máximo de ganancia flotante",
    "PENDIENTE_ACELERADA": "Movimiento fuerte en contra (pendiente acelerada) -- vender a mano",
    "TIEMPO_MAXIMO": "Tiempo máximo en la operación sin resolverse -- cierre por plazo",
}


# Stop-loss/take-profit se ponen como orden REAL en QuantFury al abrir la
# posicion (confirmado por el usuario, 19-sept-2026) -- la plataforma los
# ejecuta sola, al instante, sin esperar a este bot. Un mensaje con uno de
# estos dos motivos es solo la CONFIRMACION de que el contador interno ya
# se entero de algo que en QuantFury ya paso -- no una instruccion. Todos
# los demas motivos (racha rota, pendiente acelerada, trailing, cambio de
# candidato, venta parcial, tiempo maximo) SI son accion real: QuantFury
# no sabe nada de esas señales, alguien tiene que ir a la app a cerrar (o
# vender parte) a mano.
_MOTIVOS_SIN_ACCION = {"STOP_LOSS", "TAKE_PROFIT"}


def mensaje_venta(par: str, direccion: str, precio_cierre: float, pnl_eur: float,
                   pnl_pct: float, motivo: str, capital_tras_cierre: float) -> str:
    """`motivo` puede ser uno de `_MOTIVOS_CIERRE` (stop/take-profit
    automatico) o cualquier otro texto libre -- el bot puede pedir vender
    por una razon de mercado que no sea SL/TP (racha rota, cambio de
    candidato, etc.), QuantFury no ejecuta nada solo, siempre lo hace el
    usuario."""
    dir_es = "LONG" if direccion == "largo" else "SHORT"
    emoji = "✅" if pnl_eur >= 0 else "❌"
    res = "GANANCIA" if pnl_eur >= 0 else "PÉRDIDA"
    motivo_es = _MOTIVOS_CIERRE.get(motivo, motivo)
    nota = ("(ya ejecutado en QuantFury -- esto es solo confirmación, no hace falta que hagas nada)"
            if motivo in _MOTIVOS_SIN_ACCION else "⚠️ <b>ACCIÓN REQUERIDA:</b> cierra esto a mano en QuantFury")
    return (
        f"{emoji} <b>VENDER {dir_es} — {res}</b>\n"
        f"Par: <b>{par}</b>\n"
        f"Precio cierre: <b>{precio_cierre:,.2f}</b>\n"
        f"PnL: <b>{pnl_eur:+,.2f} € ({pnl_pct:+.2f}%)</b>\n"
        f"Motivo: {motivo_es}\n"
        f"{nota}\n"
        f"Capital tras cierre: {capital_tras_cierre:,.2f} €"
    )


def avisar_venta(par: str, direccion: str, precio_cierre: float, pnl_eur: float,
                  pnl_pct: float, motivo: str, capital_tras_cierre: float) -> bool:
    return enviar_telegram(mensaje_venta(par, direccion, precio_cierre, pnl_eur, pnl_pct, motivo, capital_tras_cierre))


def avisar_latido() -> bool:
    """Aviso de que el bot ha corrido este ciclo, aunque no haya habido
    ninguna operacion -- pedido explicito del usuario (19-sept-2026):
    sin esto, un ciclo que no encuentra señal es indistinguible de un cron
    que dejo de correr. Pensado para llamarse SIEMPRE al final de
    `bot_paper.ejecutar_ciclo`, haya habido trade o no."""
    from datetime import datetime, timezone
    return enviar_telegram(
        f"🟢 Bot QuantFury activo -- {datetime.now(timezone.utc).strftime('%d/%m %H:%M UTC')}"
    )


def avisar_inicio(pares: list[str], capital_inicial: float, riesgo_base_pct: float) -> bool:
    """Aviso de arranque -- pedido explicito del usuario (19-sept-2026),
    distinto del latido de cada ciclo (`avisar_latido`): se manda UNA sola
    vez, la primera vez que `bot_paper.py` corre sin `estado_paper.json`
    todavia (ver `cargar_estado`) -- asi confirma que el bot arranco con la
    configuracion correcta (pares, capital, riesgo) sin repetirse cada dia."""
    return enviar_telegram(
        "🚀 <b>Corvus IV -- bot iniciado</b>\n"
        f"Pares: {', '.join(pares)}\n"
        f"Capital inicial: {capital_inicial:,.2f} €\n"
        f"Riesgo por operación: {riesgo_base_pct*100:.1f}%"
    )


def leer_actualizaciones(offset: int) -> list[dict]:
    """Poll de `getUpdates` -- pensado para llamarse UNA vez al principio de
    cada ciclo cron (`bot_paper.ejecutar_ciclo`), no en un bucle infinito
    como haria un listener en tiempo real (ver v12/main.py en el otro
    proyecto, que si es un proceso que corre sin parar). `timeout=0`
    (no long-polling) porque el cron no debe quedarse esperando -- si no
    hay nada nuevo, devuelve al instante una lista vacia. Consecuencia
    aceptada (pedido explicito del usuario, 19-sept-2026): un /balance
    mandado justo despues de un ciclo no se aplica hasta el ciclo
    siguiente, no al momento."""
    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token:
        return []
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=0&allowed_updates=%5B%22message%22%5D"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data.get("result", [])
    except Exception as e:
        print(f"[telegram] fallo al leer actualizaciones: {e}")
        return []


def avisar_error(detalle: str) -> bool:
    """Aviso de fallo -- añadido 19-sept-2026 tras una auditoria completa
    del bot antes de subirlo a produccion: sin esto, si `ejecutar_ciclo`
    lanza una excepcion en cualquier punto (Binance caido, error de red,
    cualquier bug) antes de llegar a `avisar_latido`, NO se manda NINGUN
    mensaje -- un fallo real es indistinguible de un cron que sigue
    corriendo sin encontrar señal, que es exactamente lo que el latido
    se penso para evitar. Pensado para llamarse desde un try/except que
    envuelva TODO `ejecutar_ciclo`."""
    return enviar_telegram(
        f"🔴 <b>Corvus IV -- el ciclo ha fallado</b>\n<code>{detalle}</code>"
    )


def avisar_recordatorio_balance() -> bool:
    """Recordatorio semanal -- pedido explicito del usuario (19-sept-2026):
    "me tiene que pedir el balance cada semana y yo mandarselo". Desde que
    se añadio `bot_paper.procesar_comandos_telegram` (mismo dia), el
    usuario puede responder de verdad con `/balance <numero>` escrito en
    el chat/grupo de Telegram -- se aplica en el SIGUIENTE ciclo (el bot
    sigue siendo un script de cron, no un listener en tiempo real, ver
    docstring de `procesar_comandos_telegram`), no al instante."""
    return enviar_telegram(
        "📋 <b>Corvus IV -- recordatorio semanal</b>\n"
        "¿Cuál es tu balance REAL de QuantFury esta semana?\n"
        "Responde aquí mismo con: <code>/balance 105.30</code>"
    )
