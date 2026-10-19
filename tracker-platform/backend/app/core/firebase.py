import firebase_admin
from firebase_admin import credentials

from app.core.config import FIREBASE_CREDENTIALS_PATH

# inicializa la app de Firebase Admin UNA sola vez al importar este modulo --
# cualquier router/dep que necesite verificar tokens solo importa este
# archivo (por su efecto secundario), nunca llama a initialize_app() el
# mismo
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(str(FIREBASE_CREDENTIALS_PATH)))
