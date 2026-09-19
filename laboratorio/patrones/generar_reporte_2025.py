"""
19-sept-2026: informe visual (HTML) de la prueba en la particion de
Validacion (2025) del sistema completo -- pedido explicito del usuario:
"los dos graficos [ETH y BTC], las entradas y salidas en el grafico con
las flechas y las lineas, el listado de los trades, las ganancias y
perdidas y las notificaciones que enviaria [...] tambien notificacion de
que el bot esta corriendo".

No reimplementa la logica de trading: recorre 2025 dia a dia llamando a
`ejecucion.quantfury.bot_paper.procesar_dia(..., enviar=False)`, la MISMA
funcion que usa el bot en vivo -- lo unico que hace este script es no
enviar los mensajes de verdad y en su lugar guardarlos para mostrarlos en
la pagina, mas construir los graficos y la tabla de operaciones a partir
de los eventos que esa funcion ya devuelve.

Simplificacion deliberada para esta prueba historica (documentada, no
oculta): `capital_real_usuario` se sincroniza cada dia con
`capital_interno` (no hay un usuario real reportando balance semanal en
un backtest) -- el capado de QuantFury se aplica igualmente, solo que
usando el propio capital de papel como referencia del tramo.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from laboratorio.datos_lab import cargar_ohlcv_lab
from ejecucion.quantfury.bot_paper import PARES, CAPITAL_INICIAL, precalcular_series, procesar_dia
from ejecucion.quantfury.alertas_telegram import avisar_latido

MOTIVO = ("Generar el informe visual de la prueba en la particion de Validacion (2025) "
          "del sistema completo (motores+entradas+salidas+cartera+riesgo_quantfury), "
          "pedido explicito del usuario 19-sept-2026")


def _estado_inicial() -> dict:
    return {
        "capital_interno": CAPITAL_INICIAL,
        "capital_real_usuario": CAPITAL_INICIAL,
        "posiciones": {par: None for par in PARES},
    }


def correr_2025(par: str) -> tuple[dict, list[dict]]:
    df = cargar_ohlcv_lab(par, "1d", estrategia="generar_reporte_2025",
                           acceso_validacion=True, motivo=MOTIVO)
    estado = _estado_inicial()
    idxs_2025 = [i for i, f in enumerate(df["open_time"]) if f.year == 2025]
    series = precalcular_series(df)  # una sola vez para todo el año, ver docstring en bot_paper.py

    eventos = []
    for idx in idxs_2025:
        estado["capital_real_usuario"] = estado["capital_interno"]
        eventos.extend(procesar_dia(par, df, idx, estado, enviar=False, series=series))

    velas_2025 = df.iloc[idxs_2025][["open_time", "close"]].reset_index(drop=True)
    return {
        "capital_final": estado["capital_interno"],
        "velas": [{"fecha": f.strftime("%Y-%m-%d"), "close": float(c)}
                  for f, c in zip(velas_2025["open_time"], velas_2025["close"])],
    }, eventos


def _emparejar_trades(eventos: list[dict]) -> list[dict]:
    """Los eventos de `procesar_dia` alternan abre/(venta_parcial)/cierra
    (una sola posicion a la vez por par) -- los junta en un solo registro
    de trade para la tabla del informe. Desde la venta parcial confirmada
    el 14-sept-2026 (ver [[project_corvus4_switch_confirmado]]), una
    operacion puede tener un evento `venta_parcial` intermedio que realiza
    parte de la ganancia antes del cierre final -- su PnL se SUMA al del
    cierre para que la tabla muestre el resultado TOTAL de la operacion,
    no solo el tramo que queda abierto al final."""
    trades = []
    abierta = None
    pnl_parcial_acumulado = 0.0
    for e in eventos:
        if e["evento"] == "abre":
            abierta = e
            pnl_parcial_acumulado = 0.0
        elif e["evento"] == "venta_parcial" and abierta is not None:
            pnl_parcial_acumulado += e["pnl_eur"]
        elif e["evento"] == "cierra" and abierta is not None:
            trades.append({
                "direccion": abierta["direccion"],
                "fecha_entrada": abierta["fecha"].strftime("%Y-%m-%d"),
                "precio_entrada": abierta["precio"],
                "fecha_salida": e["fecha"].strftime("%Y-%m-%d"),
                "precio_salida": e["precio"],
                "pnl_eur": round(pnl_parcial_acumulado + e["pnl_eur"], 2),
                "motivo": e["motivo"],
                "capital_interno_tras": e["capital_interno_tras"],
            })
            abierta = None
    return trades


def _notificaciones(eventos: list[dict]) -> list[dict]:
    return [{"fecha": e["fecha"].strftime("%Y-%m-%d"), "evento": e["evento"], "texto": e["texto"]}
            for e in eventos]


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Corvus IV -- Validacion 2025</title>
<style>
  :root {
    --bg: #0b0f14; --panel: #121821; --borde: #212b38; --texto: #e6edf3; --texto-tenue: #8b98a8;
    --verde: #35c98f; --rojo: #ef5b5b; --acento: #4da3ff; --amarillo: #e8b64c;
  }
  * { box-sizing: border-box; }
  body { background: var(--bg); color: var(--texto); font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; }
  h1 { font-size: 1.4rem; margin: 0 0 4px; }
  .subtitulo { color: var(--texto-tenue); font-size: 0.9rem; margin-bottom: 24px; }
  .grid-monedas { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 900px) { .grid-monedas { grid-template-columns: 1fr; } }
  .panel { background: var(--panel); border: 1px solid var(--borde); border-radius: 10px; padding: 16px; margin-bottom: 20px; }
  .panel h2 { margin: 0 0 4px; font-size: 1.1rem; }
  .resumen { display: flex; gap: 18px; font-size: 0.85rem; color: var(--texto-tenue); margin-bottom: 10px; flex-wrap: wrap; }
  .resumen b { color: var(--texto); }
  .ganancia { color: var(--verde); } .perdida { color: var(--rojo); }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th, td { padding: 6px 8px; text-align: right; border-bottom: 1px solid var(--borde); white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--texto-tenue); font-weight: 600; }
  .tabla-scroll { max-height: 340px; overflow-y: auto; }
  .pill { padding: 1px 8px; border-radius: 999px; font-size: 0.72rem; }
  .pill-largo { background: rgba(53,201,143,0.15); color: var(--verde); }
  .pill-corto { background: rgba(239,91,91,0.15); color: var(--rojo); }
  .feed { max-height: 480px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
  .msg { background: #0e1520; border: 1px solid var(--borde); border-radius: 8px; padding: 10px 12px; font-size: 0.82rem; white-space: pre-line; }
  .msg .fecha { color: var(--texto-tenue); font-size: 0.72rem; margin-bottom: 4px; }
  .msg.latido { color: var(--texto-tenue); font-style: italic; }
  b { font-weight: 600; }
  canvas { width: 100%; display: block; }
  .error-banner { background: rgba(239,91,91,0.12); border: 1px solid var(--rojo); color: var(--rojo);
    border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; font-size: 0.85rem; white-space: pre-wrap; }
</style>
</head>
<body>
  <h1>Corvus IV -- prueba fuera de muestra en 2025</h1>
  <div class="subtitulo">Motores + entrada en vivo + salidas (stop/take-profit/racha rota) + cambio de candidato + riesgo global + riesgo QuantFury. Particion de Validacion, nunca usada para calibrar nada.</div>

  <div class="grid-monedas" id="grid-monedas"></div>

  <div class="panel">
    <h2>Notificaciones que habria mandado el bot</h2>
    <div class="subtitulo">Incluye el aviso de "sigo vivo" que se manda al final de cada ciclo real, aunque no haya trade.</div>
    <div class="feed" id="feed-notificaciones"></div>
  </div>

<script>
// Grafico dibujado a mano en <canvas>, SIN libreria externa -- 19-sept-2026:
// la version anterior cargaba Chart.js desde un CDN (cdnjs.cloudflare.com).
// Si el ordenador que abre el fichero no tiene internet en ese momento, o
// algo bloquea ese dominio (cortafuegos, adblocker), `Chart` queda
// indefinido y `new Chart(...)` lanzaba una excepcion SIN capturar que
// paraba el resto del script -- ni la tabla de trades de la segunda
// moneda ni el feed de notificaciones llegaban a pintarse, dejando la
// pagina "vacia" salvo el titulo estatico. Dibujar el grafico a mano
// quita esa dependencia de internet por completo (el informe funciona
// sin conexion, abierto con doble-clic) y el try/catch de mas abajo deja
// un aviso visible en vez de una pagina en blanco si algo mas falla.
const DATOS = __DATOS_JSON__;

function colorPnl(v){ return v >= 0 ? 'ganancia' : 'perdida'; }

function dibujarMarcador(ctx, x, y, tipo, color) {
  ctx.fillStyle = color;
  if (tipo === 'circulo') {
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
  } else if (tipo === 'triangulo') {
    ctx.beginPath(); ctx.moveTo(x, y - 6); ctx.lineTo(x - 6, y + 5); ctx.lineTo(x + 6, y + 5); ctx.closePath(); ctx.fill();
  } else {
    ctx.save(); ctx.translate(x, y); ctx.rotate(Math.PI / 4); ctx.fillRect(-5, -5, 10, 10); ctx.restore();
  }
}

function dibujarGrafico(canvas, fechas, precios, trades) {
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth || 600, H = parseInt(canvas.getAttribute('height'), 10) || 220;
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.height = H + 'px';
  ctx.scale(dpr, dpr);

  const padL = 58, padR = 12, padT = 10, padB = 22;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const minP = Math.min(...precios), maxP = Math.max(...precios);
  const margen = (maxP - minP) * 0.06 || 1;
  const yMin = minP - margen, yMax = maxP + margen;
  const xAt = i => padL + (fechas.length <= 1 ? 0 : (i / (fechas.length - 1)) * plotW);
  const yAt = v => padT + (1 - (v - yMin) / (yMax - yMin)) * plotH;

  ctx.font = '11px -apple-system, "Segoe UI", Roboto, sans-serif';
  ctx.strokeStyle = '#212b38'; ctx.fillStyle = '#8b98a8';
  const nLineas = 5;
  for (let k = 0; k <= nLineas; k++) {
    const v = yMin + (yMax - yMin) * k / nLineas;
    const y = yAt(v);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
    ctx.textAlign = 'right'; ctx.fillText(v.toFixed(0), padL - 6, y + 3);
  }
  const nFechas = Math.min(6, fechas.length - 1);
  ctx.textAlign = 'center';
  for (let k = 0; k <= nFechas; k++) {
    const i = Math.round(k / nFechas * (fechas.length - 1));
    ctx.fillText(fechas[i], xAt(i), H - 6);
  }

  ctx.strokeStyle = '#4da3ff'; ctx.lineWidth = 1.3; ctx.beginPath();
  precios.forEach((p, i) => { const x = xAt(i), y = yAt(p); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); });
  ctx.stroke();

  trades.forEach(t => {
    const iE = fechas.indexOf(t.fecha_entrada), iS = fechas.indexOf(t.fecha_salida);
    if (iE === -1 || iS === -1) return;
    const color = t.pnl_eur >= 0 ? '#35c98f' : '#ef5b5b';
    const xE = xAt(iE), yE = yAt(t.precio_entrada), xS = xAt(iS), yS = yAt(t.precio_salida);
    ctx.strokeStyle = color; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(xE, yE); ctx.lineTo(xS, yS); ctx.stroke();
    dibujarMarcador(ctx, xE, yE, t.direccion === 'largo' ? 'triangulo' : 'diamante', color);
    dibujarMarcador(ctx, xS, yS, 'circulo', color);
  });
}

function construirPanelMoneda(par, d) {
  const cont = document.createElement('div');
  cont.className = 'panel';
  const retorno = ((d.capital_final / __CAPITAL_INICIAL__) - 1) * 100;
  cont.innerHTML = `
    <h2>${par}</h2>
    <div class="resumen">
      <span>Capital interno final: <b class="${colorPnl(retorno)}">${d.capital_final.toFixed(2)}€ (${retorno>=0?'+':''}${retorno.toFixed(1)}%)</b></span>
      <span>Trades: <b>${d.trades.length}</b></span>
      <span>Ganadoras: <b>${d.trades.filter(t=>t.pnl_eur>=0).length}</b></span>
    </div>
    <canvas id="chart-${par}" height="220"></canvas>
    <div class="tabla-scroll">
      <table>
        <thead><tr><th>Dir</th><th>Entrada</th><th>Precio</th><th>Salida</th><th>Precio</th><th>PnL €</th><th>Motivo</th></tr></thead>
        <tbody>
          ${d.trades.map(t => `<tr>
            <td><span class="pill pill-${t.direccion}">${t.direccion}</span></td>
            <td>${t.fecha_entrada}</td><td>${t.precio_entrada.toFixed(2)}</td>
            <td>${t.fecha_salida}</td><td>${t.precio_salida.toFixed(2)}</td>
            <td class="${colorPnl(t.pnl_eur)}">${t.pnl_eur>=0?'+':''}${t.pnl_eur.toFixed(2)}</td>
            <td>${t.motivo}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
  document.getElementById('grid-monedas').appendChild(cont);

  const fechas = d.velas.map(v => v.fecha);
  const precios = d.velas.map(v => v.close);
  dibujarGrafico(document.getElementById(`chart-${par}`), fechas, precios, d.trades);
}

try {
  for (const par of Object.keys(DATOS.monedas)) {
    construirPanelMoneda(par, DATOS.monedas[par]);
  }

  const feed = document.getElementById('feed-notificaciones');
  DATOS.notificaciones.forEach(n => {
    const div = document.createElement('div');
    div.className = 'msg' + (n.evento === 'latido' ? ' latido' : '');
    div.innerHTML = `<div class="fecha">${n.fecha} -- ${n.par || ''}</div>${n.texto}`;
    feed.appendChild(div);
  });
} catch (err) {
  const aviso = document.createElement('div');
  aviso.className = 'error-banner';
  aviso.textContent = 'Este informe no ha podido terminar de dibujarse (' + err.message + '). '
    + 'Esto es un fallo del generador, no de tus datos -- avisa para que se corrija.';
  document.body.insertBefore(aviso, document.body.firstChild.nextSibling);
}
</script>
</body>
</html>
"""


def main():
    monedas = {}
    todos_eventos = []
    for par in PARES:
        resumen, eventos = correr_2025(par)
        resumen["trades"] = _emparejar_trades(eventos)
        monedas[par] = resumen
        for e in eventos:
            e["par"] = par
        todos_eventos.extend(eventos)

    todos_eventos.sort(key=lambda e: e["fecha"])
    notificaciones = _notificaciones(todos_eventos)
    for n, e in zip(notificaciones, todos_eventos):
        n["par"] = e["par"]

    datos = {"monedas": monedas, "notificaciones": notificaciones}
    html = HTML_TEMPLATE.replace("__DATOS_JSON__", json.dumps(datos, ensure_ascii=False))
    html = html.replace("__CAPITAL_INICIAL__", str(CAPITAL_INICIAL))

    ruta = "/Users/jorgeansotegui/Desktop/corvus4/laboratorio/patrones/reporte_2025_validacion.html"
    with open(ruta, "w") as f:
        f.write(html)
    print(f"informe generado: {ruta}")
    for par, d in monedas.items():
        retorno = (d["capital_final"] / CAPITAL_INICIAL - 1) * 100
        print(f"  {par}: {d['capital_final']:.2f}e ({retorno:+.1f}%), {len(d['trades'])} trades")


if __name__ == "__main__":
    main()
