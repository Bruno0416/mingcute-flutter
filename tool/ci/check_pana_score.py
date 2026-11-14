#!/usr/bin/env python3
"""Require pana's exact full score (160/160) from a ``pana --json`` report.

Fails closed: missing/empty/invalid JSON, a missing score, a maximum other than
160 (pub.dev changed its model: stop and review, never lower the bar) and any
granted < max all block. Usage: check_pana_score.py REPORT.json
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

EXPECTED_MAX = 160


def check(report_text: str) -> str:
    if not report_text.strip():
        raise ValueError('pana produced no output')
    start = report_text.find('{')
    try:
        report = json.loads(report_text[start:] if start >= 0 else report_text)
    except ValueError as exc:
        raise ValueError(f'pana output is not valid JSON: {exc}') from exc
    scores = report.get('scores') if isinstance(report, dict) else None
    if not isinstance(scores, dict) or not isinstance(scores.get('grantedPoints'), int) \
            or not isinstance(scores.get('maxPoints'), int):
        raise ValueError('pana report has no grantedPoints/maxPoints (incomplete run)')
    granted, maximum = scores['grantedPoints'], scores['maxPoints']
    if maximum != EXPECTED_MAX:
        raise ValueError(f'pana maxPoints is {maximum}, expected {EXPECTED_MAX}: the pub.dev scoring model changed; review before continuing')
    if granted != maximum:
        sections = report.get('report', {}).get('sections', []) if isinstance(report.get('report'), dict) else []
        lost = [f"{s.get('title')}: {s.get('grantedPoints')}/{s.get('maxPoints')}"
                for s in sections if s.get('grantedPoints') != s.get('maxPoints')]
        raise ValueError(f'pana score {granted}/{maximum}; below 160/160. Sections: {"; ".join(lost) or "unknown"}')
    return f'{granted}/{maximum}'


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('usage: check_pana_score.py REPORT.json', file=sys.stderr)
        return 2
    try:
        print(f'PASS: pana {check(Path(argv[1]).read_text(encoding="utf-8"))}')
        return 0
    except (OSError, ValueError) as exc:
        print(f'Pana score gate FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
