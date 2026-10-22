import json

from fastapi import APIRouter, Depends

from app.api.deps import usuario_actual
from app.db import database as db
from app.db.database import conectar

router = APIRouter(prefix="/freldi", tags=["freldi"])


@router.get("")
def obtener(_uid: str = Depends(usuario_actual)):
    """Snapshot cacheado (ver freldi.refrescar_cache, se recalcula como
    mucho una vez al dia) -- nunca llama a Multivac en caliente."""
    with conectar() as conn:
        snapshot = db.meta_get(conn, "freldi_snapshot")
        actualizado = db.meta_get(conn, "freldi_actualizado")
    return {
        "data": json.loads(snapshot) if snapshot else None,
        "actualizadoTs": float(actualizado) * 1000 if actualizado else None,
    }
