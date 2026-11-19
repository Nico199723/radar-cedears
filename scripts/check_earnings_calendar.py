"""Corrida real del calendario sin publicar Pages, recalcular señales ni tocar paper."""
import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from actualizar import read_catalog, ETF_SYMBOLS, ROOT, NY_TZ
from earnings_calendar import earnings_for_universe


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',default=str(ROOT/'.cache'/'earnings.json'))
    p.add_argument('--out',default=str(ROOT/'backtest-out'/'earnings-check.json'))
    p.add_argument('--snapshot',help='Snapshot técnico vigente opcional para priorizar candidatos')
    args=p.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    now=datetime.now(timezone.utc); priority=set()
    if args.snapshot:
        snapshot=json.loads(Path(args.snapshot).read_text())
        stamp=datetime.fromisoformat(snapshot['meta']['generated_at_utc'])
        if stamp.tzinfo is None or not 0<=(now-stamp).total_seconds()<=36*3600:
            raise ValueError('Snapshot técnico sin vigencia (36h)')
        priority={a['usa'] for a in snapshot.get('assets',[]) if a.get('usa') and
                  ((a.get('data') or {}).get('score') or 0)>=65}
    assets=[{'ticker':a['cedear'],'usa':a['subyacente_usa'],'sector':a['sector'],
             'earnings_is_etf':a['subyacente_usa'] in ETF_SYMBOLS or a['sector']=='Índices y ETFs'}
            for a in read_catalog()]
    logging.info('Calendario real: %d instrumentos, %d prioritarios; no publica ni toca paper',len(assets),len(priority))
    dates,coverage=earnings_for_universe(assets,now.astimezone(NY_TZ).date(),args.cache,priority=priority)
    result={'as_of':now.isoformat(),'coverage':coverage,'earnings':dates}
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps(coverage,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
