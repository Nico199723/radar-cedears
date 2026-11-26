"""Small presentation-only chart files; never feed signals or the paper ledger."""
import json
import logging
import math
import re
from pathlib import Path

BARS = 90


def chart_filename(symbol):
    if not isinstance(symbol, str) or not symbol or symbol.startswith('^'):
        return None
    return re.sub(r'[^A-Za-z0-9.-]', '_', symbol) + '.json'


def chart_series(frame, bars=BARS):
    """Input must contain complete daily candles. Compute MAs before trimming."""
    import pandas as pd
    f = frame.sort_index()
    f = f.loc[~f.index.duplicated(keep='last')]
    close = pd.to_numeric(f['Close'], errors='coerce')
    close = close.where(close.map(lambda v: math.isfinite(v) if pd.notna(v) else False))
    def clean(series):
        return [round(float(v), 2) if pd.notna(v) and math.isfinite(v) else None
                for v in series.iloc[-bars:]]
    return {'d': [v.date().isoformat() for v in close.index[-bars:]],
            'c': clean(close),
            **{f'm{n}': clean(close.rolling(n).mean()) for n in (21, 50, 200)}}


def publish_charts(frames, now, directory):
    from actualizar import last_complete_daily
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # A failed symbol must not leave a chart from an older cut behind.
    for old in directory.glob('*.json'):
        old.unlink()
    count = 0
    seen = set()
    for symbol, frame in frames.items():
        name = chart_filename(symbol)
        if name is None:
            continue
        try:
            if name in seen:
                raise ValueError('Nombre de gráfico duplicado')
            seen.add(name)
            complete = last_complete_daily(frame, now)
            if complete.empty:
                continue
            chart = chart_series(complete)
            payload = json.dumps(chart, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            (directory / name).write_text(payload, encoding='utf-8')
            count += 1
        except Exception as exc:
            logging.warning('Gráfico omitido %s: %s', symbol, exc)
    return {'path': './charts/', 'bars': BARS, 'count': count}
