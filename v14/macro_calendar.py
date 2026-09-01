"""
V14 — Calendario de eventos macro.

Durante ventanas ±2h alrededor de FOMC, NFP y CPI, el bot sube el umbral
de entrada +20 puntos (de 58 a 78), bloqueando trades de baja convicción
en momentos de alta volatilidad macro.

Fuentes oficiales:
  FOMC : federalreserve.gov/monetarypolicy/fomccalendars.htm
  CPI  : bls.gov/schedule/news_release/cpi.htm
  NFP  : primer viernes de cada mes, 12:30 UTC (08:30 EST)
"""

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

# ── FOMC (anuncio a las 14:00 UTC) ────────────────────────────────────────────
FOMC_HOUR_UTC = 14

FOMC_DATES = {
    2023: ["2023-02-01","2023-03-22","2023-05-03","2023-06-14",
           "2023-07-26","2023-09-20","2023-11-01","2023-12-13"],
    2024: ["2024-01-31","2024-03-20","2024-05-01","2024-06-12",
           "2024-07-31","2024-09-18","2024-11-07","2024-12-18"],
    2025: ["2025-01-29","2025-03-19","2025-05-07","2025-06-18",
           "2025-07-30","2025-09-17","2025-11-05","2025-12-17"],
    2026: ["2026-01-28","2026-03-18","2026-05-06","2026-06-17",
           "2026-07-29","2026-09-16","2026-11-04","2026-12-09"],
    2027: ["2027-01-27","2027-03-17","2027-05-05","2027-06-16",
           "2027-07-28","2027-09-22","2027-11-03","2027-12-15"],
}

# ── CPI USA (publicación a las 12:30 UTC) ─────────────────────────────────────
CPI_HOUR_UTC = 12

CPI_DATES = {
    2023: ["2023-01-12","2023-02-14","2023-03-14","2023-04-12",
           "2023-05-10","2023-06-13","2023-07-12","2023-08-10",
           "2023-09-13","2023-10-12","2023-11-14","2023-12-12"],
    2024: ["2024-01-11","2024-02-13","2024-03-12","2024-04-10",
           "2024-05-15","2024-06-12","2024-07-11","2024-08-14",
           "2024-09-11","2024-10-10","2024-11-13","2024-12-11"],
    2025: ["2025-01-15","2025-02-12","2025-03-12","2025-04-10",
           "2025-05-13","2025-06-11","2025-07-15","2025-08-12",
           "2025-09-10","2025-10-15","2025-11-13","2025-12-10"],
    2026: ["2026-01-14","2026-02-11","2026-03-11","2026-04-09",
           "2026-05-13","2026-06-10","2026-07-15","2026-08-12",
           "2026-09-09","2026-10-14","2026-11-12","2026-12-09"],
    2027: ["2027-01-13","2027-02-10","2027-03-10","2027-04-14",
           "2027-05-12","2027-06-09","2027-07-14","2027-08-11",
           "2027-09-08","2027-10-13","2027-11-10","2027-12-08"],
}


def _first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    days_ahead = (4 - d.weekday()) % 7
    return d + timedelta(days=days_ahead)


def get_macro_events(year: int) -> list:
    """Devuelve lista de (datetime_utc, etiqueta) para el año dado."""
    events = []

    # NFP: primer viernes de cada mes a las 12:30 UTC
    for month in range(1, 13):
        d = _first_friday(year, month)
        dt = datetime(d.year, d.month, d.day, 12, 30, tzinfo=timezone.utc)
        events.append((dt, "NFP"))

    # FOMC
    for date_str in FOMC_DATES.get(year, []):
        dt = datetime.fromisoformat(date_str).replace(
            hour=FOMC_HOUR_UTC, tzinfo=timezone.utc)
        events.append((dt, "FOMC"))

    # CPI
    for date_str in CPI_DATES.get(year, []):
        dt = datetime.fromisoformat(date_str).replace(
            hour=CPI_HOUR_UTC, tzinfo=timezone.utc)
        events.append((dt, "CPI"))

    return events


def is_macro_event_window(ts, window_hours: float = 2.0) -> tuple[bool, str | None]:
    """
    Devuelve (True, etiqueta) si ts está dentro de ±window_hours de un evento macro.
    ts puede ser datetime o pandas Timestamp.
    """
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    window = timedelta(hours=window_hours)
    year = ts.year
    for y in (year - 1, year, year + 1):
        for event_dt, label in get_macro_events(y):
            if abs(ts - event_dt) <= window:
                return True, label
    return False, None


# Incremento de min_score durante ventana macro
MACRO_MIN_SCORE_BONUS = 20


if __name__ == "__main__":
    # Test rápido: próximos eventos desde hoy
    from datetime import date as _date
    now = datetime.now(timezone.utc)
    year = now.year
    events = sorted(get_macro_events(year) + get_macro_events(year + 1))
    upcoming = [(dt, lbl) for dt, lbl in events if dt >= now][:10]
    print(f"\nPróximos eventos macro desde {now.strftime('%Y-%m-%d %H:%M')} UTC:\n")
    for dt, lbl in upcoming:
        print(f"  {lbl:5s}  {dt.strftime('%Y-%m-%d %H:%M')} UTC")
    print()
