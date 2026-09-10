"""
Divergencia de Open Interest — candidato NUEVO (dato sin usar hasta ahora,
~/Desktop/tr/data/oi_historical_4h.csv, apalancamiento agregado en
derivados de BTC). Dos hipótesis distintas sobre el mismo dato, ambas con
justificación económica real y opuestas entre sí -- se prueban las dos:

- "capitulacion": precio cae Y el Open Interest cae fuerte a la vez ->
  posiciones apalancadas siendo liquidadas/cerradas en masa (desapalancamiento
  forzado). La apuesta: una vez el apalancamiento débil ya salió del mercado,
  queda menos gente que pueda ser forzada a vender más -> terreno para rebote.

- "squeeze": precio cae pero el Open Interest SUBE (o no baja) -> se están
  abriendo cortos nuevos contra la caída (apalancamiento apostando a que siga
  bajando), no gente cerrando largos. Si el precio rebota, esos cortos nuevos
  tienen que cubrirse comprando, amplificando el rebote (short squeeze) --
  mecanismo distinto al de "capitulacion", con predicción de dirección igual
  (largo) pero lectura de mercado contraria (poco apalancamiento vs. mucho
  apalancamiento fresco en contra).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from datos.cargar_oi import cargar_oi, fusionar_oi

VENTANA_CAIDA = 6          # 1 dia en 4h
CAIDA_MINIMA = -0.08
VENTANA_OI = 6
OI_CAIDA_MINIMA = -0.10    # para modo "capitulacion"
OI_SUBE_MINIMA = 0.05      # para modo "squeeze"


def calcular_indicadores(df: pd.DataFrame, ventana_oi: int = VENTANA_OI, ventana_caida: int = VENTANA_CAIDA) -> pd.DataFrame:
    df = fusionar_oi(df, cargar_oi())
    df["caida_reciente"] = df["close"] / df["close"].shift(ventana_caida) - 1
    df["oi_var"] = df["oi"] / df["oi"].shift(ventana_oi) - 1
    return df


def calcular_senales(
    df: pd.DataFrame,
    modo: str = "capitulacion",
    caida_minima: float = CAIDA_MINIMA,
    oi_umbral: float | None = None,
) -> pd.DataFrame:
    df = df.copy()
    cae_precio = (df["caida_reciente"] <= caida_minima).fillna(False)
    if modo == "capitulacion":
        umbral = OI_CAIDA_MINIMA if oi_umbral is None else oi_umbral
        cond_oi = (df["oi_var"] <= umbral).fillna(False)
    elif modo == "squeeze":
        umbral = OI_SUBE_MINIMA if oi_umbral is None else oi_umbral
        cond_oi = (df["oi_var"] >= umbral).fillna(False)
    else:
        raise ValueError(f"modo desconocido: {modo}")
    df["entra_largo"] = cae_precio & cond_oi
    return df


@dataclass
class TradeOI:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, objetivo: float = 0.15, stop: float = -0.10) -> list[TradeOI]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    n = len(df)
    trades: list[TradeOI] = []
    en_posicion = False
    idx_entrada = precio_entrada = None
    for i in range(n):
        if not en_posicion:
            if entra[i]:
                en_posicion = True
                idx_entrada, precio_entrada = i, close[i]
        else:
            retorno = close[i] / precio_entrada - 1
            if retorno >= objetivo or retorno <= stop:
                motivo = "objetivo" if retorno >= objetivo else "stop"
                trades.append(TradeOI(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False
    return trades
