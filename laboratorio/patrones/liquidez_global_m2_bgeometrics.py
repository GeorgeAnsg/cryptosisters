"""
Tercera y ultima pieza de la investigacion del "Global Liquidity Index"
(GLI) del youtuber (17-sept-2026), tras `liquidez_global_ciclos.py` (proxy
solo EEUU, sin desfase estable) y `liquidez_global_completa_montecarlo.py`
(proxy Fed+BCE+BOJ construido a mano, mejor correlacion r=0.641 en
+200 dias pero NO significativa frente a un Monte Carlo de 147 desfases
probados, p=0.234).

Diferencia clave de esta version: el usuario mando una captura de la
grafica real del youtuber. En ella, la serie de "Global Liquidity Index"
esta MUY reescalada y desplazada en el tiempo a mano (sin eje propio
visible) -- el usuario confirmo que no tiene mas datos sobre que desfase
exacto usa. Busqueda en la web (17-sept-2026): el "Global Liquidity Index"
que citan estos canales casi siempre es un indicador concreto (originado
por el usuario de TradingView "ingeforberg", 2023, con variantes de otros
autores), construido con M2 (oferta monetaria), NO con balance de bancos
centrales como se probo antes -- y el desfase que la propia comunidad
declara de antemano es bastante consistente: ~70 dias (10 semanas, fuente:
bgeometrics.com, "M2 global de los 21 bancos centrales mas grandes,
desplazado 10 semanas") y ~90 dias (CryptoSlate). Aqui se usa el valor
declarado por la fuente (70 dias) SIN buscar el mejor desfase -- evita
por construccion el problema de "mejor de N intentos" que el Monte Carlo
anterior ya demostro que infla la correlacion aparente por puro azar.

Fuente de datos: API publica y gratuita de bgeometrics.com (JSON servido
sin login, descargado en directo el 17-sept-2026):
- https://charts.bgeometrics.com/files/glm2_in.json  (M2 global, 21 bancos
  centrales, semanal, en USD -- la composicion real que usan estos
  trackers, distinta del Fed+BCE+BOJ que yo aproxime a mano antes).
- https://charts.bgeometrics.com/files/glm2_btc_price.json (precio BTC,
  misma fuente/alineacion).
Limitacion honesta e inevitable: el tier gratuito solo tiene historia desde
2022-09-19 (202 puntos semanales) -- mucho mas corto que los ~8 anios
usados en los intentos anteriores. Aplicando la reserva de validacion
ciega del proyecto (2025+ fuera), solo quedan ~2.3 anios de datos, y el
calculo interanual (365d, necesario para no comparar solo la tendencia de
fondo compartida) dispone de apenas ~1.1 anios de solapamiento util
(n=401 dias). Ninguna prueba aqui puede ser estadisticamente solida con
tan poca muestra -- se reporta de todas formas por ser la comprobacion mas
honesta posible con datos gratuitos (desfase fijado de antemano, no
elegido a la vista del resultado).

Resultado (17-sept-2026):
- Con la reserva del proyecto respetada (2022-09 a 2025-01, unico tramo
  limpio disponible): correlacion interanual con el desfase fijo de
  +70 dias = r=0.007 (practicamente cero). Monte Carlo (2000 repeticiones,
  desfase FIJO, solo se destruye la relacion temporal real desplazando
  circularmente) -- p=0.996, nada significativo.
- Incluyendo 2025-2026 (informativo, fuera de la reserva del proyecto, NO
  usado para ninguna decision): la correlacion se invierte a r=-0.676 y
  aparece "significativa" en el Monte Carlo (p=0.034) -- pero en la
  direccion CONTRARIA a la hipotesis del youtuber (mas liquidez
  anticiparia SUBIDAS, no bajadas). Esto es coherente con analisis
  externos que documentan que la relacion M2-BTC se rompio en el Q4 de
  2025 (M2 global siguio subiendo mientras BTC caia) -- no es evidencia a
  favor de la idea, es la misma idea fallando de otra manera.

Cuarta prueba, añadida a peticion del usuario ("busca maximos y minimos, y
mira si coinciden con los de Bitcoin en funcion de su separacion"): repetir
el emparejamiento de techos/suelos de CICLO (mismo metodo que
`liquidez_global_ciclos.py`/`liquidez_global_completa_montecarlo.py`,
argrelextrema no causal) pero sobre el dato REAL de M2 global de
bgeometrics en vez del proxy casero -- y probando varias ventanas de
deteccion (60/90/120/180 dias) en vez de una sola, porque con solo 4 años
de historia una ventana de 180 dias por si sola deja muy pocos puntos.

Resultado: igual que con el proxy casero, EL DESFASE NO ES ESTABLE. Segun
la ventana usada y el techo/suelo concreto, las diferencias van de +7 a
+310 dias (y tambien negativas, -86 a -187, BTC primero) -- algunos pares
sueltos caen cerca del rango "oficial" (70-90 dias) pero la mayoria no, sin
ningun patron consistente al mirar TODOS los pares detectados (no solo los
que a simple vista encajan). Mismo patron que las pruebas 1 y 2: mirando
solo 2-3 techos/suelos es facil fijarse en los que casualmente coinciden.

Veredicto: descartado tambien con el dato y el desfase REALES que declara
la propia comunidad del indicador (no una aproximacion propia ni un
desfase buscado a posteriori), Y con el metodo de emparejamiento de
ciclo que pidio el usuario explicitamente. Con datos gratuitos y las
cuatro formulaciones razonables probadas (proxy EEUU, proxy Fed+BCE+BOJ
con busqueda de mejor desfase, Global M2 real con desfase fijo declarado,
Global M2 real con emparejamiento de techos/suelos), ninguna sostiene la
impresion visual de la grafica del youtuber. La impresion visual se explica
mejor por el reescalado/desplazamiento manual sin eje propio (confirmado
por el propio usuario al describir la captura) que por una relacion
sistematica explotable. Ver `registro/intentos.jsonl`
(completa `liquidez_global_ciclos_gli`).
"""
from __future__ import annotations

import json
import urllib.request

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

ORDENES_CICLO_DIAS = [60, 90, 120, 180]  # varias ventanas, no una sola -- 4 años de historia da pocos puntos con 180

CORTE_RESERVA = pd.Timestamp("2025-01-01", tz="UTC")
LAG_DIAS = 70  # 10 semanas, declarado por bgeometrics.com, no buscado
N_MONTECARLO = 2000
SEMILLA = 20260917


def cargar_json(nombre: str) -> pd.Series:
    data = json.loads(urllib.request.urlopen(f"https://charts.bgeometrics.com/files/{nombre}").read())
    idx = pd.to_datetime([d[0] for d in data], unit="ms", utc=True)
    val = [d[1] for d in data]
    return pd.Series(val, index=idx).sort_index()


def zscore(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / s.std()


def picos_valles(serie: pd.Series, orden: int):
    arr = serie.to_numpy()
    idx_max = [i for i in argrelextrema(arr, np.greater_equal, order=orden)[0] if 0 < i < len(arr) - 1]
    idx_min = [i for i in argrelextrema(arr, np.less_equal, order=orden)[0] if 0 < i < len(arr) - 1]
    return sorted(idx_max), sorted(idx_min)


def emparejar_ciclo(fechas, m2_suave, btc_suave, etiqueta):
    print(f"\n{'='*70}\n{etiqueta} -- emparejamiento de techos/suelos de ciclo\n{'='*70}")
    for orden in ORDENES_CICLO_DIAS:
        m2_max, m2_min = picos_valles(m2_suave, orden)
        btc_max, btc_min = picos_valles(btc_suave, orden)
        print(f"\n-- orden={orden} dias -- techos M2={len(m2_max)} techos BTC={len(btc_max)} "
              f"suelos M2={len(m2_min)} suelos BTC={len(btc_min)}")
        for bi in btc_max:
            if m2_max:
                cercano = min(m2_max, key=lambda mi: abs(mi - bi))
                print(f"  techo BTC {fechas[bi].date()} <-> techo M2 {fechas[cercano].date()} ({(bi-cercano):+d}d)")
        for bi in btc_min:
            if m2_min:
                cercano = min(m2_min, key=lambda mi: abs(mi - bi))
                print(f"  suelo BTC {fechas[bi].date()} <-> suelo M2 {fechas[cercano].date()} ({(bi-cercano):+d}d)")


if __name__ == "__main__":
    m2 = cargar_json("glm2_in.json")
    btc = cargar_json("glm2_btc_price.json")

    desde = max(m2.index.min(), btc.index.min())
    hasta = min(m2.index.max(), btc.index.max())
    idx_diario = pd.date_range(desde, hasta, freq="D", tz="UTC")
    m2_d = m2.reindex(idx_diario, method="ffill")
    btc_d = btc.reindex(idx_diario, method="ffill")

    print(f"Rango completo disponible (fuente gratuita): {desde.date()} a {hasta.date()}")

    for etiqueta, hasta_corte in [
        ("completo (incluye 2025+, informativo, NO usado para decidir)", hasta),
        ("con reserva del proyecto (2025+ excluido)", min(hasta, CORTE_RESERVA)),
    ]:
        m2_c = m2_d[m2_d.index <= hasta_corte]
        btc_c = btc_d[btc_d.index <= hasta_corte]
        n = len(btc_c)
        print(f"\n{'='*70}\n{etiqueta} -- {m2_c.index[0].date()} a {m2_c.index[-1].date()} ({n} dias)\n{'='*70}")

        m2_shift = m2_c.shift(LAG_DIAS)
        validos = m2_shift.notna() & btc_c.notna()
        r_nivel = np.corrcoef(btc_c[validos], m2_shift[validos])[0, 1]
        print(f"Correlacion de NIVELES crudos (lag fijo +{LAG_DIAS}d): r={r_nivel:.3f}  (n={validos.sum()})")
        print("  (aviso: dos series con tendencia de fondo compartida casi siempre dan r alto aqui, poco informativo)")

        btc_yoy = btc_c.pct_change(365) * 100
        m2_yoy = m2_c.pct_change(365) * 100
        m2_yoy_shift = m2_yoy.shift(LAG_DIAS)
        validos_yoy = btc_yoy.notna() & m2_yoy_shift.notna()
        n_yoy = int(validos_yoy.sum())
        if n_yoy < 30:
            print(f"YoY: insuficientes puntos tras quitar tendencia y aplicar lag (n={n_yoy}) -- no se calcula")
            continue
        r_yoy = np.corrcoef(btc_yoy[validos_yoy], m2_yoy_shift[validos_yoy])[0, 1]
        print(f"Correlacion INTERANUAL (365d, lag fijo +{LAG_DIAS}d): r={r_yoy:.3f}  "
              f"(n={n_yoy} dias, ~{n_yoy/365:.1f} anios de solapamiento util)")

        a = btc_yoy[validos_yoy].to_numpy()
        b = m2_yoy_shift[validos_yoy].to_numpy()
        rng = np.random.default_rng(SEMILLA)
        nulos = np.empty(N_MONTECARLO)
        for i in range(N_MONTECARLO):
            despl = rng.integers(1, len(b) - 1)
            b_shift = np.roll(b, despl)
            nulos[i] = abs(np.corrcoef(a, b_shift)[0, 1])
        p = (nulos >= abs(r_yoy)).mean()
        print(f"Monte Carlo (lag fijo, {N_MONTECARLO} reps) -- nula: mediana={np.median(nulos):.3f} "
              f"p90={np.percentile(nulos,90):.3f} p99={np.percentile(nulos,99):.3f}")
        print(f"p-valor: {p:.3f}  ({'NO significativo' if p > 0.05 else 'significativo'})")

        m2_suave = zscore(m2_c).rolling(30, min_periods=15).mean().bfill()
        btc_suave = np.log(btc_c).rolling(30, min_periods=15).mean().bfill()
        emparejar_ciclo(m2_c.index, m2_suave, btc_suave, etiqueta)
