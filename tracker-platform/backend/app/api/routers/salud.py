from fastapi import APIRouter

router = APIRouter(tags=["salud"])


@router.get("/salud")
def salud():
    return {"ok": True}
