import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from score_history import update, publish, restore, validate


class ScoreHistoryTest(unittest.TestCase):
    def fixture(self, day='2026-11-25', score=0, version='v1'):
        return {'meta': {'rules_version': version, 'generated_at_utc': day+'T23:00:00+00:00', 'paper_snapshot_day': day},
                'assets': [{'ticker': 'NVDA', 'score_decision': score, 'signal': 'HOLD', 'data': {'date': day, 'score': 4, 'rank_score': 9}}],
                'sectors': [{'proxy': 'SMH', 'score_decision': 50, 'signal': 'HOLD', 'data': {'date': day}}]}

    def state(self):
        return {'schema': 1, 'series': {}}

    def test_zero_and_no_mutation_of_signals(self):
        d = self.fixture(); before = copy.deepcopy(d)
        state = update(self.state(), d)
        self.assertEqual(state['series']['assets-NVDA.json'][0]['score'], 0)
        self.assertEqual(d['assets'][0]['signal'], before['assets'][0]['signal'])
        self.assertIn('sectors-SMH.json', state['series'])

    def test_repeat_session_replaces_and_does_not_inflate(self):
        state = update(self.state(), self.fixture())
        update(state, self.fixture(score=2))
        self.assertEqual(len(state['series']['assets-NVDA.json']), 1)
        self.assertEqual(state['series']['assets-NVDA.json'][0]['score'], 2)

    def test_version_change_preserved(self):
        state = update(self.state(), self.fixture())
        update(state, self.fixture(score=80, version='v2'))
        self.assertEqual([p['version'] for p in state['series']['assets-NVDA.json']], ['v1', 'v2'])

    def test_regression_and_stale_not_appended(self):
        state = update(self.state(), self.fixture())
        update(state, self.fixture(day='2026-11-24'))
        d = self.fixture(day='2026-11-26'); d['assets'][0]['data']['date']='2026-11-25'
        update(state, d)
        self.assertEqual(len(state['series']['assets-NVDA.json']), 2)
        self.assertIsNone(state['series']['assets-NVDA.json'][-1]['score'])

    def test_missing_score_never_falls_back_to_old_technical_score(self):
        d = self.fixture(score=None);d['assets'][0]['data']['rank_score']=None
        state=update(self.state(),d)
        self.assertIsNone(state['series']['assets-NVDA.json'][0]['score'])

    def test_finite_safe_files_and_public_json(self):
        d = self.fixture(score=float('nan')); d['assets'][0]['ticker']='BRK/B'
        state = update(self.state(),d)
        with tempfile.TemporaryDirectory() as tmp:
            publish(state,d,tmp)
            raw=(Path(tmp)/'docs/scores/assets-BRK_B.json').read_text()
            self.assertNotIn('NaN',raw)
            self.assertIsNone(json.loads(raw)['points'][0]['score'])
            self.assertTrue((Path(tmp)/'.scores/score-history.json').exists())
        self.assertEqual(d['meta']['score_history']['mode'],'observed')

    def test_retention(self):
        from datetime import date, timedelta
        state=self.state()
        for i in range(95):update(state,self.fixture(day=(date(2026,1,1)+timedelta(days=i)).isoformat()))
        self.assertEqual(len(state['series']['assets-NVDA.json']),90)

    @patch.dict(os.environ, {'GITHUB_REPOSITORY':'owner/repo','GH_ACTIONS_TOKEN':'test'})
    @patch('score_history.api_get_json')
    def test_restore_first_run_and_expiry(self, api):
        api.return_value={'total_count':0,'artifacts':[]}
        self.assertEqual(restore(),self.state())
        api.return_value={'total_count':1,'artifacts':[]}
        with self.assertRaises(RuntimeError):restore()
        api.side_effect=OSError('offline')
        with self.assertRaises(OSError):restore()

    def test_restore_validates_archive(self):
        import io
        from zipfile import ZipFile
        payload=io.BytesIO()
        with ZipFile(payload,'w') as z:z.writestr('score-history.json',json.dumps(update(self.state(),self.fixture())))
        with patch.dict(os.environ,{'GITHUB_REPOSITORY':'r','GH_ACTIONS_TOKEN':'t'}), patch('score_history.api_get_json',return_value={'artifacts':[{'name':'radar-score-history-v1','created_at':'now','archive_download_url':'url'}]}), patch('score_history.artifact_zip',return_value=payload.getvalue()):
            self.assertEqual(restore()['series']['assets-NVDA.json'][0]['score'],0)
