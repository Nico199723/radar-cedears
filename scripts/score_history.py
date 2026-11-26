"""Observed decision scores only; presentation state never feeds the signal engine."""
import io
import json
import math
import os
from datetime import date
from pathlib import Path
from zipfile import ZipFile
from chart_data import chart_filename
from paper_store import api_get_json, artifact_zip

ARTIFACT = 'radar-score-history-v1'
LIMIT = 90


def validate(state):
    if state.get('schema') != 1 or not isinstance(state.get('series'), dict):
        raise ValueError('Historial de puntajes inválido; no reiniciar')
    for points in state['series'].values():
        if not isinstance(points, list) or len(points) > LIMIT:
            raise ValueError('Serie inválida')
        for p in points:
            date.fromisoformat(p['date'])
            score = p['score']
            if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100):
                raise ValueError('Puntaje inválido')
            if not isinstance(p['version'], str) or not isinstance(p['signal'], str):
                raise ValueError('Metadatos inválidos')
    return state


def restore():
    repo, token = os.getenv('GITHUB_REPOSITORY'), os.getenv('GH_ACTIONS_TOKEN')
    if not repo or not token:
        raise RuntimeError('Faltan credenciales de persistencia; no reiniciar historial')
    answer = api_get_json(f'https://api.github.com/repos/{repo}/actions/artifacts?name={ARTIFACT}&per_page=50', token)
    items = sorted((x for x in answer.get('artifacts', []) if x.get('name') == ARTIFACT and not x.get('expired')), key=lambda x: x['created_at'], reverse=True)
    if not items:
        if answer.get('total_count', 0):
            raise RuntimeError('Historial expirado: restaurar backup')
        return {'schema': 1, 'series': {}}
    # Fail rather than quietly reverting to an older, incomplete series.
    with ZipFile(io.BytesIO(artifact_zip(items[0]['archive_download_url'], token))) as z:
        return validate(json.loads(z.read('score-history.json')))


def update(state, dataset):
    validate(state)
    version = dataset['meta']['rules_version']
    observed = dataset['meta']['generated_at_utc']
    latest = dataset['meta']['paper_snapshot_day']
    for group, key in [('assets', 'ticker'), ('sectors', 'proxy')]:
        for row in dataset.get(group, []):
            name = chart_filename(row.get(key))
            if name is None:
                continue
            name = group + '-' + name
            row['score_history_file'] = name
            series = state['series'].setdefault(name, [])
            data = row.get('data') or {}
            session = latest
            fresh = data.get('date') == latest
            date.fromisoformat(session)
            score = row.get('score_decision')
            if score is None:
                score = data.get('rank_score')
            if not fresh or isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100:
                score = None
            point = {'date': session, 'score': score, 'version': version,
                     'signal': row.get('signal', 'SIN DATOS'), 'observed_at': observed}
            if series and session < series[-1]['date']:
                continue
            if series and (session, version) == (series[-1]['date'], series[-1]['version']):
                series[-1] = point  # Latest published observation for this complete candle.
            else:
                series.append(point)
            state['series'][name] = series[-LIMIT:]
    return validate(state)


def publish(state, dataset, root):
    root = Path(root)
    folder = root / 'docs' / 'scores'
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('*.json'):
        old.unlink()
    for name, points in state['series'].items():
        if Path(name).name != name:
            raise ValueError('Nombre de historial inválido')
        (folder / name).write_text(json.dumps({'points': points}, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    path = root / '.scores' / 'score-history.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(path)
    dataset['meta']['score_history'] = {'path': './scores/', 'observations': LIMIT,
        'mode': 'observed', 'count': len(state['series'])}
