import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import candidatos, mis_posiciones, salud, usuarios
from app.db.database import inicializar_tablas
from app.services import descubrimiento, refresher

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
    # motor de descubrimiento/refresco, igual que backend/main.py de la app
    # vieja -- corre en segundo plano durante toda la vida del proceso
    refresher.arrancar_en_segundo_plano()
    threading.Thread(target=descubrimiento.ciclo_descubrimiento, daemon=True).start()


app.include_router(salud.router)
app.include_router(usuarios.router)
app.include_router(candidatos.router)
app.include_router(mis_posiciones.router)

# cada router nuevo (mercado...) se registra aqui a medida que se porta
# desde la app vieja -- un router por recurso, no un solo main.py con todos
# los endpoints como en backend/main.py (la app vieja)
