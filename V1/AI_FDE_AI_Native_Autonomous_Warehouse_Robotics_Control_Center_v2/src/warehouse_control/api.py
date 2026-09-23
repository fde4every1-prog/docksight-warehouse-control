from fastapi import FastAPI
from warehouse_control.diagnostics import run
from warehouse_control.repository import query
app=FastAPI(title="Synthetic Warehouse Control Center Brownfield API",version='2.0.0')
@app.get('/health')
def health(): return {'status':'ok','physical_control':'disabled'}
@app.get('/diagnostics')
def diagnostics(): return run()
@app.get('/robots/{robot_id}')
def robot(robot_id:str):
    rows=query('select * from robots where robot_id=?',(robot_id,))
    return rows[0] if rows else {'error':'not_found'}
