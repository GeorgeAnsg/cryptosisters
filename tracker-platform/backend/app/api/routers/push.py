from urllib.parse import urlparse

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


# el contenido del aviso sigue siendo el mismo para todos, pero guardamos
# el uid para poder aplicarle su whitelist de monedas (ver ajustes.py)
# antes de mandarle cada push -- usuario_actual exige login de paso
@router.post("/suscribirse")
def suscribirse(s: Suscripcion, uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO push_suscripciones (endpoint, p256dh, auth, uid) VALUES (?, ?, ?, ?)",
            (s.endpoint, s.p256dh, s.auth, uid),
        )
    return {"ok": True}


@router.delete("/suscribirse")
def desuscribirse(endpoint: str, uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute("DELETE FROM push_suscripciones WHERE endpoint=?", (endpoint,))
    return {"ok": True}


# diagnostico -- para saber de verdad cuantas suscripciones hay guardadas y
# de que proveedor es cada una (web.push.apple.com, fcm.googleapis.com...)
# sin tener que adivinar por el numero de "enviados" del boton de prueba
@router.get("/suscripciones")
def listar_suscripciones(uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        filas = conn.execute("SELECT endpoint, creado_en FROM push_suscripciones ORDER BY creado_en").fetchall()
    return [{"proveedor": urlparse(f["endpoint"]).netloc, "desde": f["creado_en"]} for f in filas]


# boton "Borrar todas" -- para empezar de cero cuando hay suscripciones
# fantasma (de un dispositivo reinstalado, de un intento fallido...) que
# inflan el numero de "enviados" sin que lleguen de verdad
@router.delete("/suscripciones")
def borrar_todas(uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute("DELETE FROM push_suscripciones")
    return {"ok": True}


# boton "Enviar prueba" en Notificaciones -- para poder confirmar de punta
# a punta (VAPID + suscripcion + que de verdad salta en el dispositivo) sin
# tener que esperar a la proxima alerta real
@router.post("/probar")
def probar(uid: str = Depends(usuario_actual)):
    return push.enviar_a_todos("Corvus", "Esto es una notificación de prueba 🔔")
