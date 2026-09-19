"""18-sept-2026: categorizacion semantica de titulares de noticias de alto
impacto (ver descargar_noticias_importantes.py) para el mecanismo de
salida informado por noticias -- ver memoria persistente
project_corvus4_mecanismo_noticias.

Reagrupa HIGH_IMPACT_KEYWORDS (v6/core/bot_sentiment.py, proyecto
/Users/jorgeansotegui/Desktop/tr) en 6 categorias semanticas. Una misma
noticia puede caer en varias categorias a la vez (ej. "sec bans crypto
after ftx collapse" es regulatorio Y colapso_quiebra) -- no es
mutuamente excluyente a proposito, porque el impacto real tampoco lo es.

Primer uso: se persiste este fichero PORQUE la version anterior de esta
categorizacion (sesion previa a esta) se quedo solo en la conversacion y
nunca se guardo en el repo -- ver leccion 7 de la skill
deteccion-flexible-patrones (no dejar el codigo de metodologia "al
vuelo").

18-sept-2026: corregido un fallo real de falsos positivos -- el usuario
sospechaba que la categorizacion no pesaba/interpretaba bien las noticias,
y al comprobarlo aparecieron casos concretos: "hack" (hackeo_seguridad)
coincidia con la palabra "hackathon" (8 de 141 noticias graves en
2021-2022 eran sobre hackathons, no hackeos), y "war" (geopolitico)
coincidia con "warning", "toward", "hardware", "software", "award" (52
falsos positivos solo en esa muestra). El fallo era buscar la palabra
como fragmento de texto en vez de exigir que fuera una palabra completa.

18-sept-2026, SEGUNDA vuelta (el primer arreglo se paso de frenada): exigir
la palabra EXACTA (limite de palabra a ambos lados, sin permitir ningun
sufijo) rompio 35 coincidencias reales, varias de eventos importantes de
verdad -- "hacked" (Axie Infinity Ronin, $600M), "hacked" (Wormhole,
$320M), "collapses" (Terra) ya no coincidian con "hack"/"collapse" en su
forma exacta sin conjugar. La palabra exacta bloqueaba "hackathon" pero
tambien "hackeado". Solucion: permitir un conjunto pequeño de sufijos
verbales normales (-s/-es/-ed/-ing/-er/-ers) DESPUES de la raiz, pero
seguir exigiendo limite de palabra al principio (eso es lo que de verdad
bloquea "toward"/"hardware"/"software"/"award", porque en esas palabras
"war" no esta al principio de un token) y que el sufijo tiene que ser
exactamente uno de esos, no cualquier cosa (eso es lo que sigue bloqueando
"hackathon" -- "athon" no es un sufijo verbal valido). Confirmado con
Terra/Luna, FTX, Axie Ronin y Wormhole que la deteccion real no se rompio,
y que "hackathon"/"warning"/"toward" siguen sin colar.

18-sept-2026, TERCERA vuelta (revision completa, una a una, pedida por el
usuario): "ftx"/"celsius"/"tether" sueltos en colapso_quiebra son un
nombre de entidad, no una palabra de crisis -- coinciden con CUALQUIER
noticia rutinaria que las mencione (partnerships, listados de precio,
patrocinios), no solo con el colapso real. Medido en ETH 2021-2023: 87 de
134 noticias "colapso_quiebra" (65%) NO tenian ninguna palabra de crisis
al lado, solo el nombre. Probado quitar el nombre suelto del todo: la
señal de FTX se debilita mucho (se queda plana en ~80 en vez de picos
claros) porque gran parte de la cobertura real de FTX usa palabras como
"crisis"/"fraud"/"fiasco" que no estaban en la lista de palabras de
colapso_quiebra (bankruptcy/insolvent/collapse/frozen/halted withdrawals).
Solucion intermedia: el nombre de la entidad SOLO cuenta si aparece EN EL
MISMO titular junto con una palabra de crisis (lista ampliada, ver
PALABRAS_CRISIS_AMPLIA). Con esto: colapso_quiebra baja de 134 a 47
(65% menos ruido) y Terra/Luna y FTX salen MEJOR que antes (98-99.9% en
las fechas correctas, en vez de diluido entre ruido de fondo).

18-sept-2026, CUARTA vuelta (correccion de sesgo retrospectivo, señalada
por el usuario): la solucion de la tercera vuelta ("ftx"/"celsius"/
"tether" como nombres reconocidos) solo funciona porque YA SABEMOS, en
retrospectiva, que esas 3 entidades acabaron quebrando -- el bot en vivo
nunca tiene esa ventaja, no puede "saber de antemano" que nombre vigilar.
Meter esos 3 nombres a mano es Filtrar con informacion del futuro dentro
de la propia prueba de validacion, no una simplificacion razonable.
Solucion: quitar los 3 nombres de entidad y la logica de co-ocurrencia
por completo, y en su lugar anadir las palabras de PALABRAS_CRISIS_AMPLIA
directamente como keywords genericas de colapso_quiebra (con limite de
palabra + sufijos verbales, igual que el resto) -- salvo "crisis", que se
descarta por separado: medido en ETH 2021-2023, "crisis" sola disparaba
26 falsos positivos genericos sin relacion con una quiebra real (crisis
energetica, crisis bancaria macro, "gas fee crisis", "Curve Crisis" sobre
gestion de riesgo, no sobre un colapso) -- ademas "crisis" ya esta en
geopolitico, no hace falta duplicarla aqui. Tambien se encontro y
corrigio un bug aparte: "bankrupt" (adjetivo/verbo, ej. "Celsius is
bankrupt") es una palabra DISTINTA de "bankruptcy" (sustantivo), no una
conjugacion con sufijo -- se anadio como keyword propia. Resultado final
100% generico (sin ningun nombre de entidad, sin "crisis"): mismo total
de aciertos (47, igual que la version con nombres), Terra/Luna
practicamente igual (84.4 vs 84.9 antes) y FTX practicamente igual (99.6
vs 99.9 antes) -- la diferencia de contenido es una MEJORA: pierde 8
titulares que eran solo comentario de mercado posterior a la crisis FTX
("Solana se recupera de la crisis FTX") y gana 8 titulares de
hackeos/fraudes reales (Nomad bridge $190M drenado, demanda SEC por
fraude) que antes solo colaban de rebote via la palabra "crisis".

18-sept-2026, QUINTA vuelta (auditoria completa pedida por el usuario de
las 6 categorias, buscando cualquier nombre "quemado" -- ej. "que sepa que
es Iran en vez de buscar guerra"): revisadas macro/geopolitico/
regulatorio/hackeo_seguridad/colapso_quiebra/crash_mercado, ninguna tenia
nombres de pais/persona/empresa -- solo "sec"/"cftc"/"congress"/"senate"
en regulatorio, que son nombres de INSTITUCIONES genericas (como "federal
reserve" en macro), no de un evento concreto conocido de antemano, asi que
no es el mismo problema que ftx/celsius/tether. Se encontro un hueco real
probando el propio ejemplo del usuario: "Iran launches missile strike on
Israel" NO se detectaba como geopolitico -- la categoria tenia "airstrike"
(una palabra) pero no "missile"/"strike"/"attack" sueltos. Probado anadir
"attack": DESCARTADO, 13 de 13 titulares con "attack" en ETH 2021-2023 son
sobre hackeos/exploits ("flash loan attack", "Sybil attack"), cero sobre
guerra real -- habria contaminado geopolitico con jerga de seguridad
cripto. "strike" tambien descartado (jerga de "strike price" en opciones
financieras, alto riesgo de falso positivo). "missile" y "troops" SI
anadidos: cero apariciones en 3 años de dataset real (no contaminan nada
existente) y son vocabulario militar genuinamente generico, verificado con
el ejemplo real de Iran/Israel Y con nombres de pais inventados
(Zalvaria/Kordania) -- ambos detectados igual, confirmando que no depende
de saber que pais es.

18-sept-2026, SEXTA vuelta (falsos NEGATIVOS, no falsos positivos --
señalado por el usuario: preocupacion de que las listas, hechas mirando
solo 2021-2023, no cubran vocabulario nuevo que aparecio despues). Se
busco en el propio dataset 2021-2023 jerga real de colapso/hackeo que las
listas actuales NO cubrian: "depeg"/"depegged" (una stablecoin pierde su
paridad con el dolar -- paso de verdad con USDC durante el colapso de
Silicon Valley Bank, marzo 2023) y "bank run" no estaban en ninguna
categoria, a pesar de ser eventos claramente graves. Añadidos a
colapso_quiebra. Este tipo de comprobacion (buscar eventos conocidos que
DEBERIAN estar categorizados y no lo estan) hay que repetirla cada vez que
lleguen datos de un periodo nuevo (2024, 2025...) -- el vocabulario de
prensa cripto evoluciona, y una lista fijada en 2021-2023 no cubre
automaticamente terminologia que se populariza despues.

18-sept-2026, SEPTIMA vuelta (auditoria de la segunda fuente, Tree News --
ver project_corvus4_mecanismo_noticias): al revisar por que Tree News
(estilo teletipo Bloomberg/Reuters, mas seco que Cointelegraph) solo caia
en categoria el 4% de sus mensajes, aparecio una laguna real de
vocabulario de CONSECUENCIA LEGAL que ninguna categoria cubria: "Binance
founder Changpeng Zhao agrees to plead guilty", "SBF enters not guilty
plea", condenas y sentencias de fraude cripto -- ninguna tenia
"bankruptcy/fraud/scandal" literal pero son la misma familia de eventos
graves (colapso_quiebra). Añadidas "guilty"/"convicted"/"indicted"/
"sentenced" a colapso_quiebra, verificadas contra los 34.168 titulares de
Cointelegraph+Tree News combinados (71-103 aciertos genuinos por palabra,
todos casos reales de fraude/condena cripto). Descartada "plea" sola: con
limite de palabra + sufijos verbales coincidia tambien con "please"
("plea"+"se"), el mismo tipo de fragmento que las vueltas 1-2 ya
corrigieron. La auditoria tambien confirmo que la mayoria del 96% restante
de Tree News SIN categoria es correctamente ruido (anuncios de listado de
exchanges reenviados via MadNews.io: "Binance Will List X", "Huobi Global
Will List Y") -- el filtro de "interesante" los excluye bien, no es un
fallo."""
from __future__ import annotations

import re

CATEGORIAS: dict[str, list[str]] = {
    "macro": [
        "federal reserve", "fed rate", "fomc", "rate hike", "rate cut",
        "inflation", "cpi", "gdp", "recession", "quantitative easing", "quantitative tightening",
        "nonfarm payroll", "non-farm payroll", "jobs report", "unemployment rate",
        "consumer price", "producer price", "pce", "core inflation",
        "retail sales", "pmi", "ism manufacturing", "jobless claims",
        "earnings report", "trade deficit", "trade surplus",
    ],
    "geopolitico": [
        "war", "invasion", "military", "sanction", "conflict", "airstrike",
        "nuclear", "escalat", "ceasefire", "crisis", "coup", "missile", "troops",
    ],
    "regulatorio": [
        "sec ", "cftc", "ban crypto", "banned crypto", "illegal crypto", "crackdown",
        "etf approved", "etf rejected", "etf denied", "spot etf", "spot bitcoin etf",
        "congress", "senate", "legislation", "executive order",
        "strategic reserve", "bitcoin reserve", "national reserve",
    ],
    "hackeo_seguridad": [
        "hack", "exploit", "breach", "stolen",
    ],
    "colapso_quiebra": [
        "bankruptcy", "bankrupt", "insolvent", "collapse", "frozen", "halted withdrawals",
        "fraud", "drain", "fallout", "contagion", "fiasco", "debacle", "scandal",
        "depeg", "depegged", "depegging", "bank run",
        "guilty", "convicted", "indicted", "sentenced",
    ],
    # 18-sept-2026, OCTAVA vuelta: se quito "government" (bare) de regulatorio
    # y "interest rate" (bare) de macro -- ver docstring del modulo.
    "crash_mercado": [
        "flash crash", "market crash", "circuit breaker", "liquidation cascade",
    ],
}


SUFIJOS_VERBALES = ("e", "es", "ed", "ing", "er", "ers", "s")


RE_RUIDO_ESTRUCTURAL = re.compile(
    r"price analysis \d"
    r"|\[opinion\]"
    r"|(❤️ ?—|👍 ?—|👍 for|❤️ for|react with|share in the comments)"
    r"|\(ad\)|#sponsored|acceleration\)"
    r"|^\W*\d+ (reasons|tips|things|wildest|lowlights|mistakes|lessons)"
    r"|, says [A-Z]|, according to [A-Z]",
    re.IGNORECASE | re.MULTILINE,
)


def es_ruido_estructural(titulo: str) -> bool:
    """18-sept-2026: el usuario pidio leer a mano ~500 titulares reales (los
    que caen cerca de techos/suelos de verdad del precio de ETH 2021-2024,
    ver project_corvus4_mecanismo_noticias) y juzgar el o cada uno como
    interesante/ruido con criterio propio, para sacar una regla de verdad en
    vez de seguir iterando keyword a keyword.

    Resultado del juicio manual (509 titulares): 237 eran ruido -- pero de
    esos 237, 231 (97.5%) YA estaban marcados "interesante" por el sistema de
    categorias. El problema real no es que se pierdan noticias importantes
    (0 falsos negativos entre las que juzgue muy_mala/muy_buena) -- es que se
    ahogan en ruido (un titular cada dos, en esta muestra, no aporta nada).

    Se probaron patrones ESTRUCTURALES (no de contenido) contra ese juicio
    manual como referencia: resumenes multi-tema (digest/podcast/roundup),
    encuestas de reaccion, contenido patrocinado, columnas recurrentes de
    "Price analysis", opiniones atribuidas a una persona ("X says Y").
    Version ORIGINAL (18-sept-2026, primera vuelta) incluia tambien los
    posts tipo digest/podcast ("Rise'n'Crypto", "Catch up on the news...",
    "here are the stories you missed") -- cubria el 32% del ruido con un 7%
    de coste. SEGUNDA vuelta (mismo dia, ampliando el juicio manual a los
    406 titulares COMPLETOS de 2024, no solo los de cerca de extremos): ese
    7% de coste no era ruido al azar -- 9 de los eventos mas importantes del
    año (sentencia de SBF a 25 años, victoria electoral de Trump, dimision
    de Gensler, la quiebra en cascada de agosto-2024...) SOLO estaban
    cubiertos a traves de un envoltorio de podcast/digest, sin ningun
    titular plano alternativo ese mismo dia. Quitar el patron digest/podcast
    arregla esto (0 perdidas de señal fuerte en 816 titulares juzgados a
    mano) a cambio de bajar la limpieza de ruido real del 32% al 10% --
    aceptado explicitamente: es preferible un mecanismo con mas ruido que
    uno que pueda quedarse ciego el dia que quiebra un exchange o gana unas
    elecciones. El 90% de ruido restante (comentario/especulacion sin marca
    estructural, ej. "How can Bitcoin survive the banking crisis?") no tiene
    ninguna señal lexica fiable que lo distinga del contenido real -- hace
    falta entender el titular, no reconocer un patron, y eso no se puede
    resolver con un LLM en produccion porque el bot corre en vivo SIN ACCESO
    A INTERNET (decision del usuario, ver docstring de
    descargar_telegram_cointelegraph.py)."""
    return bool(RE_RUIDO_ESTRUCTURAL.search(titulo))


def _patron_palabra_completa(keyword: str) -> re.Pattern:
    """Compila la keyword exigiendo que empiece como palabra completa (no
    a mitad de otra palabra -- eso es lo que bloquea "war" dentro de
    "toward"/"hardware"/"software"/"award", porque ahi "war" no arranca en
    un limite de palabra) y, para keywords de una sola palabra, permite
    que termine en alguno de los sufijos verbales normales del ingles
    (hack -> hacked/hacking/hacker/hackers/hacks) sin aceptar CUALQUIER
    sufijo -- por eso "hackathon" sigue sin coincidir, "athon" no esta en
    la lista. Las frases de varias palabras (con espacio) se dejan exactas,
    no suelen conjugarse.

    18-sept-2026, OCTAVA vuelta (encontrado en el cruce motor<->noticias, ver
    project_corvus4_mecanismo_noticias): la keyword "pce" (indicador de
    inflacion de la Fed) le quitaba la "e" final pensando que era un verbo
    conjugable ("collapse"->"collaps"+sufijos), dejando raiz "pc" -- y como
    el sufijo es opcional, el patron tambien aceptaba "PC" (ordenador) suelto.
    Avisos tecnicos de Bithumb sobre su app ("PC/Mobile APP...") caian en
    macro por esto. Arreglado exigiendo mas de 3 letras para aplicar el
    recorte de "e" final -- los acronimos de 3 letras o menos (pce, sec, etf,
    cpi...) nunca se conjugan como un verbo real, asi que no necesitan esa
    logica y corren el riesgo de que el recorte produzca otra palabra corta
    de verdad (pc, sec ya se define con espacio final en su propia keyword)."""
    kw = keyword.strip()
    raiz = kw[:-1] if kw.endswith("e") and " " not in kw and len(kw) > 3 else kw
    if " " in kw:
        return re.compile(r"\b" + re.escape(kw) + r"\b")
    return re.compile(r"\b" + re.escape(raiz) + r"(?:" + "|".join(SUFIJOS_VERBALES) + r")?\b")


_PATRONES: dict[str, list[re.Pattern]] = {
    cat: [_patron_palabra_completa(kw) for kw in keywords]
    for cat, keywords in CATEGORIAS.items()
}


def categorizar(titulo: str) -> set[str]:
    """Devuelve el conjunto de categorias en las que cae este titular
    (puede ser vacio si no encaja en ninguna, o varias a la vez)."""
    t = titulo.lower()
    return {cat for cat, patrones in _PATRONES.items() if any(p.search(t) for p in patrones)}


def categorizar_noticias(noticias: list[dict]) -> list[dict]:
    """Añade el campo 'categorias' (list[str]) a cada noticia, sin mutar
    la entrada."""
    out = []
    for n in noticias:
        n2 = dict(n)
        n2["categorias"] = sorted(categorizar(n["titulo"]))
        out.append(n2)
    return out
