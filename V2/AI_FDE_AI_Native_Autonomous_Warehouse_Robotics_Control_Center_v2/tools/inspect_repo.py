from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for p in sorted(ROOT.rglob('*')):
    if p.is_file(): print(p.relative_to(ROOT), p.stat().st_size)
