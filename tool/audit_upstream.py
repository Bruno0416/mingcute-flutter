#!/usr/bin/env python3
"""Read-only upstream SVG support audit. Does not create or modify fonts."""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path
from sync_icons import ROOT, collect, convert_svg, dump_json, write_if_changed, fetch_upstream


def audit(source: Path):
    data=collect(source)
    summary={'accepted':{},'rejected':{},'examples':{}}
    for style,files in data.items():
        errors=Counter()
        samples=[]
        okay=0
        for name,(_,content) in files.items():
            try:
                convert_svg(content)
                okay+=1
            except Exception as exc:
                msg=str(exc)
                errors[msg]+=1
                samples.append({'icon':name,'reason':msg})
        summary['accepted'][style]=okay
        summary['rejected'][style]=dict(errors)
        summary['examples'][style]=samples[:50]
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path, help='Optional offline local checkout; otherwise automatically fetches upstream')
    p.add_argument('--ref', default='main', help='Upstream branch (only with automatic fetching)')
    p.add_argument('--output',type=Path,default=ROOT/'tool/source_audit.json')
    args=p.parse_args()
    source = args.source if args.source is not None else fetch_upstream(ROOT / 'tool/.cache/upstream', args.ref)
    result=audit(source)
    print('Supported SVGs:',result['accepted'])
    print('Rejected SVGs by reason:',result['rejected'])
    write_if_changed(args.output,dump_json(result))
    print('Audit report:',args.output)
    if any(result['rejected'].values()):
        raise SystemExit(1)
