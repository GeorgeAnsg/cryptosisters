import json
import os

from pywebpush import WebPushException, webpush

from app.db import database as db

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY")
VAPID_CLAIMS = {"sub": os.environ.get("VAPID_CONTACT_EMAIL", "mailto:admin@example.com")}


def enviar_a_todos(titulo, cuerpo):
    """Broadcast a toda suscripcion push guardada -- mismo patron que
    telegram.enviar: silencioso si no esta configurado, nunca rompe el
    ciclo de refresco por un fallo de notificacion."""
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        print("Push no configurado, me salto el aviso:", titulo)
        return
    payload = {"notification": {"title": titulo, "body": cuerpo, "icon": "icons/icon-192x192.png"}}
    with db.conectar() as conn:
        suscripciones = conn.execute("SELECT endpoint, p256dh, auth FROM push_suscripciones").fetchall()
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
            except WebPushException as e:
                # 404/410 = el navegador invalido la suscripcion (desinstalo
                # la app, borro datos...) -- limpiarla para no reintentar
                # para siempre contra un endpoint muerto
                if e.response is not None and e.response.status_code in (404, 410):
                    conn.execute("DELETE FROM push_suscripciones WHERE endpoint=?", (s["endpoint"],))
                else:
                    print("fallo enviando push:", e)
        conn.commit()
