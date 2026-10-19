from fastapi import APIRouter, Depends
from firebase_admin import auth as firebase_auth

from app.api.deps import usuario_actual
from app.db.database import conectar

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


# llamado por el frontend justo despues de loguear -- crea la fila en
# "usuarios" si es la primera vez que se ve ese uid (login o registro, tanto
# da), si no, no hace nada
@router.post("/sesion")
def abrir_sesion(uid: str = Depends(usuario_actual)):
    email = firebase_auth.get_user(uid).email
    with conectar() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO usuarios (uid, email) VALUES (?, ?)",
            (uid, email),
        )
    return {"uid": uid, "email": email}


@router.get("/sigue")
def listar_seguidos(uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        filas = conn.execute(
            "SELECT trader_address FROM usuario_sigue WHERE uid = ?", (uid,)
        ).fetchall()
    return [f["trader_address"] for f in filas]


@router.put("/sigue/{trader_address}")
def seguir(trader_address: str, uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO usuario_sigue (uid, trader_address) VALUES (?, ?)",
            (uid, trader_address),
        )
    return {"ok": True}


@router.delete("/sigue/{trader_address}")
def dejar_de_seguir(trader_address: str, uid: str = Depends(usuario_actual)):
    with conectar() as conn:
        conn.execute(
            "DELETE FROM usuario_sigue WHERE uid = ? AND trader_address = ?",
            (uid, trader_address),
        )
    return {"ok": True}
