import os
from pathlib import Path

# config centralizada por variables de entorno -- nada de constantes sueltas
# repartidas por los routers/servicios, como pasaba en la app vieja
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "data" / "tracker.db"))
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
FIREBASE_CREDENTIALS_PATH = Path(
    os.environ.get("FIREBASE_CREDENTIALS_PATH", BASE_DIR / "secrets" / "firebase-service-account.json")
)
