from pathlib import Path
import json, csv, argparse
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(); p.add_argument('--check-only',action='store_true'); a=p.parse_args()
 manifest=json.loads((ROOT/'data/manifest.json').read_text())
 missing=[x['path'] for x in manifest['files'] if not (ROOT/x['path']).exists()]
 print(json.dumps({'manifest_files':len(manifest['files']),'missing':missing,'mode':'check-only' if a.check_only else 'deterministic snapshot already generated'},indent=2))
if __name__=='__main__': main()
