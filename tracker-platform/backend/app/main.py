from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import salud, usuarios
from app.db.database import inicializar_tablas

app = FastAPI(title="Corvus")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restringir al dominio del frontend en producción
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    inicializar_tablas()


app.include_router(salud.router)
app.include_router(usuarios.router)

# cada router nuevo (traders, mercado, descubrimiento...) se registra aqui a
# medida que se porta desde la app vieja -- un router por recurso, no un
# solo main.py con todos los endpoints como en backend/main.py (la app vieja)
