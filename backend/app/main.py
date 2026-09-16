from fastapi import FastAPI,UploadFile,File,Form,HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime,timezone
import shutil,uuid
from .database import init_db,conn
app=FastAPI(title='慧眼安巡',version='0.1.0')
BASE=Path(__file__).resolve().parents[2]; FRONT=BASE/'frontend'; UP=BASE/'data/uploads/inspections'; UP.mkdir(parents=True,exist_ok=True)
init_db()
@app.on_event('startup')
def startup(): init_db()
app.mount('/assets',StaticFiles(directory=FRONT/'assets'),name='assets'); app.mount('/uploads',StaticFiles(directory=UP),name='uploads')
@app.get('/')
def index(): return FileResponse(FRONT/'index.html')
@app.get('/records')
def records_page(): return FileResponse(FRONT/'records.html')
@app.get('/report')
def report_page(): return FileResponse(FRONT/'report.html')
@app.post('/api/inspections')
async def create(scene:str=Form(...),image:UploadFile=File(...)):
 if scene not in ('dormitory','laboratory'): raise HTTPException(400,'不支持的场景')
 ext=Path(image.filename or '').suffix.lower() or '.jpg'; name=f'{uuid.uuid4().hex}{ext}'; path=UP/name
 with path.open('wb') as f: shutil.copyfileobj(image.file,f)
 now=datetime.now(timezone.utc).isoformat()
 with conn() as c:
  iid=c.execute('INSERT INTO inspections(scene,image_path,status,created_at,completed_at) VALUES(?,?,?,?,?)',(scene,name,'completed',now,now)).lastrowid
  c.execute('INSERT INTO hazards(inspection_id,name,location,evidence,risk,advice,regulation,source_url) VALUES(?,?,?,?,?,?,?,?)',(iid,'待人工确认的现场风险','照片中可见区域','演示模式已保存照片，尚未接入视觉模型，请结合现场复核。','提示','请由安全管理员现场确认后采取整改措施。','暂无已核验条款',''))
 return {'id':iid,'status':'completed'}
@app.get('/api/inspections')
def list_inspections():
 with conn() as c: return [dict(r) for r in c.execute('SELECT * FROM inspections ORDER BY id DESC')]
@app.get('/api/inspections/{iid}')
def get_inspection(iid:int):
 with conn() as c:
  i=c.execute('SELECT * FROM inspections WHERE id=?',(iid,)).fetchone(); hs=c.execute('SELECT * FROM hazards WHERE inspection_id=?',(iid,)).fetchall()
 if not i: raise HTTPException(404,'记录不存在')
 d=dict(i); d['hazards']=[dict(h) for h in hs]; return d
@app.get('/api/dashboard')
def dashboard():
 with conn() as c:
  total=c.execute('SELECT COUNT(*) n FROM inspections').fetchone()['n']; hazards=c.execute('SELECT COUNT(*) n FROM hazards').fetchone()['n']; risks=c.execute('SELECT risk,COUNT(*) n FROM hazards GROUP BY risk').fetchall()
 return {'total_inspections':total,'total_hazards':hazards,'risk_distribution':[dict(r) for r in risks]}
