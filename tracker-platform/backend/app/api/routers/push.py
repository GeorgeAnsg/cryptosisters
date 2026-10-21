from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import usuario_actual
from app.db.database import conectar
from app.services import push
from app.services.push import VAPID_PUBLIC_KEY

router = APIRouter(prefix="/push", tags=["push"])


class Suscripcion(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@router.get("/clave-publica")
def clave_publica():
    return {"clave": VAPID_PUBLIC_KEY}


# no hay uid en la tabla -- el aviso es un broadcast global (igual que
# Telegram), guardar quien es solo serviria para "quien tiene activado",
# que no se usa todavia; usuario_actual se exige solo para que no la pueda
# rellenar cualquiera sin loguear
@router.post("/suscribirse")
def suscribirse(s: Suscripcion, uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO push_suscripciones (endpoint, p256dh, auth) VALUES (?, ?, ?)",
            (s.endpoint, s.p256dh, s.auth),
        )
    return {"ok": True}


@router.delete("/suscribirse")
def desuscribirse(endpoint: str, uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute("DELETE FROM push_suscripciones WHERE endpoint=?", (endpoint,))
    return {"ok": True}


# boton "Enviar prueba" en Notificaciones -- para poder confirmar de punta
# a punta (VAPID + suscripcion + que de verdad salta en el dispositivo) sin
# tener que esperar a la proxima alerta real
@router.post("/probar")
def probar(uid: str = Depends(usuario_actual)):
    return push.enviar_a_todos("Corvus", "Esto es una notificación de prueba 🔔")
