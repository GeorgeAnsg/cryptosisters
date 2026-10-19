from fastapi import Header, HTTPException
from firebase_admin import auth as firebase_auth

from app.core import firebase  # noqa: F401 -- se importa por su efecto secundario (inicializa la app de Firebase Admin)


def usuario_actual(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="falta token de autenticación")
    token = authorization.removeprefix("Bearer ")
    try:
        datos = firebase_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="token inválido o caducado")
    return datos["uid"]
