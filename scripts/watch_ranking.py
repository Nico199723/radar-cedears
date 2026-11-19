"""Ranking informativo: nunca modifica la señal ni genera órdenes."""
from collections import Counter
from decision_engine import numeric, BUY_FLOOR

MIN_LIQUIDITY = 1_000_000
MAX_PER_SECTOR = 2


def ranked_watchlist(assets, limit=5):
    pool = []
    for a in assets:
        d = a.get('data') or {}
        score = numeric(d, 'rank_score')
        if (not a.get('usa') or score is None or numeric(d, 'price') is None
                or (numeric(d, 'dollar_volume20') or 0) < MIN_LIQUIDITY
                or a.get('signal', '').startswith(('SIN', 'DATOS'))):
            continue
        pool.append(a)
    pool.sort(key=lambda a: (-a['data']['rank_score'], a['ticker']))
    chosen, deferred, sectors = [], [], Counter()
    for a in pool:
        if sectors[a.get('sector')] >= MAX_PER_SECTOR:
            deferred.append(a)
        elif len(chosen) < limit:
            chosen.append(a)
            sectors[a.get('sector')] += 1
    chosen.extend(deferred[:max(0, limit-len(chosen))])
    chosen.sort(key=lambda a: (-a['data']['rank_score'], a['ticker']))
    result = []
    for a in chosen:
        d = a['data']
        result.append({**d, 'ticker':a['ticker'], 'usa':a['usa'],
                       'sector':a.get('sector'), 'signal':a['signal'],
                       'tone':a.get('tone'), 'candidate':a.get('candidate'),
                       'relative_spy20':d.get('rs_spy20'),
                       'relative_qqq20':d.get('rs_qqq20'),
                       'earnings':a.get('earnings'), 'earnings_status':a.get('earnings_status'),
                       'tag':('MEJOR DISPONIBLE · BAJO BANDA DE COMPRA' if d['rank_score'] < BUY_FLOOR
                              else 'RANKING PARA ESTUDIAR · REVISAR SEÑAL'),
                       'ranking_only':True})
    return result
