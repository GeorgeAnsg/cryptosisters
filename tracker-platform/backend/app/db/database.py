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
        # pool global de descubrimiento (igual que backend/candidatos de la app
        # vieja) -- a diferencia de alli, aqui NO guarda quien lo sigue (eso
        # vive en usuario_sigue, es por usuario); desestimado_motivo/fecha se
        # rellena cuando el ciclo de descubrimiento decide que ya no cumple el
        # minimo de mantenimiento, para poder avisar a quien lo seguia antes
        # de que refrescar_no_seguidos/revisar_requisitos_permanencia lo borre
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candidatos (
                address TEXT PRIMARY KEY,
                categoria TEXT, antiguedad INTEGER, estilo TEXT, riesgo TEXT,
                cuenta REAL,
                retorno_pct REAL, profit_factor REAL, puntuacion INTEGER, win_rate REAL, drawdown REAL,
                puntuacion_spot INTEGER, win_rate_spot REAL, retorno_pct_spot REAL, drawdown_spot REAL, profit_factor_spot REAL,
                descubierto_ts INTEGER,
                desestimado_motivo TEXT, desestimado_fecha INTEGER,
                posicion_actual TEXT DEFAULT '[]',
                holdings_spot TEXT DEFAULT '[]',
                operaciones_recientes TEXT DEFAULT '[]',
                monedas_top TEXT DEFAULT '[]'
            )
            """
        )
        # migracion explicita para BDs creadas antes de monedas_top (la
        # tabla ya existe, CREATE TABLE IF NOT EXISTS no la toca)
        try:
            conn.execute("ALTER TABLE candidatos ADD COLUMN monedas_top TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
        # lo que el usuario ha "abierto" el mismo, copiando una posicion de
        # alguien que sigue -- equivalente a la coleccion mis_posiciones de
        # Firestore en la app vieja (boton Abrir en Posiciones/alertas,
        # Cerrar aqui mismo con tu propio pnl a mano, eso alimenta Estadisticas)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mis_posiciones (
                uid TEXT NOT NULL,
                clave TEXT NOT NULL,
                trader_address TEXT NOT NULL,
                tipo TEXT NOT NULL,
                coin TEXT NOT NULL,
                lado TEXT,
                estado TEXT NOT NULL DEFAULT 'abierta',
                fecha_apertura INTEGER NOT NULL,
                fecha_cierre INTEGER,
                pnl REAL,
                PRIMARY KEY (uid, clave)
            )
            """
        )
        try:
            conn.execute("ALTER TABLE mis_posiciones ADD COLUMN monto_invertido REAL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE mis_posiciones ADD COLUMN precio_entrada REAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alertas (
                id TEXT PRIMARY KEY, tipo TEXT, addr TEXT, coin TEXT, lado TEXT,
                tamaño REAL, tamaño_antes REAL, precio REAL, coste REAL, estado TEXT DEFAULT 'pendiente', detectado INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS consenso_visto (
                clave TEXT PRIMARY KEY, n INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                clave TEXT PRIMARY KEY, valor TEXT
            )
            """
        )
        # suscripciones push del navegador (Notification API + Push API) --
        # el contenido del aviso (titulo/cuerpo) sigue siendo el mismo para
        # todos, pero necesitamos saber de QUIEN es cada suscripcion para
        # poder aplicar su whitelist de monedas (ver ajustes) antes de
        # mandarsela -- de ahi el uid, antes no hacia falta
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS push_suscripciones (
                endpoint TEXT PRIMARY KEY,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                uid TEXT,
                creado_en TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        try:
            conn.execute("ALTER TABLE push_suscripciones ADD COLUMN uid TEXT")
        except sqlite3.OperationalError:
            pass
        # preferencias por usuario -- de momento solo la whitelist de
        # monedas que quiere que le notifiquen (lista vacia = todas, sin
        # restriccion; asi una cuenta nueva no se queda muda por defecto)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ajustes (
                uid TEXT PRIMARY KEY,
                monedas_notificar TEXT NOT NULL DEFAULT '[]'
            )
            """
        )


def meta_get(conn: sqlite3.Connection, clave: str) -> str | None:
    fila = conn.execute("SELECT valor FROM meta WHERE clave=?", (clave,)).fetchone()
    return fila["valor"] if fila else None


def meta_set(conn: sqlite3.Connection, clave: str, valor: str) -> None:
    conn.execute("INSERT INTO meta (clave, valor) VALUES (?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (clave, valor))
    conn.commit()


def direcciones_seguidas_por_alguien(conn: sqlite3.Connection) -> set[str]:
    """El equivalente multiusuario de 'candidatos.siguiendo=1' en la app
    vieja: alli habia un unico usuario, aqui el seguimiento vive en
    usuario_sigue (una fila por usuario), asi que lo que importa para decidir
    cuanto esfuerzo de refresco dedicarle a un trader es si lo sigue ALGUIEN,
    no un flag unico en candidatos."""
    return {r["trader_address"] for r in conn.execute("SELECT DISTINCT trader_address FROM usuario_sigue")}
