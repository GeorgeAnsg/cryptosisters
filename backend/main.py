import os
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import refresher
import seed

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


@app.get("/candidatos")
def listar_candidatos(x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    filas = conn.execute("SELECT * FROM candidatos").fetchall()
    conn.close()
    return [db.fila_a_candidato(f) for f in filas]


class SeguirBody(BaseModel):
    siguiendo: bool


@app.patch("/candidatos/{addr}")
def marcar_seguir(addr: str, body: SeguirBody, x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    conn.execute("UPDATE candidatos SET siguiendo=? WHERE address=?", (int(body.siguiendo), addr))
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


@app.post("/mis_posiciones")
def abrir_posicion(body: AbrirBody, x_api_key: str | None = Header(default=None)):
    comprobar_clave(x_api_key)
    conn = db.conectar()
    conn.execute(
        """INSERT INTO mis_posiciones (id, addr, tipo, coin, lado, estado, fecha_apertura, alerta_id)
           VALUES (?,?,?,?,?,'abierta',?,?)""",
        (body.id, body.addr, body.tipo, body.coin, body.lado, int(time.time() * 1000), body.alerta_id),
    )
    if body.alerta_id:
        conn.execute("UPDATE alertas SET estado='hecho' WHERE id=?", (body.alerta_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


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


@app.get("/salud")
def salud():
    return {"ok": True}
