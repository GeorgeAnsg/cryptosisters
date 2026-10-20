"""Posiciones que el usuario ha "abierto" el mismo copiando a un trader que
sigue -- equivalente a la coleccion mis_posiciones de Firestore en la app
vieja (boton Abrir en Posiciones, Cerrar aqui con el pnl a mano). Por
usuario, nunca se cruza con el pool global de candidatos."""
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import usuario_actual
from app.db.database import conectar

router = APIRouter(prefix="/mis-posiciones", tags=["mis-posiciones"])


class AbrirBody(BaseModel):
    traderAddress: str
    tipo: str
    coin: str
    lado: str | None = None


class CerrarBody(BaseModel):
    pnl: float


@router.get("")
def listar(uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        filas = conn.execute(
            "SELECT clave, trader_address, tipo, coin, lado, estado, fecha_apertura, fecha_cierre, pnl "
            "FROM mis_posiciones WHERE uid=? ORDER BY fecha_apertura DESC",
            (uid,),
        ).fetchall()
    return [
        {
            "clave": f["clave"], "traderAddress": f["trader_address"], "tipo": f["tipo"],
            "coin": f["coin"], "lado": f["lado"], "estado": f["estado"],
            "fechaApertura": f["fecha_apertura"], "fechaCierre": f["fecha_cierre"], "pnl": f["pnl"],
        }
        for f in filas
    ]


@router.put("/{clave}")
def abrir(clave: str, body: AbrirBody, uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO mis_posiciones
               (uid, clave, trader_address, tipo, coin, lado, estado, fecha_apertura)
               VALUES (?,?,?,?,?,?, 'abierta', ?)""",
            (uid, clave, body.traderAddress, body.tipo, body.coin, body.lado, int(time.time() * 1000)),
        )
    return {"ok": True}


@router.put("/{clave}/cerrar")
def cerrar(clave: str, body: CerrarBody, uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute(
            "UPDATE mis_posiciones SET estado='cerrada', fecha_cierre=?, pnl=? WHERE uid=? AND clave=?",
            (int(time.time() * 1000), body.pnl, uid, clave),
        )
    return {"ok": True}
