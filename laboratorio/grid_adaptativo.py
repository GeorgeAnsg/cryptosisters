"""
Grid trading adaptativo — rejilla de niveles de compra/venta cuyo
espaciado se adapta a la volatilidad reciente (ATR), en vez de un
espaciado fijo en %.

Mecanismo: se colocan N niveles de compra por debajo del precio central
y N de venta por encima, separados por k×ATR. Cuando el precio cae hasta
un nivel de compra, se abre una posición ahí; cuando sube un escalón más
(el nivel de venta correspondiente), se cierra, capturando el espaciado
como beneficio. Se gana con la oscilación, no con la dirección.

RIESGO CONOCIDO Y CONTROLADO: en una tendencia bajista fuerte, el precio
puede caer por debajo de TODOS los niveles de compra sin volver a subir
-- el bot seguiría comprando niveles cada vez más bajos sin vender nunca,
acumulando pérdida sin límite. Para evitarlo: STOP DE SEGURIDAD -- si el
precio cae por debajo del nivel de compra más bajo en más de
`stop_bajo_rejilla`, se cierran TODAS las posiciones abiertas de golpe
(pérdida realizada, no se deja correr) y se re-centra la rejilla.

Re-centrado: cada `velas_recentrado` velas, o tras un stop, se recalculan
los niveles alrededor del precio actual usando el ATR reciente --
"adaptativo" significa esto: el tamaño de la rejilla cambia con la
volatilidad del momento, no queda fijo para siempre.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pandas_ta as ta


def calcular_atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def calcular_tendencia_fuerte(df: pd.DataFrame, adx_umbral: float = 25.0) -> pd.Series:
    """True cuando ADX>=umbral y +DI>-DI -- tendencia alcista confirmada
    (misma definicion ya usada y validada en stochrsi_adx.py)."""
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    trending = adx_df["ADX_14"] >= adx_umbral
    return (trending & (adx_df["DMP_14"] > adx_df["DMN_14"])).fillna(False)


def calcular_bear_confirmado(df: pd.DataFrame, velas_regimen: int = 1200, ma_cae_velas: int = 180) -> pd.Series:
    """Misma definicion exacta de 'tendencia bajista de verdad' que ya usa
    Doble techo (doble_techo.py): precio bajo su media de 200 dias Y esa
    media cayendo -- no un bajon pasajero."""
    ma = df["close"].rolling(velas_regimen).mean()
    cae = ma < ma.shift(ma_cae_velas)
    return ((df["close"] < ma) & cae).fillna(False)


@dataclass
class TradeGrid:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str  # "venta_nivel" o "stop_rejilla"
    direccion: str = "largo"
    idx_nivel: int = 0  # 0 = nivel mas cercano al centro, mayor = mas profundo
    peso_fraccion: float = 1.0  # fraccion del tamaño del nivel que cierra este trade (ventas parciales)

    @property
    def retorno_pct(self) -> float:
        if self.direccion == "corto":
            return (self.precio_entrada / self.precio_salida - 1) * 100
        return (self.precio_salida / self.precio_entrada - 1) * 100


@dataclass
class ResultadoGrid:
    trades: list[TradeGrid] = field(default_factory=list)
    n_stops_rejilla: int = 0
    n_recentrados: int = 0


def simular(
    df: pd.DataFrame,
    n_niveles: int = 5,
    k_atr_espaciado: float = 0.5,
    velas_recentrado: int = 180,       # ~30 dias en 4h
    stop_bajo_rejilla: float = 2.0,    # en unidades de "espaciado de rejilla"
    ventana_atr: int = 14,
    interruptor_tendencia: bool = False,
    adx_umbral: float = 25.0,
    k_atr_trailing: float = 3.0,
    espaciado_dinamico: bool = False,
    k_atr_espaciado_tendencia: float = 2.0,
    filtro_bear: bool = False,
    mascara_bloqueo: np.ndarray | None = None,
    senal_refuerzo: np.ndarray | None = None,
    ventana_refuerzo: int = 6,
    mult_espaciado_reforzado: float = 3.0,
    salida_parcial: bool = False,
    fraccion_parcial: float = 0.5,
    k_atr_trailing_parcial: float = 2.0,
    serie_tendencia_externa: np.ndarray | None = None,
    k_atr_objetivo_mult: float = 1.0,
) -> ResultadoGrid:
    """
    interruptor_tendencia: si True, mientras ADX>=adx_umbral y +DI>-DI
    (tendencia alcista fuerte confirmada), las posiciones abiertas NO se
    venden en su nivel fijo -- se les pone un trailing stop de
    k_atr_trailing x ATR en su lugar, dejando correr la ganancia. En
    cuanto la tendencia deja de estar confirmada, vuelven a venderse en
    su nivel de rejilla normal (si siguen abiertas).

    espaciado_dinamico: si True, el espaciado de la rejilla NO es fijo --
    cada vez que se re-centra, se usa `k_atr_espaciado_tendencia` (mas
    ancho) si hay tendencia fuerte en ese momento, o `k_atr_espaciado`
    (mas estrecho) si el mercado esta lateral. Así la rejilla "aguanta
    mas" en tendencia (menos operaciones, pero sobreviven mas tiempo) y
    "aprieta" en lateral (mas operaciones pequeñas, que es donde el grid
    rinde mejor).

    mascara_bloqueo: array booleano (misma longitud que df) -- mientras es
    True, no se abren posiciones NUEVAS en el grid (las que ya estaban
    abiertas se siguen gestionando con normalidad). Pensado para no pisar
    a otros motores (p.ej. Doble suelo/techo) cuando ya tienen algo abierto.

    senal_refuerzo: array booleano -- si una compra del grid ocurre dentro
    de `ventana_refuerzo` velas de una señal externa activa (p.ej. Doble
    suelo confirmado), esa posición concreta se marca como "reforzada":
    en vez de vender en el siguiente escalón normal, su objetivo se
    multiplica por `mult_espaciado_reforzado` -- se le da más margen para
    correr porque hay una confirmación independiente de que el nivel es
    real, no solo ruido de la rejilla.

    salida_parcial: si True, CADA nivel que llega a su precio de venta normal
    no se cierra entero -- se cierra `fraccion_parcial` ahí (beneficio
    asegurado, igual que en doble_suelo_salida_dinamica.py) y el resto se
    deja correr con un trailing de `k_atr_trailing_parcial` x ATR, SIN
    depender de si hay tendencia confirmada (a diferencia de
    interruptor_tendencia, que suelta el 100% solo si ADX confirma).
    Incompatible con interruptor_tendencia (ambos deciden qué hacer al
    llegar al nivel de venta) -- si los dos están activos, manda
    salida_parcial.

    k_atr_objetivo_mult: DESACOPLA la distancia del take-profit del espaciado
    de entrada -- el nivel de venta pasa a ser precio_entrada + espaciado *
    k_atr_objetivo_mult (en vez de precio_entrada + espaciado, mult=1.0).
    El espaciado de ENTRADA y el stop de seguridad no cambian. Validado en
    laboratorio/grid_creativo.py: k_atr_objetivo_mult=1.5 mejora capital,
    Calmar Y drawdown en BTC y ETH simultaneamente, con menos operaciones al
    año (10-sept-2026) -- valor recomendado para uso real, default 1.0 aqui
    solo para no alterar el comportamiento de nadie que ya use esta función.
    """
    close = df["close"].to_numpy()
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    atr = calcular_atr(df, ventana_atr).to_numpy()
    n = len(df)

    if serie_tendencia_externa is not None:
        tendencia_fuerte = serie_tendencia_externa
    else:
        tendencia_fuerte = (
            calcular_tendencia_fuerte(df, adx_umbral).to_numpy()
            if (interruptor_tendencia or espaciado_dinamico) else np.zeros(n, dtype=bool)
        )
    bear_confirmado = (
        calcular_bear_confirmado(df).to_numpy() if filtro_bear else np.zeros(n, dtype=bool)
    )
    maximo_en_tendencia: dict[int, float] = {}

    resultado = ResultadoGrid()

    def nueva_rejilla(i):
        k = k_atr_espaciado_tendencia if (espaciado_dinamico and tendencia_fuerte[i]) else k_atr_espaciado
        espaciado = k * atr[i]
        centro = close[i]
        niveles_compra = [centro - espaciado * kk for kk in range(1, n_niveles + 1)]
        return centro, espaciado, niveles_compra

    idx_ultimo_recentrado = ventana_atr  # esperar a tener ATR valido
    while idx_ultimo_recentrado < n and np.isnan(atr[idx_ultimo_recentrado]):
        idx_ultimo_recentrado += 1
    if idx_ultimo_recentrado >= n:
        return resultado

    centro, espaciado, niveles_compra = nueva_rejilla(idx_ultimo_recentrado)
    # posiciones abiertas: lista de (idx_nivel, idx_entrada, precio_entrada)
    posiciones_abiertas: dict[int, tuple[int, float]] = {}
    niveles_reforzados: set[int] = set()
    parciales_tomados: dict[int, float] = {}  # idx_nivel -> maximo desde la toma parcial

    for i in range(idx_ultimo_recentrado, n):
        # 1. stop de seguridad: precio muy por debajo del nivel de compra mas bajo
        nivel_mas_bajo = min(niveles_compra)
        if close[i] < nivel_mas_bajo - stop_bajo_rejilla * espaciado and posiciones_abiertas:
            for idx_nivel, (idx_ent, precio_ent) in posiciones_abiertas.items():
                peso = 1.0 - fraccion_parcial if idx_nivel in parciales_tomados else 1.0
                resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, close[i], "stop_rejilla", idx_nivel=idx_nivel, peso_fraccion=peso))
            posiciones_abiertas = {}
            niveles_reforzados.clear()
            parciales_tomados.clear()
            resultado.n_stops_rejilla += 1
            centro, espaciado, niveles_compra = nueva_rejilla(i)
            resultado.n_recentrados += 1
            idx_ultimo_recentrado = i
            continue

        # 2. re-centrado periodico, o inmediato si cambia el regimen (solo con
        #    espaciado dinamico -- si no, no tiene sentido recentrar por esto)
        cambio_regimen = espaciado_dinamico and i > 0 and tendencia_fuerte[i] != tendencia_fuerte[i - 1]
        if i - idx_ultimo_recentrado >= velas_recentrado or cambio_regimen:
            centro, espaciado, niveles_compra = nueva_rejilla(i)
            resultado.n_recentrados += 1
            idx_ultimo_recentrado = i

        # 3. rellenar compras: nivel tocado y sin posicion abierta ahi
        #    -- si filtro_bear esta activo y hay bear confirmado, o si la
        #    mascara de bloqueo esta activa, no se abren posiciones NUEVAS
        #    (las que ya estaban abiertas se siguen gestionando).
        bloqueado = (filtro_bear and bear_confirmado[i]) or (mascara_bloqueo is not None and mascara_bloqueo[i])
        if not bloqueado:
            for idx_nivel, nivel in enumerate(niveles_compra):
                if idx_nivel in posiciones_abiertas:
                    continue
                if low[i] <= nivel:
                    posiciones_abiertas[idx_nivel] = (i, nivel)
                    if senal_refuerzo is not None and senal_refuerzo[max(0, i - ventana_refuerzo):i + 1].any():
                        niveles_reforzados.add(idx_nivel)

        # 4. rellenar ventas: precio sube un escalon por encima del nivel de compra
        #    -- salvo que el interruptor de tendencia este activo, en cuyo caso se
        #    deja correr con un trailing stop en vez de vender en el nivel fijo.
        for idx_nivel in list(posiciones_abiertas.keys()):
            idx_ent, precio_ent = posiciones_abiertas[idx_nivel]
            if interruptor_tendencia and tendencia_fuerte[i]:
                maximo_en_tendencia[idx_nivel] = max(maximo_en_tendencia.get(idx_nivel, precio_ent), close[i])
                trailing = maximo_en_tendencia[idx_nivel] - k_atr_trailing * atr[i]
                if close[i] < trailing and close[i] > precio_ent:
                    resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, close[i], "trailing_tendencia", idx_nivel=idx_nivel))
                    del posiciones_abiertas[idx_nivel]
                    maximo_en_tendencia.pop(idx_nivel, None)
                continue
            mult = mult_espaciado_reforzado if idx_nivel in niveles_reforzados else 1.0
            nivel_venta = precio_ent + espaciado * mult * k_atr_objetivo_mult

            if salida_parcial:
                if idx_nivel not in parciales_tomados:
                    if high[i] >= nivel_venta:
                        resultado.trades.append(TradeGrid(
                            idx_ent, i, precio_ent, nivel_venta, "venta_parcial",
                            idx_nivel=idx_nivel, peso_fraccion=fraccion_parcial))
                        parciales_tomados[idx_nivel] = nivel_venta  # maximo desde la toma parcial
                else:
                    parciales_tomados[idx_nivel] = max(parciales_tomados[idx_nivel], close[i])
                    trailing = parciales_tomados[idx_nivel] - k_atr_trailing_parcial * atr[i]
                    if close[i] < trailing:
                        resultado.trades.append(TradeGrid(
                            idx_ent, i, precio_ent, close[i], "trailing_parcial",
                            idx_nivel=idx_nivel, peso_fraccion=1.0 - fraccion_parcial))
                        del posiciones_abiertas[idx_nivel]
                        parciales_tomados.pop(idx_nivel, None)
                        niveles_reforzados.discard(idx_nivel)
                continue

            if high[i] >= nivel_venta:
                motivo = "venta_nivel_reforzado" if mult > 1.0 else "venta_nivel"
                resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, nivel_venta, motivo, idx_nivel=idx_nivel))
                del posiciones_abiertas[idx_nivel]
                maximo_en_tendencia.pop(idx_nivel, None)
                niveles_reforzados.discard(idx_nivel)

    # cerrar lo que quede abierto al final, al ultimo precio (marcar a mercado)
    for idx_nivel, (idx_ent, precio_ent) in posiciones_abiertas.items():
        peso = 1.0 - fraccion_parcial if idx_nivel in parciales_tomados else 1.0
        resultado.trades.append(TradeGrid(idx_ent, n - 1, precio_ent, close[-1], "fin_periodo", idx_nivel=idx_nivel, peso_fraccion=peso))

    return resultado


def evaluar_capital(res: ResultadoGrid, n_niveles: int, decreciente: bool = True) -> tuple[float, float]:
    """Convierte la lista de trades (que pueden solaparse -- varios niveles
    abiertos a la vez) en una curva de capital con `stake = capital/n_niveles`
    por nivel -- sumar los retornos % de cada trade como si cada uno usara el
    capital entero sería un error de contabilidad (varias posiciones
    concurrentes no pueden usar el 100% del capital cada una).

    decreciente: si True, los niveles más profundos (más lejos del centro,
    idx_nivel alto) reciben MENOS capital que los cercanos -- así una racha
    de caída que llena todos los niveles no apuesta a partes iguales en el
    escenario más arriesgado.

    Devuelve (capital_final, caida_maxima_pct), partiendo de 100.
    """
    if decreciente:
        brutos = [n_niveles - k for k in range(n_niveles)]
        suma = sum(brutos)
        pesos = {k: brutos[k] / suma for k in range(n_niveles)}
    else:
        pesos = {k: 1 / n_niveles for k in range(n_niveles)}

    trades_ordenados = sorted(res.trades, key=lambda t: t.idx_salida)
    capital, pico, caida_max = 100.0, 100.0, 0.0
    for t in trades_ordenados:
        peso = pesos.get(t.idx_nivel, 1 / n_niveles) * t.peso_fraccion
        capital += 100.0 * peso * (t.retorno_pct / 100)
        pico = max(pico, capital)
        caida_max = min(caida_max, (capital / pico - 1) * 100)
    return capital, caida_max


def simular_bidireccional(
    df: pd.DataFrame,
    n_niveles: int = 5,
    k_atr_espaciado: float = 0.5,
    k_atr_espaciado_tendencia: float = 2.0,
    velas_recentrado: int = 180,
    stop_bajo_rejilla: float = 2.0,
    ventana_atr: int = 14,
    adx_umbral: float = 25.0,
) -> ResultadoGrid:
    """
    Variante bidireccional, propuesta por el usuario: en vez de solo dejar
    de comprar durante un bear confirmado (filtro_bear en `simular`), el
    grid se INVIERTE a corto -- corta en los niveles de arriba, cubre en
    los de abajo -- usando la misma definicion de bear que ya valida
    Doble techo (precio bajo su 200MA Y esa media cayendo).

    Al cambiar de regimen (largo <-> corto), se cierran todas las
    posiciones abiertas del modo anterior de golpe y se reconstruye la
    rejilla en el modo nuevo.
    """
    close = df["close"].to_numpy()
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    atr = calcular_atr(df, ventana_atr).to_numpy()
    tendencia_fuerte = calcular_tendencia_fuerte(df, adx_umbral).to_numpy()
    bear_confirmado = calcular_bear_confirmado(df).to_numpy()
    n = len(df)

    resultado = ResultadoGrid()

    def modo_de(i):
        return "corto" if bear_confirmado[i] else "largo"

    def nueva_rejilla(i, modo):
        k = k_atr_espaciado_tendencia if tendencia_fuerte[i] else k_atr_espaciado
        espaciado = k * atr[i]
        centro = close[i]
        signo = -1 if modo == "largo" else 1
        niveles = [centro + signo * espaciado * kk for kk in range(1, n_niveles + 1)]
        return centro, espaciado, niveles

    idx0 = ventana_atr
    while idx0 < n and np.isnan(atr[idx0]):
        idx0 += 1
    if idx0 >= n:
        return resultado

    modo = modo_de(idx0)
    centro, espaciado, niveles = nueva_rejilla(idx0, modo)
    posiciones_abiertas: dict[int, tuple[int, float]] = {}
    idx_ultimo_recentrado = idx0

    for i in range(idx0, n):
        modo_actual = modo_de(i)

        # 0. cambio de regimen largo<->corto: cerrar todo y reconstruir
        if modo_actual != modo:
            for idx_nivel, (idx_ent, precio_ent) in posiciones_abiertas.items():
                resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, close[i], "cambio_regimen", modo))
            posiciones_abiertas = {}
            modo = modo_actual
            centro, espaciado, niveles = nueva_rejilla(i, modo)
            resultado.n_recentrados += 1
            idx_ultimo_recentrado = i
            continue

        # 1. stop de seguridad (el nivel mas alejado del precio actual, en contra)
        nivel_extremo = min(niveles) if modo == "largo" else max(niveles)
        precio_contra = close[i] < nivel_extremo - stop_bajo_rejilla * espaciado if modo == "largo" \
            else close[i] > nivel_extremo + stop_bajo_rejilla * espaciado
        if precio_contra and posiciones_abiertas:
            for idx_nivel, (idx_ent, precio_ent) in posiciones_abiertas.items():
                resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, close[i], "stop_rejilla", modo))
            posiciones_abiertas = {}
            resultado.n_stops_rejilla += 1
            centro, espaciado, niveles = nueva_rejilla(i, modo)
            resultado.n_recentrados += 1
            idx_ultimo_recentrado = i
            continue

        # 2. re-centrado periodico
        if i - idx_ultimo_recentrado >= velas_recentrado:
            centro, espaciado, niveles = nueva_rejilla(i, modo)
            resultado.n_recentrados += 1
            idx_ultimo_recentrado = i

        # 3. rellenar entradas
        for idx_nivel, nivel in enumerate(niveles):
            if idx_nivel in posiciones_abiertas:
                continue
            tocado = low[i] <= nivel if modo == "largo" else high[i] >= nivel
            if tocado:
                posiciones_abiertas[idx_nivel] = (i, nivel)

        # 4. rellenar salidas (un escalon a favor)
        for idx_nivel in list(posiciones_abiertas.keys()):
            idx_ent, precio_ent = posiciones_abiertas[idx_nivel]
            if modo == "largo":
                nivel_salida = precio_ent + espaciado
                tocado_salida = high[i] >= nivel_salida
            else:
                nivel_salida = precio_ent - espaciado
                tocado_salida = low[i] <= nivel_salida
            if tocado_salida:
                resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, nivel_salida, "salida_nivel", modo))
                del posiciones_abiertas[idx_nivel]

    for idx_nivel, (idx_ent, precio_ent) in posiciones_abiertas.items():
        resultado.trades.append(TradeGrid(idx_ent, n - 1, precio_ent, close[-1], "fin_periodo", modo))

    return resultado
