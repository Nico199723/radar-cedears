"""Versioned experiment only: never used to mutate the production ledger."""
import math
VERSION='atr-risk-v1-candidate'
CAPITAL=2000.
RISK_FRACTION=.005
ATR_MULTIPLE=2.
MAX_EXPOSURE=.5
FEE_BPS=5.
SLIPPAGE_BPS=10.
HORIZONS=(5,10,20)
FIXED_STOPS={'fixed6':.06,'fixed8':.08}


def position_plan(entry, atr, capital=CAPITAL, kind='atr'):
    if not all(math.isfinite(v) and v>0 for v in (entry,atr,capital)):return None
    distance=ATR_MULTIPLE*atr if kind=='atr' else entry*FIXED_STOPS[kind]
    stop=entry-distance
    if stop<=0:return None
    # Size includes normal adverse stop slippage + both commissions.
    expected_exit=stop*(1-SLIPPAGE_BPS/10000)
    unit_risk=entry-expected_exit+(entry+expected_exit)*FEE_BPS/10000
    shares=min(capital*RISK_FRACTION/unit_risk,capital*MAX_EXPOSURE/(entry*(1+FEE_BPS/10000)))
    return {'entry':entry,'stop':stop,'atr_at_signal':atr,'shares':shares,
            'risk_per_share':unit_risk,'risk_usd':shares*unit_risk,
            'risk_fraction':shares*unit_risk/capital,'target_2r':entry+2*unit_risk}
