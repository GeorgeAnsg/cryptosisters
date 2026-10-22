"""Indice FRELDI(X) -- trae el snapshot ya calculado del endpoint publico de
Multivac (otra app del mismo usuario, ver /Desktop/new/Trading/freldi), en
vez de traer toda esa logica a Corvus. Se pide como mucho una vez al dia
(ver ciclo_freldi en refresher.py) y se guarda en 'meta' -- la UI siempre
lee lo cacheado, nunca llama a Multivac en caliente."""
import json
import time
import urllib.request

FRELDI_URL = "http://tu0mtnondcwqlyno8q2ewx5p.46.224.182.44.sslip.io/api/finance/freldi"
INTERVALO_SEGUNDOS = 24 * 60 * 60


def obtener_freldi():
    with urllib.request.urlopen(FRELDI_URL, timeout=20) as r:
        body = json.loads(r.read())
    if not body.get("success") or not body.get("data"):
        raise ValueError("respuesta de Multivac sin 'success'/'data'")
    return body["data"]


def refrescar_cache(conn) -> None:
    from app.db import database as db

    datos = obtener_freldi()
    db.meta_set(conn, "freldi_snapshot", json.dumps(datos, ensure_ascii=False))
    db.meta_set(conn, "freldi_actualizado", str(time.time()))
    conn.commit()
