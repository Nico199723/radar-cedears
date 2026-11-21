import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lectura_espectral as sp  # noqa: E402

SEEDS = (7, 11, 23)
BUY = {"COMPRA CONDICIONAL", "COMPRA CON PRECAUCIÓN"}


def build(segments, seed=7, vol=0.003, warm=300, warm_drift=0.0015, volume=10_000_000.0):
    """Serie diaria sintética: tendencia previa + tramos (n_ruedas, retorno diario)."""
    rng = np.random.default_rng(seed)
    rets = [warm_drift] * warm
    for n, d in segments:
        rets += [d] * n
    rets = np.array(rets) + rng.normal(0, vol, len(rets))
    close = 100.0 * np.cumprod(1 + rets)
    idx = pd.bdate_range(end="2026-11-12", periods=len(close))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.004, len(close))))
    lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.004, len(close))))
    v = volume * rng.uniform(0.95, 1.05, len(close))
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": close, "Volume": v}, index=idx)


FRESH = [(10, -0.004), (3, 0.010)]                 # cruzó la SMA21 hace 1-3 ruedas
FIFTEEN_UP = [(10, -0.004), (15, 0.007)]           # 12-15 ruedas arriba, ya subió bastante
REBOUND_200 = [(20, -0.009), (8, 0.007)]           # cayó, hizo piso en la SMA200 y rebota
JUST_LOST = [(25, 0.004), (4, -0.018)]             # recién perdió la SMA21
PARABOLIC = [(10, -0.004), (15, 0.020)]
KNIFE = [(60, -0.006)]


def read(seg, seed, **kw):
    return sp.read(build(seg, seed), **kw)


def _index_frame(drift_tail):
    idx = pd.bdate_range(end="2026-11-12", periods=260)
    c = 100 * np.cumprod(1 + np.r_[[0.001] * 200, drift_tail])
    return pd.DataFrame({"Open": c, "High": c * 1.004, "Low": c * 0.996, "Close": c, "Volume": 1e8}, index=idx), idx


def hostile_macro():
    d, idx = _index_frame([-0.006] * 60)
    vix = pd.Series(np.r_[np.full(250, 20.0), np.linspace(22, 33, 10)], index=idx)
    return sp.macro_wind(d, d, vix)


def friendly_macro():
    d, idx = _index_frame([0.001] * 60)
    vix = pd.Series(np.r_[np.full(250, 22.0), np.linspace(20, 14, 10)], index=idx)
    return sp.macro_wind(d, d, vix)


class TimingTests(unittest.TestCase):
    def test_fresh_cross_is_worth_more_than_fifteen_bars_above(self):
        for s in SEEDS:
            a, b = read(FRESH, s), read(FIFTEEN_UP, s)
            self.assertGreater(a.score, b.score + 8, (s, a.score, b.score, a.stage, b.stage))

    def test_rebound_from_200_beats_just_lost_the_21(self):
        for s in SEEDS:
            a, b = read(REBOUND_200, s), read(JUST_LOST, s)
            self.assertGreater(a.score, b.score + 15, (s, a.score, b.score, a.stage, b.stage))
            self.assertIn(a.signal, BUY, (s, a.signal, a.stage))

    def test_extension_and_runup_reduce_value(self):
        for s in SEEDS:
            a, b = read(FRESH, s), read(PARABOLIC, s)
            self.assertLess(b.score, a.score - 10, (s, a.score, b.score))
            self.assertEqual(b.stage, "EXTENDIDA")
            self.assertNotEqual(b.signal, "COMPRA CONDICIONAL")

    def test_falling_knife_is_deteriorated_not_a_buy(self):
        for s in SEEDS:
            r = read(KNIFE, s)
            self.assertIn(r.signal, {"REDUCIR / EVITAR", "SALIR / EVITAR"}, (s, r.signal, r.score))
            self.assertLess(r.score, 35)

    def test_no_cliff_at_the_sma21(self):
        """Cruzar la SMA21 es un evento, pero a centímetros de la media no hay saltos."""
        base = build(FRESH, 7)
        ma21 = base["Close"].rolling(21).mean().iloc[-1]
        a = float(sp.atr(base).iloc[-1])
        vals = []
        for k in np.arange(-0.6, 0.61, 0.1):
            d = base.copy()
            px = ma21 + k * a
            d.iloc[-1, d.columns.get_loc("Close")] = px
            d.iloc[-1, d.columns.get_loc("High")] = max(d["High"].iloc[-1], px)
            d.iloc[-1, d.columns.get_loc("Low")] = min(d["Low"].iloc[-1], px)
            vals.append(sp.read(d).score)
        self.assertLess(np.abs(np.diff(vals)).max(), 8.0, vals)


class NoVetoTests(unittest.TestCase):
    def test_signal_vocabulary_has_no_veto(self):
        for seg in (FRESH, FIFTEEN_UP, REBOUND_200, JUST_LOST, PARABOLIC, KNIFE):
            for s in SEEDS:
                self.assertNotIn("VETAD", read(seg, s).signal)

    def test_hostile_macro_modulates_but_does_not_block(self):
        hm = hostile_macro()
        self.assertEqual(hm["label"], "EN CONTRA")
        for s in SEEDS:
            neutral, hostile = read(FRESH, s), read(FRESH, s, macro=hm)
            self.assertLessEqual(neutral.score - hostile.score, sp.MACRO_SCORE_SWING + 0.5)
            self.assertIn(hostile.signal, BUY | {"VIGILAR COMPRA · SCORE"})
            self.assertLess(hostile.size_mult, neutral.size_mult)
            self.assertGreaterEqual(hostile.size_mult, 0.4)

    def test_friendly_macro_keeps_full_size(self):
        fm = friendly_macro()
        self.assertEqual(fm["label"], "A FAVOR")
        self.assertGreaterEqual(read(FRESH, 7, macro=fm).size_mult, 0.9)

    def test_missing_macro_is_neutral(self):
        m = sp.macro_wind(None, None, None)
        self.assertEqual(m["label"], "NEUTRAL")
        self.assertFalse(m["verified"])

    def test_earnings_and_low_liquidity_are_frictions(self):
        base, near = read(FRESH, 7), read(FRESH, 7, earnings_days=3)
        self.assertEqual(near.signal, base.signal)
        self.assertLess(near.size_mult, base.size_mult)
        self.assertTrue(any("Balance" in x for x in near.frictions))
        thin = sp.read(build(FRESH, 7, volume=20_000))   # ~USD 3 M diarios
        self.assertIn(thin.signal, BUY)
        self.assertLess(thin.size_mult, base.size_mult)

    def test_only_data_integrity_blocks(self):
        self.assertEqual(sp.read(build(FRESH, 7).iloc[-100:]).signal, "SIN DATOS")
        self.assertEqual(sp.read(build(FRESH, 7, volume=2_000)).signal, "NO OPERABLE")
        self.assertEqual(sp.read(build(FRESH, 7), fresh=False).signal, "DATOS VIEJOS")

    def test_public_payload_is_serializable(self):
        json.dumps(read(REBOUND_200, 7).public())


class IndicatorPerspectiveTests(unittest.TestCase):
    @staticmethod
    def mk(**kw):
        d = dict(rsi14=50, rsi_slope3=0, macd_hist_atr=0.0, macd_slope3_atr=0.0,
                 macd_hist_w_n=None, macd_slope_w_n=None)
        d.update(kw)
        return d

    def test_macd_negative_but_turning_up_is_not_the_same_as_falling(self):
        up = self.mk(macd_hist_atr=-0.10, macd_slope3_atr=0.12)
        down = self.mk(macd_hist_atr=-0.10, macd_slope3_atr=-0.12)
        self.assertGreater(sp._momentum(up), sp._momentum(down) + 0.12)

    def test_oversold_turning_up_scores_above_oversold_still_falling(self):
        self.assertGreater(sp._momentum(self.mk(rsi14=33, rsi_slope3=6)),
                           sp._momentum(self.mk(rsi14=33, rsi_slope3=-6)) + 0.05)

    def test_overbought_is_a_penalty_not_a_veto(self):
        hi = self.mk(rsi14=85, macd_hist_atr=0.2, macd_slope3_atr=0.05)
        ok = self.mk(rsi14=60, macd_hist_atr=0.2, macd_slope3_atr=0.05)
        self.assertLess(sp._momentum(hi), sp._momentum(ok))
        self.assertGreater(sp._momentum(hi), 0.2)


if __name__ == "__main__":
    unittest.main()
