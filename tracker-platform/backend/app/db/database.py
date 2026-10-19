import sqlite3

from app.core.config import DB_PATH

# mismo patron que la app vieja (sqlite3 crudo, sin ORM) -- funciona bien a
# esta escala y no añade la complejidad de SQLAlchemy sin necesidad real
def conectar() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# llamado una vez al arrancar la app (ver main.py) -- crea las tablas si no
# existen, nunca las borra ni las migra; para cambios de esquema reales se
# añadira una migracion explicita cuando haga falta, no aqui
def inicializar_tablas() -> None:
    with conectar() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                uid TEXT PRIMARY KEY,
                email TEXT,
                creado_en TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        # que traders sigue cada usuario -- el descubrimiento de traders es
        # un proceso global en segundo plano (no dispara nada por usuario);
        # esto es solo la lista de follow/unfollow de cada uno
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuario_sigue (
                uid TEXT NOT NULL REFERENCES usuarios(uid),
                trader_address TEXT NOT NULL,
                creado_en TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (uid, trader_address)
            )
            """
        )
