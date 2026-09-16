from pathlib import Path
import sqlite3
BASE=Path(__file__).resolve().parents[2]; DB=BASE/'data'/'app.db'
DB.parent.mkdir(parents=True,exist_ok=True)
def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
 with conn() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS inspections(id INTEGER PRIMARY KEY AUTOINCREMENT,scene TEXT NOT NULL,image_path TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,completed_at TEXT,error TEXT); CREATE TABLE IF NOT EXISTS hazards(id INTEGER PRIMARY KEY AUTOINCREMENT,inspection_id INTEGER,name TEXT,location TEXT,evidence TEXT,risk TEXT,advice TEXT,regulation TEXT,source_url TEXT); CREATE TABLE IF NOT EXISTS regulations(id TEXT PRIMARY KEY,scene TEXT,document_title TEXT,article TEXT,content TEXT,source_url TEXT);''')
