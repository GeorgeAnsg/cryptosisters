"""
Puerta 4 -- Presupuesto de intentos (DSR). Ver tests/README.md y
registro/NOTA-presupuesto.md.

Cuenta intentos DISTINTOS en registro/intentos.jsonl -- por nombre, tal
como manda la regla de contabilidad de registro/README.md ("corregir un
bug en un intento ya registrado actualiza ese mismo registro y NO cuenta
como intento nuevo. Probar una variante genuinamente distinta SI cuenta").
"""
from __future__ import annotations

import json
from pathlib import Path

PRESUPUESTO_TOTAL = 420  # con 9 años de datos, ver docs/00-PLAN-MAESTRO.md

_RUTA_INTENTOS = Path(__file__).resolve().parent.parent / "registro" / "intentos.jsonl"


def contar_intentos() -> dict:
    if not _RUTA_INTENTOS.exists():
        return {"n_lineas": 0, "n_distintos": 0, "nombres": []}
    nombres = []
    with open(_RUTA_INTENTOS) as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            entrada = json.loads(linea)
            nombre = entrada.get("nombre")
            if nombre:
                nombres.append(nombre)
    return {"n_lineas": len(nombres), "n_distintos": len(set(nombres)), "nombres": sorted(set(nombres))}


def verificar_presupuesto(umbral_aviso: float = 0.8) -> dict:
    estado = contar_intentos()
    n = estado["n_distintos"]
    fraccion = n / PRESUPUESTO_TOTAL
    return {
        "n_intentos_distintos": n,
        "n_lineas_registradas": estado["n_lineas"],
        "presupuesto_total": PRESUPUESTO_TOTAL,
        "presupuesto_restante": PRESUPUESTO_TOTAL - n,
        "fraccion_gastada": round(fraccion, 3),
        "aviso": fraccion >= umbral_aviso,
        "ok": fraccion < 1.0,
    }
