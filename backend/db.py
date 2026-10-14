import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidatos (
    address TEXT PRIMARY KEY,
    categoria TEXT, prioridad INTEGER, antiguedad INTEGER, estilo TEXT, riesgo TEXT, monedas TEXT,
    cuenta REAL, siguiendo INTEGER DEFAULT 0,
    retorno_pct REAL, profit_factor REAL, puntuacion INTEGER, win_rate REAL, drawdown REAL,
    posicion_actual TEXT DEFAULT '[]',
    holdings_spot TEXT DEFAULT '[]',
    operaciones_recientes TEXT DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS alertas (
    id TEXT PRIMARY KEY, tipo TEXT, addr TEXT, coin TEXT, lado TEXT,
    tamaño REAL, precio REAL, coste REAL, estado TEXT DEFAULT 'pendiente', detectado INTEGER
);
CREATE TABLE IF NOT EXISTS mis_posiciones (
    id TEXT PRIMARY KEY, addr TEXT, tipo TEXT, coin TEXT, lado TEXT, estado TEXT DEFAULT 'abierta',
    fecha_apertura INTEGER, fecha_cierre INTEGER, pnl REAL, alerta_id TEXT
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
    conn.commit()
    conn.close()


def fila_a_candidato(row):
    d = dict(row)
    for campo in CANDIDATO_JSON_FIELDS:
        d[campo] = json.loads(d[campo] or "[]")
    d["siguiendo"] = bool(d["siguiendo"])
    return d
