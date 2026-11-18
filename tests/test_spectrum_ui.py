import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class SpectralUITests(unittest.TestCase):
    def test_score_and_context_visible(self):
        js=(ROOT/'docs/app.js').read_text()
        for part in ('aria-valuenow','spectrumInfo(x)','r.frictions','r.narrative','r.size_mult','r.stage'):
            self.assertIn(part,js)
        self.assertNotIn('VETADO',js)
    def test_freshness_guard_preserved(self):
        js=(ROOT/'docs/app.js').read_text()
        self.assertIn('/3600000>36',js)
        self.assertIn("x.signal='DATOS VIEJOS'",js)

    def test_rendered_detail_uses_spectrum_and_escapes_text(self):
        import subprocess, json
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('docs/app.js','utf8').split('function openDetails')[0];
const ctx={document:{getElementById:()=>({})}};vm.createContext(ctx);vm.runInContext(source,ctx);
vm.runInContext(`dataset={macro:{state:'NEUTRAL'}};`,ctx);
const asset={ticker:'AAA',usa:'AAA',sector:'Tech',signal:'COMPRA CON PRECAUCIÓN',data:{rank_score:60,spectrum:{score_decision:60,stage:'RECUPERACIÓN FRESCA',size_mult:.4,deterioration:20,conviction:'MEDIA',frictions:['Balance cercano'],narrative:['<script>alert(1)</script>']}}};
ctx.asset=asset;const html=vm.runInContext("detailContent(asset,'asset')",ctx);
assert(html.includes('RECUPERACIÓN FRESCA'));assert(html.includes('Balance cercano'));
assert(html.includes('aria-valuenow="60"'));assert(!html.includes('<script>'));
assert(!html.includes('mínimo 62/100'));assert(html.includes('Tamaño'));
'''
        subprocess.run(['node','-e',script],cwd=ROOT,check=True,capture_output=True,text=True)
