import json
import os

from pywebpush import WebPushException, webpush

from app.db import database as db
from app.services.hyperliquid import etiqueta_moneda

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY")
VAPID_CLAIMS = {"sub": os.environ.get("VAPID_CONTACT_EMAIL", "mailto:admin@example.com")}


def enviar_a_todos(titulo, cuerpo, coin=None):
    """Broadcast a toda suscripcion push guardada -- mismo patron que
    telegram.enviar: silencioso si no esta configurado (desde el ciclo de
    refresco), nunca rompe nada por un fallo de notificacion. Devuelve un
    resumen (en vez de None) para que /push/probar pueda decirle al usuario
    POR QUE no le ha llegado nada, en vez de fallar en silencio.

    coin=None (avisos sin moneda concreta, p.ej. la prueba manual) nunca se
    filtra; si se da, cada suscripcion se salta segun la whitelist de SU
    uid en 'ajustes' (lista vacia = sin restriccion, igual que el frontend)."""
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        print("Push no configurado, me salto el aviso:", titulo)
        return {"configurado": False, "enviados": 0, "fallidos": 0, "suscripciones": 0}
    payload = {"notification": {"title": titulo, "body": cuerpo, "icon": "icons/icon-192x192.png"}}
    enviados = 0
    fallidos = 0
    with db.conectar() as conn:
        suscripciones = conn.execute("SELECT endpoint, p256dh, auth, uid FROM push_suscripciones").fetchall()
        if coin is not None:
            etiqueta = etiqueta_moneda(coin)
            whitelists = {
                fila["uid"]: json.loads(fila["monedas_notificar"])
                for fila in conn.execute("SELECT uid, monedas_notificar FROM ajustes")
            }
            suscripciones = [
                s for s in suscripciones
                if not whitelists.get(s["uid"]) or etiqueta in whitelists[s["uid"]]
            ]
        for s in suscripciones:
            try:
                webpush(
                    subscription_info={
                        "endpoint": s["endpoint"],
                        "keys": {"p256dh": s["p256dh"], "auth": s["auth"]},
                    },
                    data=json.dumps(payload),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=dict(VAPID_CLAIMS),
                )
                enviados += 1
            except WebPushException as e:
                fallidos += 1
                # 404/410 = el navegador invalido la suscripcion (desinstalo
                # la app, borro datos...) -- limpiarla para no reintentar
                # para siempre contra un endpoint muerto
                if e.response is not None and e.response.status_code in (404, 410):
                    conn.execute("DELETE FROM push_suscripciones WHERE endpoint=?", (s["endpoint"],))
                else:
                    print("fallo enviando push:", e)
        conn.commit()
    return {"configurado": True, "enviados": enviados, "fallidos": fallidos, "suscripciones": len(suscripciones)}
