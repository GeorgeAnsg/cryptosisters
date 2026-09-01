"""
bot_sentiment.py — Fuentes de sentimiento y datos externos (v6)
================================================================
  - GDELT news sentiment (fetch_sentiment, load_daily_sentiment)
  - Fear & Greed Index (fetch_fear_greed, load_fear_greed_sentiment)
  - Macro correlaciones: DXY, SP500, Gold, Oil (fetch/load_macro_correlations)
  - Funding rate (fetch_funding_oi)
  - Order book walls (fetch_orderbook_signals)
"""

import os
import json
import time
import requests
import pandas as pd


# =============================================================================
# KEYWORDS DE SENTIMIENTO
# =============================================================================

BULLISH_KEYWORDS = [
    "bull", "bullish", "surge", "soar", "rally", "breakout", "moon",
    "all-time high", "ath", "pump", "gain", "growth", "adoption",
    "approved", "approval", "etf approved", "institutional",
    "partnership", "upgrade", "launch", "milestone", "record",
    "accumulation", "recovery", "support held", "inflows",
    "whale buying", "short squeeze", "golden cross",
]

BEARISH_KEYWORDS = [
    "bear", "bearish", "crash", "dump", "plunge", "drop", "sell-off",
    "selloff", "hack", "hacked", "exploit", "vulnerability", "ban",
    "banned", "regulation", "fine", "penalty", "lawsuit", "fraud",
    "scam", "rug pull", "rugpull", "bankruptcy", "insolvent",
    "liquidation", "fear", "panic", "collapse", "warning",
    "outflows", "whale selling", "death cross", "breakdown",
]

HIGH_IMPACT_KEYWORDS = [
    "federal reserve", "fed rate", "fomc", "interest rate", "rate hike", "rate cut",
    "inflation", "cpi", "gdp", "recession", "quantitative easing", "quantitative tightening",
    "nonfarm payroll", "non-farm payroll", "jobs report", "unemployment rate",
    "consumer price", "producer price", "pce", "core inflation",
    "retail sales", "pmi", "ism manufacturing", "jobless claims",
    "earnings report", "trade deficit", "trade surplus",
    "war", "invasion", "military", "sanction", "conflict", "airstrike",
    "nuclear", "escalat", "ceasefire", "crisis", "coup",
    "sec ", "cftc", "ban crypto", "banned crypto", "illegal crypto", "crackdown",
    "etf approved", "etf rejected", "etf denied", "spot etf", "spot bitcoin etf",
    "government", "congress", "senate", "legislation", "executive order",
    "hack", "exploit", "breach", "stolen", "bankruptcy", "insolvent",
    "collapse", "frozen", "halted withdrawals",
    "ftx", "celsius", "tether",
    "flash crash", "market crash", "circuit breaker", "liquidation cascade",
    "strategic reserve", "bitcoin reserve", "national reserve",
]


# =============================================================================
# GDELT
# =============================================================================

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

CRYPTO_NEWS_DOMAINS = [
    "coindesk.com", "cointelegraph.com", "decrypt.co",
    "theblock.co", "bitcoinmagazine.com", "newsbtc.com",
]

TICKER_TO_NAME = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple",
    "HYPE": "hyperliquid", "AAVE": "aave",
    "ADA": "cardano", "DOGE": "dogecoin", "BNB": "binance coin",
    "MATIC": "polygon", "DOT": "polkadot", "LTC": "litecoin",
    "AVAX": "avalanche", "LINK": "chainlink", "TRX": "tron",
    "SHIB": "shiba inu", "ATOM": "cosmos", "UNI": "uniswap",
}


def analyze_headline_sentiment(title: str) -> int:
    t = title.lower()
    if not any(kw in t for kw in HIGH_IMPACT_KEYWORDS):
        return 0
    bull = sum(1 for kw in BULLISH_KEYWORDS if kw in t)
    bear = sum(1 for kw in BEARISH_KEYWORDS if kw in t)
    if bull > bear: return 1
    if bear > bull: return -1
    return 0


def build_gdelt_query(ticker: str) -> str:
    domain_filter = " OR ".join(f"domainis:{d}" for d in CRYPTO_NEWS_DOMAINS)
    name = TICKER_TO_NAME.get(ticker.upper(), ticker.lower())
    return f"{name} ({domain_filter})"


def fetch_gdelt_articles(query: str, timespan: str = None, start: str = None,
                         end: str = None, maxrecords: int = 20, retries: int = 6) -> list:
    params = {"query": query, "mode": "artlist", "format": "json",
              "maxrecords": maxrecords, "sort": "datedesc"}
    if timespan: params["timespan"] = timespan
    if start and end:
        params["startdatetime"] = start
        params["enddatetime"]   = end
    for _ in range(retries):
        try:
            resp = requests.get(GDELT_URL, params=params, timeout=20,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                articles = []
                for a in resp.json().get("articles", []):
                    sd = a.get("seendate", "")
                    date_str = f"{sd[0:4]}-{sd[4:6]}-{sd[6:8]}" if len(sd) >= 8 else ""
                    articles.append({"title": a.get("title", ""), "date": date_str,
                                     "source": a.get("domain", "")})
                return articles
            if resp.status_code == 429:
                time.sleep(15); continue
            return []
        except Exception:
            time.sleep(5)
    return []


def fetch_sentiment(pair: str) -> dict:
    symbol = pair.split("/")[0]
    try:
        articles = fetch_gdelt_articles(build_gdelt_query(symbol), timespan="3d", maxrecords=20)
        bullish = bearish = 0
        news_list = []
        for a in articles[:15]:
            title = a.get("title", "")
            val   = analyze_headline_sentiment(title)
            if val > 0: bullish += 1
            elif val < 0: bearish += 1
            news_list.append({"title": title[:80],
                              "sentiment": "+" if val > 0 else ("-" if val < 0 else "=")})
        total = bullish + bearish
        if total == 0:
            return {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral",
                    "shock": None, "news": news_list[:5]}
        bull_score = round(bullish / total * 15)
        bear_score = round(bearish / total * 15)
        sentiment  = ("positivo" if bullish > bearish * 1.5
                      else "negativo" if bearish > bullish * 1.5 else "mixto")
        shock      = None
        if total >= 4:
            if bearish / total >= 0.8: shock = "bear"
            elif bullish / total >= 0.8: shock = "bull"
        return {"bullish_score": bull_score, "bearish_score": bear_score,
                "sentiment": sentiment, "shock": shock, "news": news_list[:5]}
    except Exception as e:
        return {"bullish_score": 0, "bearish_score": 0, "sentiment": "error",
                "news": [], "error": str(e)}


def load_daily_sentiment(news_file: str) -> dict:
    with open(news_file, "r", encoding="utf-8") as f:
        news = json.load(f)
    by_day: dict = {}
    for item in news:
        day = item.get("date", "")
        if day:
            by_day.setdefault(day, []).append(item["sentiment"])
    result = {}
    for day, labels in by_day.items():
        bullish = sum(1 for s in labels if s == "+")
        bearish = sum(1 for s in labels if s == "-")
        total   = bullish + bearish
        if total == 0:
            result[day] = {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral", "shock": None}
            continue
        bull_score = round(bullish / total * 15)
        bear_score = round(bearish / total * 15)
        sentiment  = ("positivo" if bullish > bearish * 1.5
                      else "negativo" if bearish > bullish * 1.5 else "mixto")
        shock = None
        if total >= 4:
            if bearish / total >= 0.8: shock = "bear"
            elif bullish / total >= 0.8: shock = "bull"
        result[day] = {"bullish_score": bull_score, "bearish_score": bear_score,
                       "sentiment": sentiment, "shock": shock}
    return result


# =============================================================================
# FEAR & GREED
# =============================================================================

def fetch_fear_greed() -> dict:
    # V14: DVOL (Deribit implied volatility) reemplaza Fear & Greed
    try:
        from v14.deribit_options import get_current_dvol, dvol_score
        dvol = get_current_dvol(timeout=8)
        ds = dvol_score(dvol)
        return {
            "value": round(dvol, 1) if dvol is not None else 55,
            "label": ds["label"],
            "bull_mod": ds["bull_mod"],
            "bear_mod": ds["bear_mod"],
        }
    except Exception:
        return {"value": 55, "label": "normal", "bull_mod": 5, "bear_mod": 5}


def load_fear_greed_sentiment(fg_file: str) -> dict:
    with open(fg_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = {}
    for item in data:
        val = item["value"]
        if val >= 75:   bs, be, s, sh = 15, 0, "positivo", "bull"
        elif val >= 65: bs, be, s, sh = 10, 2, "positivo", None
        elif val >= 55: bs, be, s, sh = 7,  4, "mixto",    None
        elif val >= 45: bs, be, s, sh = 5,  5, "neutral",  None
        elif val >= 35: bs, be, s, sh = 4,  7, "mixto",    None
        elif val >= 25: bs, be, s, sh = 2, 10, "negativo", None
        else:           bs, be, s, sh = 0, 15, "negativo", "bear"
        result[item["date"]] = {"bullish_score": bs, "bearish_score": be,
                                "sentiment": s, "shock": sh,
                                "value": val, "bull_mod": bs, "bear_mod": be}
    return result


# =============================================================================
# MACRO CORRELACIONES (DXY, SP500, Gold, Oil)
# =============================================================================

MACRO_CORR_ENABLED: bool = os.getenv("MACRO_CORR_ENABLED", "1").strip() == "1"

_MACRO_TICKERS = {
    "DXY":   "DX-Y.NYB",
    "SP500": "^GSPC",
    "Gold":  "GC=F",
    "Oil":   "CL=F",
}


def _score_macro(name: str, chg: float) -> tuple:
    bull = bear = 0
    if name == "DXY":
        if chg >= 1.2:    bear += 4
        elif chg >= 0.8:  bear += 2
        elif chg <= -1.2: bull += 3
        elif chg <= -0.8: bull += 2
    elif name == "SP500":
        if chg >= 1.5:    bull += 3
        elif chg >= 0.8:  bull += 1
        elif chg <= -1.5: bear += 4
        elif chg <= -0.8: bear += 2
    elif name == "Gold":
        if chg >= 2.0:   bear += 3
        elif chg >= 1.2: bear += 1
    elif name == "Oil":
        if chg >= 4.0:   bear += 2
        elif chg >= 2.5: bear += 1
    return bull, bear


def fetch_macro_correlations() -> dict:
    if not MACRO_CORR_ENABLED:
        return {"bull_mod": 0, "bear_mod": 0, "detail": {}}
    try:
        import yfinance as yf
        bull_mod = bear_mod = 0
        detail   = {}
        for name, ticker in _MACRO_TICKERS.items():
            df = yf.download(ticker, period="3d", interval="1d",
                             progress=False, auto_adjust=True)
            if df.empty or len(df) < 2:
                continue
            close = df["Close"].squeeze()
            chg   = float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100)
            detail[name] = round(chg, 2)
            b, be = _score_macro(name, chg)
            bull_mod += b; bear_mod += be
        return {"bull_mod": min(bull_mod, 8), "bear_mod": min(bear_mod, 8), "detail": detail}
    except Exception:
        return {"bull_mod": 0, "bear_mod": 0, "detail": {}}


def load_macro_correlations_historical(start_date: str, end_date: str) -> dict:
    try:
        import yfinance as yf
        from datetime import datetime, timedelta
        start_ext = (datetime.fromisoformat(start_date) - timedelta(days=5)).strftime("%Y-%m-%d")
        all_data  = {}
        for name, ticker in _MACRO_TICKERS.items():
            df = yf.download(ticker, start=start_ext, end=end_date,
                             interval="1d", progress=False, auto_adjust=True)
            if not df.empty:
                all_data[name] = df["Close"].squeeze()
        if not all_data:
            return {}
        result = {}
        dates  = sorted(set(str(d.date()) for s in all_data.values() for d in s.index))
        for day_str in dates:
            if day_str < start_date:
                continue
            bull_mod = bear_mod = 0
            detail   = {}
            for name, series in all_data.items():
                idx = series.index.searchsorted(day_str)
                if idx == 0 or idx >= len(series):
                    continue
                curr = float(series.iloc[idx])
                prev = float(series.iloc[idx - 1])
                if prev == 0:
                    continue
                chg = (curr - prev) / prev * 100
                detail[name] = round(chg, 2)
                b, be = _score_macro(name, chg)
                bull_mod += b; bear_mod += be
            result[day_str] = {"bull_mod": min(bull_mod, 8), "bear_mod": min(bear_mod, 8),
                               "detail": detail}
        print(f"  Correlaciones macro: {len(result)} días cargados ({start_date} → {end_date})",
              flush=True)
        return result
    except Exception as e:
        print(f"  [WARN] Correlaciones macro no disponibles: {e}")
        return {}


# =============================================================================
# FUNDING RATE
# =============================================================================

def fetch_funding_oi(exchange, pair: str) -> dict:
    # V14: funding en neutro fijo (backtest muestra que la señal real perjudica en OOS 2025-26)
    return {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3}


# =============================================================================
# ORDER BOOK
# =============================================================================

def fetch_orderbook_signals(exchange, pair: str, current_price: float) -> dict:
    try:
        ob   = exchange.fetch_order_book(pair, 50)
        bids = [(b[0], b[0] * b[1]) for b in ob["bids"] if b[1] > 0]
        asks = [(a[0], a[0] * a[1]) for a in ob["asks"] if a[1] > 0]
        if not bids or not asks:
            return {"support_walls": [], "resistance_walls": [], "bull_mod": 0, "bear_mod": 0}
        bid_mean = sum(b[1] for b in bids) / len(bids)
        ask_mean = sum(a[1] for a in asks) / len(asks)
        support_walls    = [b[0] for b in bids if b[1] > 3 * bid_mean]
        resistance_walls = [a[0] for a in asks if a[1] > 3 * ask_mean]
        bull_mod = bear_mod = 0
        for w in support_walls:
            if current_price * 0.995 <= w <= current_price:
                bull_mod = 7; break
        for w in resistance_walls:
            if current_price <= w <= current_price * 1.005:
                bear_mod = 7; break
        return {"support_walls": support_walls[:5], "resistance_walls": resistance_walls[:5],
                "bull_mod": bull_mod, "bear_mod": bear_mod}
    except Exception:
        return {"support_walls": [], "resistance_walls": [], "bull_mod": 0, "bear_mod": 0}
