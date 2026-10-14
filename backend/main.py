import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import db
import descubrimiento
import hyperliquid
import refresher
import seed
import telegram_bot

API_KEY = os.environ.get("API_KEY")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # publico pero protegido por API_KEY, ver comprobar_clave()
    allow_methods=["*"],
    allow_headers=["*"],
)


def comprobar_clave(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="clave invalida")


@app.on_event("startup")
def iniciar():
    db.iniciar()
    seed.sembrar_si_vacio()
    refresher.arrancar_en_segundo_plano()
    threading.Thread(target=descubrimiento.ciclo_descubrimiento, daemon=True).start()
    telegram_bot.arrancar_en_segundo_plano()


@app.get("/candidatos")
def listar_candidatos(x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    filas = conn.execute("SELECT * FROM candidatos").fetchall()
    conn.close()
    return [db.fila_a_candidato(f) for f in filas]


@app.delete("/candidatos/{addr}")
def borrar_candidato(addr: str, x_api_key: str | None = Header(default=None)):
    """Quitar un candidato de la lista del todo -- para limpiar entradas sin
    sentido (cuentas vacías, pruebas) a mano, sin esperar a que el ciclo de
    permanencia decida borrarlo solo."""
    comprobar_clave(x_api_key)
    conn = db.conectar()
    conn.execute("DELETE FROM candidatos WHERE address=?", (addr,))
    conn.commit()
    conn.close()
    return {"ok": True}


class SeguirBody(BaseModel):
    # se puede seguir/dejar de seguir trading y spot por separado -- cada uno
    # es opcional, solo se toca el que venga informado
    sigue_trading: bool | None = None
    sigue_spot: bool | None = None


@app.patch("/candidatos/{addr}")
def marcar_seguir(addr: str, body: SeguirBody, x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    if body.sigue_trading is not None:
        conn.execute("UPDATE candidatos SET sigue_trading=? WHERE address=?", (int(body.sigue_trading), addr))
    if body.sigue_spot is not None:
        conn.execute("UPDATE candidatos SET sigue_spot=? WHERE address=?", (int(body.sigue_spot), addr))
    # "siguiendo" se mantiene como derivado (sigue_trading O sigue_spot) para
    # todo lo que solo necesita saber "¿se sigue a este trader, en lo que sea?"
    conn.execute("UPDATE candidatos SET siguiendo=(sigue_trading OR sigue_spot) WHERE address=?", (addr,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/alertas")
def listar_alertas(x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    filas = [dict(f) for f in conn.execute("SELECT * FROM alertas").fetchall()]
    conn.close()
    return filas


class EstadoBody(BaseModel):
    estado: str


@app.patch("/alertas/{id}")
def actualizar_alerta(id: str, body: EstadoBody, x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    conn.execute("UPDATE alertas SET estado=? WHERE id=?", (body.estado, id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/mis_posiciones")
def listar_mis_posiciones(x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    filas = [dict(f) for f in conn.execute("SELECT * FROM mis_posiciones").fetchall()]
    conn.close()
    return filas


class AbrirBody(BaseModel):
    id: str
    addr: str
    tipo: str
    coin: str
    lado: str | None = None
    alerta_id: str | None = None
    tamaño: float | None = None
    precio_entrada: float | None = None
    tamaño_trader: float | None = None


@app.post("/mis_posiciones")
def abrir_posicion(body: AbrirBody, x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    db.abrir_posicion(conn, body.id, body.addr, body.tipo, body.coin, body.lado, body.alerta_id,
                       body.tamaño, body.precio_entrada, body.tamaño_trader)
    conn.close()
    return {"ok": True}


class AñadirBody(BaseModel):
    tamaño_adicional: float
    precio: float


@app.patch("/mis_posiciones/{id}/añadir")
def añadir_a_posicion(id: str, body: AñadirBody, x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    fila = conn.execute("SELECT tamaño, precio_entrada FROM mis_posiciones WHERE id=? AND estado='abierta'", (id,)).fetchone()
    if fila is None:
        conn.close()
        raise HTTPException(status_code=404, detail="posicion no encontrada o ya cerrada")
    tamaño_antes = fila["tamaño"] or 0
    precio_antes = fila["precio_entrada"] if fila["precio_entrada"] is not None else body.precio
    tamaño_nuevo = tamaño_antes + body.tamaño_adicional
    # precio medio ponderado por tamaño, como si fuera un solo coste medio acumulado
    precio_nuevo = (tamaño_antes * precio_antes + body.tamaño_adicional * body.precio) / tamaño_nuevo
    conn.execute("UPDATE mis_posiciones SET tamaño=?, precio_entrada=? WHERE id=?", (tamaño_nuevo, precio_nuevo, id))
    conn.commit()
    conn.close()
    return {"ok": True, "tamaño": tamaño_nuevo, "precio_entrada": round(precio_nuevo, 6)}


class ReducirBody(BaseModel):
    tamaño_reducido: float
    precio: float


@app.patch("/mis_posiciones/{id}/reducir")
def reducir_posicion(id: str, body: ReducirBody, x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    fila = conn.execute("SELECT * FROM mis_posiciones WHERE id=? AND estado='abierta'", (id,)).fetchone()
    if fila is None:
        conn.close()
        raise HTTPException(status_code=404, detail="posicion no encontrada o ya cerrada")
    tamaño_actual = fila["tamaño"] or 0
    if body.tamaño_reducido <= 0 or body.tamaño_reducido > tamaño_actual * 1.0001:
        conn.close()
        raise HTTPException(status_code=400, detail="tamaño a reducir invalido")
    # short gana cuando el precio baja, el resto (long/spot) gana cuando sube
    signo = -1 if fila["lado"] == "Short" else 1
    pnl = (body.precio - fila["precio_entrada"]) * body.tamaño_reducido * signo
    resto = tamaño_actual - body.tamaño_reducido
    if resto <= tamaño_actual * 0.001:  # reducir (casi) todo = cerrar del todo
        conn.execute(
            "UPDATE mis_posiciones SET estado='cerrada', pnl=?, fecha_cierre=? WHERE id=?",
            (round(pnl, 2), int(time.time() * 1000), id),
        )
    else:
        # la parte reducida se registra como un cierre parcial propio (para
        # que Estadisticas la cuente), y la posicion original se queda
        # abierta con lo que resta, mismo precio de entrada (coste no cambia al reducir)
        conn.execute(
            """INSERT INTO mis_posiciones (id, addr, tipo, coin, lado, estado, fecha_apertura, fecha_cierre,
               pnl, alerta_id, tamaño, precio_entrada, tamaño_trader_visto)
               VALUES (?,?,?,?,?,'cerrada',?,?,?,?,?,?,?)""",
            (f"{id}_r{int(time.time()*1000)}", fila["addr"], fila["tipo"], fila["coin"], fila["lado"],
             fila["fecha_apertura"], int(time.time() * 1000), round(pnl, 2), fila["alerta_id"],
             body.tamaño_reducido, fila["precio_entrada"], fila["tamaño_trader_visto"]),
        )
        conn.execute("UPDATE mis_posiciones SET tamaño=? WHERE id=?", (resto, id))
    conn.commit()
    conn.close()
    return {"ok": True, "pnl": round(pnl, 2), "resto": round(resto, 8)}


class CerrarBody(BaseModel):
    pnl: float


@app.patch("/mis_posiciones/{id}")
def cerrar_posicion(id: str, body: CerrarBody, x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    conn.execute(
        "UPDATE mis_posiciones SET estado='cerrada', pnl=?, fecha_cierre=? WHERE id=?",
        (body.pnl, int(time.time() * 1000), id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/precio/{coin}")
def precio_endpoint(coin: str, tipo: str = "trading", x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    return {"precio": hyperliquid.precio_actual(coin, tipo)}


@app.post("/admin/forzar_descubrimiento")
def forzar_descubrimiento(x_api_key: str | None = Header(default=None)):
    """Lanza el ciclo de descubrimiento/desestimiento ahora mismo, sin
    esperar al ciclo semanal -- util para que un cambio en los umbrales de
    puntuacion (p.ej. el filtro de inactividad) se aplique a quien ya esta
    en la lista sin esperar hasta una semana. Se ejecuta en un hilo aparte
    porque tarda (pide el año completo de varios traders); la llamada
    responde al momento."""
    comprobar_clave(x_api_key)

    def lanzar():
        descubrimiento.descubrir_candidatos()
        conn = db.conectar()
        db.meta_set(conn, "ultimo_descubrimiento", str(time.time()))
        conn.close()

    threading.Thread(target=lanzar, daemon=True).start()
    return {"ok": True, "mensaje": "lanzado en segundo plano, tardará unos minutos"}


@app.get("/spot_meta")
def spot_meta(x_api_key: str | None = Header(default=None)):
    """Mapa {'@indice': 'NOMBRE'} de TODAS las monedas spot de Hyperliquid --
    el frontend antes tenia una lista fija a mano que se quedaba corta en
    cuanto Hyperliquid listaba algo nuevo (salia '@591' en vez del nombre).
    Esta es la misma fuente que ya usa el backend para resolver nombres."""
    comprobar_clave(x_api_key)
    return hyperliquid.cargar_spot_meta()


@app.get("/salud")
def salud():
    return {"ok": True}


INDEX_HTML_PATH = Path(__file__).parent / "static" / "index.html"


@app.get("/", response_class=HTMLResponse)
def pagina_principal():
    # la API_KEY se inyecta aqui en vez de dejarla escrita en el HTML a mano
    html = INDEX_HTML_PATH.read_text()
    return html.replace("PON_AQUI_TU_API_KEY", API_KEY or "")
