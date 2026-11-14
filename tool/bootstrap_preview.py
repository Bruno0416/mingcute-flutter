#!/usr/bin/env python3
"""Prepare a real Linux/Web Flutter preview runner, then optionally launch it.

Safe to repeat. Never overwrites existing Flutter sources or generated icon data.
Requires the installed Flutter SDK; native runner is made by flutter create, not
copied from a different Flutter version or platform.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from repair_project import migrate
from sync_icons import ROOT


def run_command(argv: list[str], working_dir: Path) -> None:
    print('+ ' + ' '.join(argv), flush=True)
    subprocess.run(argv, cwd=working_dir, check=True)


def prepare(root: Path = ROOT, *, device: str = 'linux', launch: bool = True) -> None:
    root = root.resolve()
    preview = root / 'preview'
    if device not in ('linux', 'chrome'):
        raise ValueError('Supported preview devices are linux and chrome')
    if shutil.which('flutter') is None:
        raise RuntimeError('Flutter CLI not in PATH. Check `flutter doctor -v` and try again.')
    migrate(root)
    if not (preview / 'lib/main.dart').exists():
        raise FileNotFoundError('Preview sources are missing.')
    if not (preview / 'linux/CMakeLists.txt').exists() or not (preview / 'web/index.html').exists():
        run_command(['flutter', 'create', '--no-pub', '--platforms=linux,web',
                     '--project-name=mingcute_flutter_preview', '.'], preview)
    run_command(['flutter', 'pub', 'get'], preview)
    if launch:
        run_command(['flutter', 'run', '-d', device], preview)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device', choices=['linux', 'chrome'], default='linux')
    p.add_argument('--prepare-only', action='store_true', help='Create runners and resolve dependencies without launching')
    p.add_argument('--output', type=Path, default=ROOT, help='Flutter package root')
    args = p.parse_args()
    prepare(args.output, device=args.device, launch=not args.prepare_only)


if __name__ == '__main__':
    main()
