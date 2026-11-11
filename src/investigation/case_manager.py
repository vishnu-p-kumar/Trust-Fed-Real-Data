"""SQLite-backed investigation case workflow for meter-level review."""
from __future__ import annotations
import json, sqlite3, time, uuid
from pathlib import Path

class CaseManager:
    STATUSES={"open","assigned","investigating","awaiting_evidence","resolved","closed"}
    PRIORITIES={"low","medium","high","critical"}
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS cases(
              case_id TEXT PRIMARY KEY,meter_id TEXT NOT NULL,client_id TEXT,priority TEXT NOT NULL,
              status TEXT NOT NULL,assignee TEXT,summary TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS case_events(
              event_id INTEGER PRIMARY KEY AUTOINCREMENT,case_id TEXT NOT NULL,event_type TEXT NOT NULL,
              actor TEXT NOT NULL,payload TEXT NOT NULL,created_at REAL NOT NULL,
              FOREIGN KEY(case_id) REFERENCES cases(case_id))""")
    def create(self,meter_id,summary,*,client_id=None,priority="medium",actor="system"):
        if not meter_id or not summary or priority not in self.PRIORITIES: raise ValueError("meter_id, summary and valid priority are required")
        now=time.time(); cid=str(uuid.uuid4())
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO cases VALUES(?,?,?,?,?,?,?,?,?)",(cid,meter_id,client_id,priority,"open",None,summary,now,now))
            db.execute("INSERT INTO case_events(case_id,event_type,actor,payload,created_at) VALUES(?,?,?,?,?)",(cid,"created",actor,"{}",now))
        return self.get(cid)
    def update(self,case_id,*,status=None,assignee=None,priority=None,actor="system",note=None):
        if status is not None and status not in self.STATUSES: raise ValueError("invalid case status")
        if priority is not None and priority not in self.PRIORITIES: raise ValueError("invalid priority")
        with sqlite3.connect(self.path) as db:
            row=db.execute("SELECT status,assignee,priority FROM cases WHERE case_id=?",(case_id,)).fetchone()
            if row is None: raise KeyError(case_id)
            new=(status or row[0],assignee if assignee is not None else row[1],priority or row[2])
            db.execute("UPDATE cases SET status=?,assignee=?,priority=?,updated_at=? WHERE case_id=?",(*new,time.time(),case_id))
            payload=json.dumps({"status":new[0],"assignee":new[1],"priority":new[2],"note":note})
            db.execute("INSERT INTO case_events(case_id,event_type,actor,payload,created_at) VALUES(?,?,?,?,?)",(case_id,"updated",actor,payload,time.time()))
        return self.get(case_id)
    def get(self,case_id):
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM cases WHERE case_id=?",(case_id,)).fetchone()
            if row is None: raise KeyError(case_id)
            result=dict(row)
            result["events"]=[dict(r) for r in db.execute("SELECT * FROM case_events WHERE case_id=? ORDER BY event_id",(case_id,))]
        return result
    def list(self,*,status=None,client_id=None):
        query="SELECT * FROM cases WHERE 1=1"; args=[]
        if status: query+=" AND status=?"; args.append(status)
        if client_id: query+=" AND client_id=?"; args.append(client_id)
        query+=" ORDER BY updated_at DESC"
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute(query,args)]
