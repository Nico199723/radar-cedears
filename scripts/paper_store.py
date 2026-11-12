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
from urllib.error import HTTPError
from urllib.parse import urlparse
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def artifact_zip(url:str,token:str)->bytes:
    """La API autoriza una sola vez; el ZIP está en una URL firmada externa.

    urllib redirige las cabeceras por defecto. Si se reenvía el Bearer de GitHub
    a Azure Blob, invalida la firma SAS y responde HTTP 401. No filtrar secretos.
    """
    if urlparse(url).scheme!="https" or urlparse(url).hostname!="api.github.com":
        raise ValueError("La URL original del artefacto debe ser la API de GitHub")
    request=urllib.request.Request(url,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"radar-cedears-paper-track"
    })
    opener=urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request,timeout=40) as response:
            data=response.read(2_000_001)
    except HTTPError as exc:
        if exc.code not in (301,302,303,307,308):
            raise
        signed=exc.headers.get("Location")
        if not signed:
            raise RuntimeError("GitHub no entregó URL firmada del artefacto")
        dest=urlparse(signed)
        host=dest.hostname or ""
        valid_host=(host.endswith(".blob.core.windows.net") or
                    host=="objects.githubusercontent.com" or
                    host.endswith(".githubusercontent.com"))
        if dest.scheme!="https" or not valid_host:
            raise ValueError("URL de descarga inesperada; nunca enviar token a terceros")
        # Sin Authorization: la URL SAS ya tiene su propia firma temporal.
        signed_request=urllib.request.Request(signed,headers={
            "User-Agent":"radar-cedears-paper-track"
        })
        with urllib.request.urlopen(signed_request,timeout=40) as response:
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
