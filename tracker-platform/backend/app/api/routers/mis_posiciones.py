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
    montoInvertido: float | None = None


class CerrarBody(BaseModel):
    pnl: float


class AjustarBody(BaseModel):
    delta: float  # positivo = añade, negativo = reduce


@router.get("")
def listar(uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        filas = conn.execute(
            "SELECT clave, trader_address, tipo, coin, lado, estado, fecha_apertura, fecha_cierre, pnl, monto_invertido "
            "FROM mis_posiciones WHERE uid=? ORDER BY fecha_apertura DESC",
            (uid,),
        ).fetchall()
    return [
        {
            "clave": f["clave"], "traderAddress": f["trader_address"], "tipo": f["tipo"],
            "coin": f["coin"], "lado": f["lado"], "estado": f["estado"],
            "fechaApertura": f["fecha_apertura"], "fechaCierre": f["fecha_cierre"], "pnl": f["pnl"],
            "montoInvertido": f["monto_invertido"],
        }
        for f in filas
    ]


@router.put("/{clave}")
def abrir(clave: str, body: AbrirBody, uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO mis_posiciones
               (uid, clave, trader_address, tipo, coin, lado, estado, fecha_apertura, monto_invertido)
               VALUES (?,?,?,?,?,?, 'abierta', ?, ?)""",
            (uid, clave, body.traderAddress, body.tipo, body.coin, body.lado, int(time.time() * 1000), body.montoInvertido),
        )
    return {"ok": True}


@router.put("/{clave}/ajustar")
def ajustar(clave: str, body: AjustarBody, uid: str = Depends(usuario_actual)):
    """Añadir o reducir lo invertido en una posicion ya abierta -- el monto
    nunca baja de 0 (si quiere sacarlo todo, que cierre con Cerrar)."""
    with conectar() as conn:
        conn.execute(
            "UPDATE mis_posiciones SET monto_invertido = MAX(0, COALESCE(monto_invertido, 0) + ?) "
            "WHERE uid=? AND clave=? AND estado='abierta'",
            (body.delta, uid, clave),
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
