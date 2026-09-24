from pathlib import Path
import csv, sqlite3
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DB = DATA / "warehouse_legacy.db"

def csv_rows(name: str):
    p = DATA / "raw" / name
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))

def query(sql: str, params=()):
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(sql, params).fetchall()]
