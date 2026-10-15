import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidatos (
    address TEXT PRIMARY KEY,
    categoria TEXT, prioridad INTEGER, antiguedad INTEGER, estilo TEXT, riesgo TEXT, monedas TEXT,
    cuenta REAL, siguiendo INTEGER DEFAULT 0, sigue_trading INTEGER DEFAULT 0, sigue_spot INTEGER DEFAULT 0,
    retorno_pct REAL, profit_factor REAL, puntuacion INTEGER, win_rate REAL, drawdown REAL,
    puntuacion_spot INTEGER, win_rate_spot REAL, retorno_pct_spot REAL, drawdown_spot REAL, profit_factor_spot REAL,
    descubierto_ts INTEGER,
    posicion_actual TEXT DEFAULT '[]',
    holdings_spot TEXT DEFAULT '[]',
    operaciones_recientes TEXT DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS alertas (
    id TEXT PRIMARY KEY, tipo TEXT, addr TEXT, coin TEXT, lado TEXT,
    tamaño REAL, tamaño_antes REAL, precio REAL, coste REAL, estado TEXT DEFAULT 'pendiente', detectado INTEGER
);
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY, valor TEXT
);
CREATE TABLE IF NOT EXISTS mis_posiciones (
    id TEXT PRIMARY KEY, addr TEXT, tipo TEXT, coin TEXT, lado TEXT, estado TEXT DEFAULT 'abierta',
    fecha_apertura INTEGER, fecha_cierre INTEGER, pnl REAL, alerta_id TEXT,
    tamaño REAL, precio_entrada REAL, tamaño_trader_visto REAL
);
CREATE TABLE IF NOT EXISTS notificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT, ts INTEGER, leida INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS consenso_visto (
    clave TEXT PRIMARY KEY, n INTEGER
);
"""

CANDIDATO_JSON_FIELDS = ("posicion_actual", "holdings_spot", "operaciones_recientes")


def conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def iniciar():
    conn = conectar()
    conn.executescript(SCHEMA)
    # migracion para bases ya existentes creadas antes de añadir estas columnas
    columnas_mp = {f[1] for f in conn.execute("PRAGMA table_info(mis_posiciones)")}
    if "tamaño" not in columnas_mp:
        conn.execute("ALTER TABLE mis_posiciones ADD COLUMN tamaño REAL")
    if "precio_entrada" not in columnas_mp:
        conn.execute("ALTER TABLE mis_posiciones ADD COLUMN precio_entrada REAL")
    if "tamaño_trader_visto" not in columnas_mp:
        conn.execute("ALTER TABLE mis_posiciones ADD COLUMN tamaño_trader_visto REAL")
    columnas_c = {f[1] for f in conn.execute("PRAGMA table_info(candidatos)")}
    if "puntuacion_spot" not in columnas_c:
        conn.execute("ALTER TABLE candidatos ADD COLUMN puntuacion_spot INTEGER")
    if "win_rate_spot" not in columnas_c:
        conn.execute("ALTER TABLE candidatos ADD COLUMN win_rate_spot REAL")
    if "descubierto_ts" not in columnas_c:
        conn.execute("ALTER TABLE candidatos ADD COLUMN descubierto_ts INTEGER")
    if "retorno_pct_spot" not in columnas_c:
        conn.execute("ALTER TABLE candidatos ADD COLUMN retorno_pct_spot REAL")
    if "drawdown_spot" not in columnas_c:
        conn.execute("ALTER TABLE candidatos ADD COLUMN drawdown_spot REAL")
    if "profit_factor_spot" not in columnas_c:
        conn.execute("ALTER TABLE candidatos ADD COLUMN profit_factor_spot REAL")
    columnas_a = {f[1] for f in conn.execute("PRAGMA table_info(alertas)")}
    if "tamaño_antes" not in columnas_a:
        conn.execute("ALTER TABLE alertas ADD COLUMN tamaño_antes REAL")
    if "sigue_trading" not in columnas_c:
        # migracion: antes "siguiendo" era un unico interruptor para todo un
        # trader; ahora se sigue por separado su trading y su spot. A quien
        # ya estaba siguiendo se le activa el lado que SI tenia puntuacion
        # (si tenia las dos, se sigue por las dos -- eso es justo el caso de
        # "es bueno en ambas facetas" que no hay que forzar a elegir).
        conn.execute("ALTER TABLE candidatos ADD COLUMN sigue_trading INTEGER DEFAULT 0")
        conn.execute("ALTER TABLE candidatos ADD COLUMN sigue_spot INTEGER DEFAULT 0")
        conn.execute("UPDATE candidatos SET sigue_trading=1 WHERE siguiendo=1 AND puntuacion IS NOT NULL")
        conn.execute("UPDATE candidatos SET sigue_spot=1 WHERE siguiendo=1 AND puntuacion_spot IS NOT NULL")
    conn.commit()
    conn.close()


def meta_get(conn, clave):
    fila = conn.execute("SELECT valor FROM meta WHERE clave=?", (clave,)).fetchone()
    return fila["valor"] if fila else None


def meta_set(conn, clave, valor):
    conn.execute("INSERT INTO meta (clave, valor) VALUES (?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (clave, valor))
    conn.commit()


def crear_notificacion(conn, texto):
    conn.execute("INSERT INTO notificaciones (texto, ts) VALUES (?,?)", (texto, int(time.time() * 1000)))
    conn.commit()


def abrir_posicion(conn, id, addr, tipo, coin, lado, alerta_id, tamaño, precio_entrada, tamaño_trader):
    """Comparte la insercion en mis_posiciones entre el endpoint HTTP
    (main.py) y el bot de Telegram (telegram_bot.py) -- mismo efecto, dos
    puntos de entrada distintos."""
    conn.execute(
        """INSERT INTO mis_posiciones (id, addr, tipo, coin, lado, estado, fecha_apertura, alerta_id,
           tamaño, precio_entrada, tamaño_trader_visto)
           VALUES (?,?,?,?,?,'abierta',?,?,?,?,?)""",
        (id, addr, tipo, coin, lado, int(time.time() * 1000), alerta_id,
         tamaño, precio_entrada, tamaño_trader),
    )
    if alerta_id:
        conn.execute("UPDATE alertas SET estado='hecho' WHERE id=?", (alerta_id,))
    conn.commit()


def fila_a_candidato(row):
    d = dict(row)
    for campo in CANDIDATO_JSON_FIELDS:
        d[campo] = json.loads(d[campo] or "[]")
    d["siguiendo"] = bool(d["siguiendo"])
    d["sigue_trading"] = bool(d["sigue_trading"])
    d["sigue_spot"] = bool(d["sigue_spot"])
    return d
