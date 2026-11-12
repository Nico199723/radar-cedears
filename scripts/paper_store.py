"""Persistencia forward con artefactos GitHub Actions; NO commits ni claves públicas.

El GITHUB_TOKEN se lee solo de environment y nunca se escribe a docs/.
Se rechaza fallback silencioso si la API falla: hacerlo reiniciaría el historial.
Retención típica 90 días; sin corridas durante el período hay que restaurar
el último artifact manualmente; la aplicación NO debe inventar un historial.
"""
from __future__ import annotations
import io
import json
import logging
import os
from pathlib import Path
import urllib.request
from zipfile import ZipFile

ARTIFACT_NAME="radar-paper-ledger-v1"


def api_get_json(url:str,token:str)->dict:
    request=urllib.request.Request(url,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"radar-cedears-paper-track"
    })
    with urllib.request.urlopen(request,timeout=40) as response:
        return json.load(response)


def artifact_zip(url:str,token:str)->bytes:
    request=urllib.request.Request(url,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"radar-cedears-paper-track"
    })
    with urllib.request.urlopen(request,timeout=40) as response:
        data=response.read(2_000_001)
    if len(data)>2_000_000:
        raise ValueError("Snapshot del ledger inesperadamente grande")
    return data


def latest_state(repo:str,token:str)->dict | None:
    if not repo or not token:
        raise RuntimeError("Faltan GITHUB_REPOSITORY o GH_ACTIONS_TOKEN: no reiniciar historial")
    url=f"https://api.github.com/repos/{repo}/actions/artifacts?name={ARTIFACT_NAME}&per_page=50"
    answer=api_get_json(url,token)
    all_items=answer.get("artifacts",[])
    valid=[x for x in all_items if x.get("name")==ARTIFACT_NAME and not x.get("expired")]
    if not valid:
        if answer.get("total_count",0)>0:
            raise RuntimeError("Snapshots anteriores expirados: restaurar backup; NO reiniciar simulado")
        return None
    valid.sort(key=lambda x:x.get("created_at",""),reverse=True)
    for item in valid:
        try:
            raw=artifact_zip(item["archive_download_url"],token)
            with ZipFile(io.BytesIO(raw)) as z:
                names=[n for n in z.namelist() if n.endswith("ledger.json") and ".." not in n]
                if not names:raise ValueError("Falta ledger.json")
                with z.open(names[0]) as fh:
                    state=json.load(fh)
            from paper_sim import check_ledger
            check_ledger(state)
            return state
        except Exception as exc:
            logging.error("No se pudo restaurar artefacto %s: %s",item.get("id"),exc)
    raise RuntimeError("Hay snapshots pero ninguno legible: NO reiniciar contador a USD 2.000")


def load_or_initialize(latest_day:str,now_iso:str)->dict:
    from paper_sim import new_ledger
    repo=os.getenv("GITHUB_REPOSITORY")
    token=os.getenv("GH_ACTIONS_TOKEN")
    state=latest_state(repo,token)
    if state is None:
        logging.warning("Nuevo track record forward desde %s (sin operaciones previas)",latest_day)
        return new_ledger(latest_day,now_iso)
    if state["last_session"]>latest_day:
        raise RuntimeError("OHLC de SPY retrocedió respecto al ledger; NO sobrescribir con datos viejos")
    return state
