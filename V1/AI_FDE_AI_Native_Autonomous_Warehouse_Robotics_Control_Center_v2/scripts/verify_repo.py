from pathlib import Path
import csv, json, sqlite3, py_compile, hashlib, sys
ROOT=Path(__file__).resolve().parents[1]
errors=[]
# no restricted role/private-key terminology in distributable text
banned='faci'+'litator'
for p in ROOT.rglob('*'):
    if p.is_file() and '.git' not in p.parts and p.suffix.lower() in {'.md','.txt','.json','.csv','.yaml','.yml','.toml','.py','.ini','.cfg'}:
        try:s=p.read_text(encoding='utf-8')
        except UnicodeDecodeError:continue
        if banned.lower() in s.lower(): errors.append(f'banned term: {p.relative_to(ROOT)}')
# Python syntax
for p in ROOT.rglob('*.py'):
    if '__pycache__' not in p.parts:
        try: py_compile.compile(str(p), doraise=True)
        except Exception as e: errors.append(f'compile {p.relative_to(ROOT)}: {e}')
# JSON parse
for p in ROOT.rglob('*.json'):
    try: json.loads(p.read_text(encoding='utf-8'))
    except Exception as e: errors.append(f'json {p.relative_to(ROOT)}: {e}')
# CSV rectangularity/nonempty headers
for p in ROOT.rglob('*.csv'):
    try:
        with p.open(newline='',encoding='utf-8-sig') as f:
            r=csv.reader(f); header=next(r,None)
            if not header or any(h=='' for h in header): errors.append(f'csv header {p.relative_to(ROOT)}')
            n=len(header or [])
            for i,row in enumerate(r,2):
                if len(row)!=n: errors.append(f'csv width {p.relative_to(ROOT)}:{i}'); break
    except Exception as e: errors.append(f'csv {p.relative_to(ROOT)}: {e}')
# SQLite integrity
for p in ROOT.rglob('*.db'):
    try:
        con=sqlite3.connect(p); result=con.execute('PRAGMA integrity_check').fetchone()[0]; con.close()
        if result!='ok': errors.append(f'sqlite {p.relative_to(ROOT)}: {result}')
    except Exception as e: errors.append(f'sqlite {p.relative_to(ROOT)}: {e}')
# Required release files
for rel in ['README.md','AGENTS.md','requirements.txt','pyproject.toml','Dockerfile','Makefile','data/manifest.json']:
    if not (ROOT/rel).exists(): errors.append(f'missing {rel}')
if errors:
    print('VERIFY_FAIL')
    for e in errors: print(e)
    sys.exit(1)
print('VERIFY_OK')
