"""Calendario de balances (earnings) para TODO el universo, no sólo los candidatos.

Fuentes gratuitas; la fecha es siempre INDICATIVA (nunca confirmada) y hay que verificarla en
relaciones con inversores. Nunca se inventa una fecha y "sin dato" no se confunde con "sin balance".

  1) Nasdaq, calendario por día: una consulta por rueda cubre a todas las empresas que reportan
     ese día (incluye antes de la apertura / después del cierre). ~45 consultas cubren el universo.
  2) Yahoo/yfinance por ticker: sólo respaldo para los que Nasdaq no trae (ADR, balances lejanos),
     con tope por corrida y prioridad para los candidatos.
  3) Caché entre corridas (JSON): una fecha buena no se pierde porque una fuente falle un día,
     y los tickers sin fecha no se reconsultan en cada corrida.

El mismo contrato que `earnings.earnings_for_candidates`: devuelve (dict símbolo -> entrada|None,
cobertura). `símbolo in dict` significa "consultado"; entrada None significa "consultado y sin
fecha publicada". Los ETF no se consultan (no publican balances).
"""
from __future__ import annotations

import json
import logging
import time as _time
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta
from pathlib import Path

NASDAQ_URL = "https://api.nasdaq.com/api/calendar/earnings?date={day}"
NASDAQ_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}
STATUS_TEXT = "FECHA INDICATIVA — confirmar en relaciones con inversores"
CACHE_VERSION = 1

DAYS_AHEAD = 45            # ruedas hacia adelante que se piden a Nasdaq (~9 semanas)
MAX_YAHOO = 40             # consultas de respaldo por corrida
MAX_CONSECUTIVE_FAILS = 4  # si Nasdaq nos bloquea, cortar y seguir con Yahoo + caché
MAX_AGE_DAYS = 7           # una fecha lejana de caché se reconsulta pasada una semana
NEAR_DAYS = 10             # dentro de este plazo la fecha se reconsulta a diario (se mueve/confirma)
RETRY_NO_DATE_DAYS = 3     # "consultado y sin fecha": reintentar recién a los 3 días
KEEP_PAST_DAYS = 30        # purga de entradas viejas del caché
TIME_LABELS = {"BMO": "antes de la apertura", "AMC": "después del cierre"}


# ---------------------------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------------------------
def norm_symbol(sym) -> str:
    """BRK.B / BRK/B / brk-b -> BRK-B (formato Yahoo)."""
    return str(sym or "").strip().upper().replace(".", "-").replace("/", "-")


def business_days(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _parse_day(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------
# fuente 1: Nasdaq por día
# ---------------------------------------------------------------------------------------------
def parse_nasdaq(payload: dict | None, day: date) -> dict[str, dict]:
    """Filas del calendario de un día -> {símbolo: {date, time, fiscal_quarter}}."""
    rows = (((payload or {}).get("data") or {}).get("rows")) or []
    out: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = norm_symbol((row or {}).get("symbol"))
        if not sym:
            continue
        raw = str(row.get("time") or "").lower()
        when = "BMO" if "pre-market" in raw else "AMC" if "after-hours" in raw else None
        out[sym] = {"date": day.isoformat(), "time": when,
                    "fiscal_quarter": row.get("fiscalQuarterEnding") or None}
    return out


def fetch_nasdaq_day(day: date, timeout: int = 20) -> dict:
    req = urllib.request.Request(NASDAQ_URL.format(day=day.isoformat()), headers=NASDAQ_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    status = (payload or {}).get("status") or {}
    if status.get("rCode") not in (None, 200):
        raise RuntimeError(f"Nasdaq rCode {status.get('rCode')}")
    return payload


def collect_nasdaq(today: date, days_ahead: int = DAYS_AHEAD, fetch=fetch_nasdaq_day,
                   pause: float = 0.25, sleep=_time.sleep) -> tuple[dict, dict]:
    """Recorre las próximas ruedas; la fecha más cercana de cada símbolo gana."""
    found: dict[str, dict] = {}
    ok = fail = consec = 0
    aborted = False
    blocked = 0
    error_types = {}
    days = business_days(today, days_ahead)
    for d in days:
        try:
            payload = fetch(d)
            if not isinstance(payload, dict):
                raise ValueError("Nasdaq: respuesta no es un objeto JSON")
            data = payload.get('data')
            if data is not None and not isinstance(data, dict):
                raise ValueError("Nasdaq: data inválida")
            rows = (data or {}).get('rows')
            if rows is not None and not isinstance(rows, list):
                raise ValueError("Nasdaq: rows inválidas")
            parsed = parse_nasdaq(payload, d)
        except Exception as exc:  # red, bloqueo, formato: nunca romper la corrida
            fail += 1
            code = getattr(exc, 'code', None)
            if code in (403, 429): blocked += 1
            category = 'HTTP '+str(code) if code is not None else type(exc).__name__
            error_types[category] = error_types.get(category, 0) + 1
            consec += 1
            logging.warning("Nasdaq %s sin datos: %s", d, str(exc)[:100])
            if consec >= MAX_CONSECUTIVE_FAILS:
                aborted = True
                break
            sleep(pause)
            continue
        consec = 0
        ok += 1
        for sym, entry in parsed.items():
            found.setdefault(sym, entry)
        sleep(pause)
    return found, {"nasdaq_days_requested": len(days), "nasdaq_days_ok": ok,
                   "nasdaq_days_failed": fail, "nasdaq_aborted": aborted,
                   "nasdaq_days_attempted": ok + fail, "nasdaq_blocked_responses": blocked,
                   "nasdaq_error_types": error_types}


# ---------------------------------------------------------------------------------------------
# fuente 2: Yahoo por ticker (respaldo)
# ---------------------------------------------------------------------------------------------
def fetch_yahoo(sym: str, today: date) -> dict | None:
    """None = Yahoo respondió sin fecha futura. Lanza excepción si falló la consulta."""
    import yfinance as yf
    from earnings import parse_earnings
    calendar = yf.Ticker(sym).calendar
    # yfinance puede absorber HTTP/errores y devolver {}. No tratarlo como una
    # consulta válida que pruebe ausencia de fecha ni sobrescribir el caché.
    if not isinstance(calendar, dict) or not calendar:
        raise RuntimeError("Yahoo calendario vacío/no verificable")
    entry = parse_earnings(calendar, today)
    return {"date": entry["date"], "time": None, "fiscal_quarter": None} if entry else None


# ---------------------------------------------------------------------------------------------
# caché
# ---------------------------------------------------------------------------------------------
def load_cache(path) -> dict:
    if not path:
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("version") == CACHE_VERSION and isinstance(raw.get("entries"), dict):
            return {norm_symbol(k): v for k, v in raw["entries"].items()
                    if isinstance(v, dict)}
    except (OSError, ValueError, AttributeError):
        pass
    return {}


def save_cache(path, entries: dict) -> None:
    if not path:
        return
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps({"version": CACHE_VERSION, "entries": entries},
                                ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(p)
    except OSError as exc:
        logging.warning("No se pudo guardar el caché de balances: %s", exc)


def _age(entry: dict, today: date) -> int:
    d = _parse_day(entry.get("fetched_at"))
    return (today - d).days if d else 9999


def _is_usable(entry: dict | None, today: date) -> bool:
    """¿La entrada de caché sirve tal cual, sin reconsultar?"""
    if not entry:
        return False
    d = _parse_day(entry.get("date"))
    age = _age(entry, today)
    if d is None:  # "consultado y sin fecha": no insistir todos los días
        return age <= RETRY_NO_DATE_DAYS
    if d < today:
        return False
    until = (d - today).days
    return age <= (1 if until <= NEAR_DAYS else MAX_AGE_DAYS)


def _public(entry: dict, today: date) -> dict | None:
    d = _parse_day(entry.get("date"))
    if d is None or d < today:
        return None
    age = _age(entry, today)
    return {"date": d.isoformat(), "days_until": (d - today).days,
            "time": entry.get("time"), "time_label": TIME_LABELS.get(entry.get("time")),
            "fiscal_quarter": entry.get("fiscal_quarter"),
            "source": f"{entry.get('source', '?')} (calendario gratuito)",
            "status": STATUS_TEXT, "fetched_at": entry.get("fetched_at"),
            "stale": age >= 2, "cache_age_days": max(age, 0)}


# ---------------------------------------------------------------------------------------------
# orquestación
# ---------------------------------------------------------------------------------------------
def _is_stock(a: dict) -> bool:
    if a.get('earnings_is_etf') is True:
        return False
    kind = (a.get("data") or {}).get("asset_kind")
    return a.get("sector") != "Índices y ETFs" and (kind is None or kind == "ACCION")


def earnings_for_universe(assets: list[dict], today: date, cache_path=None, priority=None,
                          fetch_nasdaq=fetch_nasdaq_day, fetch_yahoo_fn=fetch_yahoo,
                          days_ahead: int = DAYS_AHEAD, max_yahoo: int = MAX_YAHOO,
                          pause: float = 0.25, sleep=_time.sleep) -> tuple[dict, dict]:
    priority = {norm_symbol(s) for s in (priority or ())}
    stocks, etfs = [], set()
    for a in assets:
        sym = norm_symbol(a.get("usa"))
        if not sym:
            continue
        if _is_stock(a):
            if sym not in stocks:
                stocks.append(sym)
        else:
            etfs.add(sym)

    cache = load_cache(cache_path)
    today_iso = today.isoformat()
    bulk, nstats = collect_nasdaq(today, days_ahead, fetch_nasdaq, pause, sleep)

    resolved: dict[str, dict | None] = {}   # símbolo -> entrada de caché (o None = sin fecha)
    origin: dict[str, str] = {}
    queue: list[str] = []
    for sym in stocks:
        if sym in bulk:
            cache[sym] = {**bulk[sym], "source": "Nasdaq", "fetched_at": today_iso}
            resolved[sym], origin[sym] = cache[sym], "nasdaq"
        elif _is_usable(cache.get(sym), today):
            resolved[sym], origin[sym] = cache[sym], "cache"
        else:
            queue.append(sym)

    # respaldo Yahoo: candidatos primero, luego los que nunca se consultaron, luego los vencidos
    queue.sort(key=lambda s: (s not in priority, s in cache, s))
    yahoo_queries = yahoo_errors = yahoo_no_future = 0
    for sym in queue[:max_yahoo]:
        yahoo_queries += 1
        try:
            entry = fetch_yahoo_fn(sym, today)
        except Exception as exc:
            yahoo_errors += 1
            logging.warning("Yahoo %s sin verificar: %s", sym, str(exc)[:100])
            sleep(pause)
            continue
        if entry and _public({**entry, 'fetched_at': today_iso}, today):
            cache[sym] = {**entry, "source": "Yahoo", "fetched_at": today_iso}
            resolved[sym], origin[sym] = cache[sym], "yahoo"
        else:
            yahoo_no_future += 1
            # Una respuesta sin fecha no revoca una fecha futura ya conocida.
            # Mantener su fuente y fetched_at originales para mostrar antigüedad.
            if _public(cache.get(sym) or {}, today):
                resolved[sym], origin[sym] = cache[sym], 'cache'
                sleep(pause)
                continue
            cache[sym] = {"date": None, "time": None, "source": "Yahoo", "fetched_at": today_iso}
            resolved[sym], origin[sym] = cache[sym], "yahoo"
        sleep(pause)

    # lo que no se pudo consultar: si hay una fecha futura vieja en caché, se muestra marcada
    for sym in queue:
        if sym not in resolved and _public(cache.get(sym) or {}, today):
            resolved[sym], origin[sym] = cache[sym], "cache"

    result: dict[str, dict | None] = {}
    for sym in resolved:
        result[sym] = _public(resolved[sym], today)

    # purga y guardado
    keep = set(stocks)
    for sym in list(cache):
        d = _parse_day(cache[sym].get("date"))
        if sym not in keep or (d and d < today - timedelta(days=KEEP_PAST_DAYS)):
            del cache[sym]
    save_cache(cache_path, cache)

    with_date = [s for s, v in result.items() if v]
    coverage = {
        "stocks": len(stocks), "etfs": len(etfs),
        "with_date": len(with_date),
        "within_14_days": sum(1 for s in with_date if result[s]["days_until"] <= 14),
        "from_nasdaq": sum(1 for s in with_date if origin[s] == "nasdaq"),
        "from_yahoo": sum(1 for s in with_date if origin[s] == "yahoo"),
        "from_cache": sum(1 for s in with_date if origin[s] == "cache"),
        "no_date": sum(1 for s, v in result.items() if v is None),
        "not_consulted": len(stocks) - len(result),
        "yahoo_queries": yahoo_queries, "yahoo_errors": yahoo_errors, "yahoo_no_future": yahoo_no_future,
        **nstats,
    }
    logging.info("BALANCES cobertura=%s", json.dumps(coverage, ensure_ascii=False, sort_keys=True))
    return result, coverage


def balance_label(entry: dict | None, checked: bool, is_etf: bool = False) -> str:
    """Etiqueta de estado. Distingue ETF, no consultada, sin fecha y fecha indicativa."""
    if is_etf:
        return "ETF · SIN BALANCES"
    if not checked:
        return "FECHA NO CONSULTADA"
    if not entry:
        return "SIN FECHA PUBLICADA"
    n = entry["days_until"]
    base = "BALANCE <=7 DÍAS" if n <= 7 else "BALANCE <=14 DÍAS" if n <= 14 else "PRÓXIMO BALANCE"
    return base + (" · DATO DE CACHÉ" if entry.get("stale") else "")
