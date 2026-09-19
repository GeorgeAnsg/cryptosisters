"""
Unico punto de carga de datos para cribados de laboratorio -- hace cumplir
en CODIGO la regla de `laboratorio/README.md` ("con datos de la particion
de Desarrollo solamente"), en vez de confiar en que cada script se acuerde.

Motivo (ver tests/README.md, puerta de "la disciplina sola no basta"): un
cribado en laboratorio/patrones/validacion_confirmacion.py cargo datos
hasta 2026-08-31 sin querer, tocando Validacion (2025) y Reserva
(2026-hoy) sin registrar el acceso -- ver la divulgacion retroactiva en
registro/accesos_validacion_reserva.jsonl. Este modulo hace que ese fallo
concreto ya no pueda repetirse por accidente: por defecto SIEMPRE recorta
a Desarrollo, y solo se puede ver mas alla pidiendolo explicitamente, con
motivo, y quedando registrado automaticamente.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import pandas as pd

from datos.cargar import cargar_ohlcv as _cargar_ohlcv_crudo

CORTE_VALIDACION = pd.Timestamp("2025-01-01", tz="UTC")  # Desarrollo termina aqui
CORTE_RESERVA = pd.Timestamp("2026-01-01", tz="UTC")      # Validacion termina aqui

_RUTA_REGISTRO = Path(__file__).resolve().parent.parent / "registro" / "accesos_validacion_reserva.jsonl"


def _registrar_acceso(par: str, tf: str, particion: str, estrategia: str, motivo: str) -> None:
    entrada = {
        "tipo": "acceso_explicito",
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "par": par,
        "timeframe": tf,
        "particion": particion,
        "estrategia": estrategia,
        "motivo": motivo,
    }
    with open(_RUTA_REGISTRO, "a") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")


def cargar_ohlcv_lab(
    par: str,
    tf: str,
    estrategia: str,
    acceso_validacion: bool = False,
    acceso_reserva: bool = False,
    motivo: str = "",
    **kwargs,
) -> pd.DataFrame:
    """Carga OHLCV para un cribado de laboratorio.

    Por defecto, recorta a Desarrollo (fecha < 2025-01-01) -- sin limite de
    accesos, como dice `laboratorio/README.md`.

    Para mirar 2025 (`acceso_validacion=True`) o 2026-hoy
    (`acceso_reserva=True`) hace falta pasar tambien `motivo`, y la llamada
    queda registrada automaticamente en
    `registro/accesos_validacion_reserva.jsonl`. `estrategia` (p.ej.
    "doble_suelo_flexible") identifica quien pidio el acceso.
    """
    df = _cargar_ohlcv_crudo(par, tf, **kwargs)

    if acceso_reserva:
        if not motivo:
            raise ValueError("acceso_reserva=True requiere `motivo` explicito.")
        _registrar_acceso(par, tf, "Reserva (2026-hoy)", estrategia, motivo)
        return df

    if acceso_validacion:
        if not motivo:
            raise ValueError("acceso_validacion=True requiere `motivo` explicito.")
        _registrar_acceso(par, tf, "Validacion (2025)", estrategia, motivo)
        return df[df["open_time"] < CORTE_RESERVA].reset_index(drop=True)

    return df[df["open_time"] < CORTE_VALIDACION].reset_index(drop=True)
