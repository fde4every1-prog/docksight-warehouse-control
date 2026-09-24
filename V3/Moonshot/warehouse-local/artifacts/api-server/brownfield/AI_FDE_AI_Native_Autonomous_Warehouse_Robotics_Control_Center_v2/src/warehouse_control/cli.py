import json, argparse
from warehouse_control.diagnostics import run

def main():
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['diagnostics']); a=p.parse_args()
    if a.command=='diagnostics': print(json.dumps(run(),indent=2))
if __name__=='__main__': main()
