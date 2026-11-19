"""Calendario de balances: cobertura del universo, caché, respaldo y etiquetas. Sin red."""
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import earnings_calendar as ec  # noqa: E402

TODAY = date(2026, 11, 13)  # viernes
NO_SLEEP = lambda s: None


def payload(*rows):
    return {"data": {"asOf": "x", "rows": [
        {"symbol": s, "time": t, "fiscalQuarterEnding": "Oct/2026"} for s, t in rows] or None},
        "status": {"rCode": 200}}


def asset(sym, sector="Software y cloud", kind="ACCION"):
    return {"ticker": sym, "usa": sym, "sector": sector, "data": {"asset_kind": kind}}


def nasdaq_from(table):
    """table: {date: [(symbol, time-string), ...]}"""
    def fetch(d):
        return payload(*table.get(d, []))
    return fetch


class ParseTests(unittest.TestCase):
    def test_parse_rows_and_time_labels(self):
        p = payload(("CSCO", "time-after-hours"), ("BRK.B", "time-pre-market"), ("XYZ", "time-not-supplied"))
        out = ec.parse_nasdaq(p, date(2026, 11, 18))
        self.assertEqual(out["CSCO"]["time"], "AMC")
        self.assertEqual(out["BRK-B"]["time"], "BMO")
        self.assertIsNone(out["XYZ"]["time"])
        self.assertEqual(out["CSCO"]["date"], "2026-11-18")

    def test_parse_empty_or_malformed(self):
        self.assertEqual(ec.parse_nasdaq({"data": {"rows": None}}, TODAY), {})
        self.assertEqual(ec.parse_nasdaq(None, TODAY), {})
        self.assertEqual(ec.parse_nasdaq({"data": {"rows": [{"symbol": ""}]}}, TODAY), {})

    def test_business_days_skip_weekends(self):
        days = ec.business_days(TODAY, 4)   # vie 13, lun 16, mar 17, mié 18
        self.assertEqual([d.day for d in days], [13, 16, 17, 18])


class CollectTests(unittest.TestCase):
    def test_earliest_date_wins(self):
        table = {date(2026, 11, 16): [("AAA", "time-pre-market")], date(2026, 11, 20): [("AAA", None), ("BBB", None)]}
        found, st = ec.collect_nasdaq(TODAY, 10, nasdaq_from(table), 0, NO_SLEEP)
        self.assertEqual(found["AAA"]["date"], "2026-11-16")
        self.assertEqual(found["BBB"]["date"], "2026-11-20")
        self.assertEqual(st["nasdaq_days_ok"], 10)

    def test_aborts_after_consecutive_failures(self):
        calls = []

        def boom(d):
            calls.append(d)
            raise OSError("403")
        found, st = ec.collect_nasdaq(TODAY, 20, boom, 0, NO_SLEEP)
        self.assertEqual(found, {})
        self.assertTrue(st["nasdaq_aborted"])
        self.assertEqual(len(calls), ec.MAX_CONSECUTIVE_FAILS)


class UniverseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = str(Path(self.tmp.name) / "earnings.json")
        self.assets = [asset("AAA"), asset("BBB"), asset("CCC"), asset("SPY", "Índices y ETFs", "ETF / INDICE / NO CLASIFICADO")]
        self.table = {date(2026, 11, 17): [("AAA", "time-after-hours")], date(2026, 11, 30): [("BBB", "time-pre-market")]}

    def tearDown(self):
        self.tmp.cleanup()

    def run_it(self, today=TODAY, yahoo=None, table=None, **kw):
        args = dict(fetch_nasdaq=nasdaq_from(self.table if table is None else table),
                    fetch_yahoo_fn=yahoo or (lambda s, t: None),
                    days_ahead=20, pause=0, sleep=NO_SLEEP)
        args.update(kw)
        return ec.earnings_for_universe(self.assets, today, self.cache, **args)

    def test_covers_universe_with_nasdaq_yahoo_and_skips_etfs(self):
        asked = []

        def yahoo(sym, today):
            asked.append(sym)
            return {"date": "2026-12-10", "time": None, "fiscal_quarter": None}
        res, cov = self.run_it(yahoo=yahoo)
        self.assertEqual(asked, ["CCC"])                       # sólo el que Nasdaq no trajo
        self.assertNotIn("SPY", res)                           # ETF: no se consulta
        self.assertEqual(res["AAA"]["days_until"], 4)
        self.assertEqual(res["AAA"]["time_label"], "después del cierre")
        self.assertEqual(res["CCC"]["source"], "Yahoo (calendario gratuito)")
        self.assertEqual((cov["stocks"], cov["etfs"], cov["with_date"]), (3, 1, 3))
        self.assertEqual((cov["from_nasdaq"], cov["from_yahoo"], cov["within_14_days"]), (2, 1, 1))
        self.assertEqual(cov["not_consulted"], 0)

    def test_cache_avoids_requery_and_survives_source_failure(self):
        self.run_it(yahoo=lambda s, t: {"date": "2026-12-10", "time": None, "fiscal_quarter": None})
        asked = []
        res, cov = self.run_it(today=TODAY + timedelta(days=1), table={},
                               yahoo=lambda s, t: asked.append(s))
        self.assertEqual(asked, [])                            # AAA y BBB se leen del caché
        self.assertEqual(res["CCC"]["date"], "2026-12-10")
        self.assertEqual(cov["from_cache"], 3)
        self.assertTrue(all(v for v in res.values()))

    def test_failing_yahoo_keeps_old_date_marked_stale(self):
        self.run_it(yahoo=lambda s, t: {"date": "2026-12-20", "time": None, "fiscal_quarter": None})

        def broken(s, t):
            raise RuntimeError("429")
        res, cov = self.run_it(today=TODAY + timedelta(days=9), table={}, yahoo=broken)
        self.assertEqual(res["CCC"]["date"], "2026-12-20")     # no se pierde la fecha buena
        self.assertTrue(res["CCC"]["stale"])
        self.assertGreaterEqual(cov["yahoo_errors"], 1)
        self.assertEqual(ec.balance_label(res["CCC"], True), "PRÓXIMO BALANCE · DATO DE CACHÉ")

    def test_no_date_is_remembered_then_retried(self):
        asked = []
        res, _ = self.run_it(yahoo=lambda s, t: asked.append(s))
        self.assertIsNone(res["CCC"])                          # consultado y sin fecha
        self.assertIn("CCC", res)
        asked.clear()
        self.run_it(today=TODAY + timedelta(days=2), table={}, yahoo=lambda s, t: asked.append(s))
        self.assertNotIn("CCC", asked)                         # dentro de 3 días: no insistir
        asked.clear()
        self.run_it(today=TODAY + timedelta(days=5), table={}, yahoo=lambda s, t: asked.append(s))
        self.assertIn("CCC", asked)                            # pasados 3 días: reintento

    def test_cap_and_priority(self):
        self.assets = [asset(s) for s in ("A1", "A2", "A3", "A4", "A5")]
        asked = []
        res, cov = self.run_it(table={}, yahoo=lambda s, t: asked.append(s), max_yahoo=2, priority={"A4", "A5"})
        self.assertEqual(sorted(asked), ["A4", "A5"])
        self.assertEqual(cov["not_consulted"], 3)
        self.assertNotIn("A1", res)
        self.assertEqual(ec.balance_label(None, "A1" in res), "FECHA NO CONSULTADA")

    def test_nearby_date_is_refreshed_daily_far_date_weekly(self):
        cache = {"AAA": {"date": "2026-11-20", "time": None, "source": "Yahoo", "fetched_at": "2026-11-11"},
                 "BBB": {"date": "2026-12-20", "time": None, "source": "Yahoo", "fetched_at": "2026-11-11"}}
        Path(self.cache).write_text(json.dumps({"version": 1, "entries": cache}), encoding="utf-8")
        self.assets = [asset("AAA"), asset("BBB")]
        asked = []
        self.run_it(table={}, yahoo=lambda s, t: asked.append(s))
        self.assertEqual(asked, ["AAA"])                       # cercana (7 d) y vieja: se reconsulta; lejana no

    def test_past_cached_date_is_never_shown(self):
        cache = {"AAA": {"date": "2026-11-01", "time": None, "source": "Nasdaq", "fetched_at": "2026-10-20"}}
        Path(self.cache).write_text(json.dumps({"version": 1, "entries": cache}), encoding="utf-8")
        self.assets = [asset("AAA")]
        res, _ = self.run_it(table={}, yahoo=lambda s, t: (_ for _ in ()).throw(RuntimeError("x")))
        self.assertNotIn("AAA", res)                           # sin fecha futura válida: "no consultada", no inventar


class LabelTests(unittest.TestCase):
    def test_labels(self):
        e = lambda n, stale=False: {"days_until": n, "stale": stale}
        self.assertEqual(ec.balance_label(None, False, is_etf=True), "ETF · SIN BALANCES")
        self.assertEqual(ec.balance_label(None, False), "FECHA NO CONSULTADA")
        self.assertEqual(ec.balance_label(None, True), "SIN FECHA PUBLICADA")
        self.assertEqual(ec.balance_label(e(3), True), "BALANCE <=7 DÍAS")
        self.assertEqual(ec.balance_label(e(12), True), "BALANCE <=14 DÍAS")
        self.assertEqual(ec.balance_label(e(40), True), "PRÓXIMO BALANCE")


if __name__ == "__main__":
    unittest.main()
