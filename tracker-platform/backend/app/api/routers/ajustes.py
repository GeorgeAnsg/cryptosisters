"""Preferencias por usuario -- de momento solo la whitelist de monedas que
quiere que le notifiquen (push + lista de Notificaciones). Lista vacia =
sin restriccion (todas), para que una cuenta nueva no se quede muda."""
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import usuario_actual
from app.db.database import conectar

router = APIRouter(prefix="/ajustes", tags=["ajustes"])


class AjustesBody(BaseModel):
    monedasNotificar: list[str]


@router.get("")
def obtener(uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        fila = conn.execute("SELECT monedas_notificar FROM ajustes WHERE uid=?", (uid,)).fetchone()
    return {"monedasNotificar": json.loads(fila["monedas_notificar"]) if fila else []}


@router.put("")
def guardar(body: AjustesBody, uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute(
            "INSERT INTO ajustes (uid, monedas_notificar) VALUES (?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET monedas_notificar=excluded.monedas_notificar",
            (uid, json.dumps(body.monedasNotificar)),
        )
    return {"ok": True}
