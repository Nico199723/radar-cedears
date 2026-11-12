"""Descarga segura del ledger: GitHub Bearer nunca llega a storage de Azure."""
import io
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from paper_store import artifact_zip


class FakeResponse:
    def __init__(self, value):
        self.value=value
    def read(self, size):
        return self.value
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class ArtifactDownloadTests(unittest.TestCase):
    def test_bearer_is_not_forwarded_to_azure_signed_zip(self):
        url="https://api.github.com/repos/Nico199723/radar-cedears/actions/artifacts/1/zip"
        dest="https://production-results.blob.core.windows.net/results/ledger.zip?sig=abc"
        captured={}
        class RedirectOpener:
            def open(self,request,timeout=None):
                captured["github_auth"]=request.get_header("Authorization")
                raise HTTPError(url,302,"Redirect",{"Location":dest},None)
        def fake_download(request, timeout=None):
            captured["blob_auth"]=request.get_header("Authorization")
            captured["blob_url"]=request.full_url
            return FakeResponse(b"test zip")
        with patch("paper_store.urllib.request.build_opener",return_value=RedirectOpener()),patch(
             "paper_store.urllib.request.urlopen",side_effect=fake_download):
            data=artifact_zip(url,"local-fake-token")
        self.assertEqual(data,b"test zip")
        self.assertEqual(captured["github_auth"],"Bearer local-fake-token")
        self.assertIsNone(captured["blob_auth"])
        self.assertEqual(captured["blob_url"],dest)

    def test_reject_unknown_signed_host(self):
        url="https://api.github.com/repos/Nico199723/radar-cedears/actions/artifacts/1/zip"
        class RedirectOpener:
            def open(self,request,timeout=None):
                raise HTTPError(url,302,"Redirect",
                                {"Location":"https://attacker.example/file.zip"},None)
        with patch("paper_store.urllib.request.build_opener",return_value=RedirectOpener()):
            with self.assertRaises(ValueError):
                artifact_zip(url,"local-fake-token")

    def test_refuse_non_github_initial_url(self):
        with self.assertRaises(ValueError):
            artifact_zip("https://attacker.example/ledger.zip","token")


if __name__=="__main__":
    unittest.main()
