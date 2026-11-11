"""Optional PostgreSQL job queue for multi-worker deployments (requires psycopg)."""
from __future__ import annotations
import json, uuid
from datetime import datetime, timezone

class PostgresJobQueue:
    def __init__(self, dsn: str):
        if not dsn: raise ValueError("PostgreSQL DSN is required")
        try: import psycopg
        except ImportError as exc: raise RuntimeError("Install psycopg[binary] to use PostgresJobQueue") from exc
        self.psycopg=psycopg; self.dsn=dsn
        with self.psycopg.connect(self.dsn) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS smartgrid_jobs(
              id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload JSONB NOT NULL,status TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,
              attempts INT NOT NULL DEFAULT 0,result JSONB,error TEXT)""")
            db.execute("CREATE INDEX IF NOT EXISTS smartgrid_jobs_status_created ON smartgrid_jobs(status,created_at)")
    @staticmethod
    def now(): return datetime.now(timezone.utc)
    def enqueue(self,kind,payload):
        if not kind.strip(): raise ValueError("job kind is required")
        jid=uuid.uuid4().hex; now=self.now()
        with self.psycopg.connect(self.dsn) as db:
            db.execute("INSERT INTO smartgrid_jobs(id,kind,payload,status,created_at,updated_at) VALUES(%s,%s,%s,'queued',%s,%s)",
                       (jid,kind,json.dumps(payload),now,now))
        return self.get(jid)
    def claim(self):
        now=self.now()
        with self.psycopg.connect(self.dsn) as db:
            row=db.execute("""SELECT id,kind,payload,attempts FROM smartgrid_jobs WHERE status='queued'
                              ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
            if not row: return None
            db.execute("UPDATE smartgrid_jobs SET status='running',attempts=attempts+1,updated_at=%s WHERE id=%s",(now,row[0]))
            return {"id":row[0],"kind":row[1],"payload":row[2],"attempts":row[3]+1,"status":"running"}
    def finish(self,jid,result):
        with self.psycopg.connect(self.dsn) as db:
            cur=db.execute("UPDATE smartgrid_jobs SET status='completed',result=%s,updated_at=%s WHERE id=%s AND status='running'",
                           (json.dumps(result),self.now(),jid))
            if cur.rowcount!=1: raise ValueError("job does not exist or is not running")
        return self.get(jid)
    def fail(self,jid,error):
        with self.psycopg.connect(self.dsn) as db:
            cur=db.execute("UPDATE smartgrid_jobs SET status='failed',error=%s,updated_at=%s WHERE id=%s AND status='running'",
                           (str(error)[:2000],self.now(),jid))
            if cur.rowcount!=1: raise ValueError("job does not exist or is not running")
        return self.get(jid)
    def get(self,jid):
        with self.psycopg.connect(self.dsn) as db:
            row=db.execute("SELECT id,kind,payload,status,created_at,updated_at,attempts,result,error FROM smartgrid_jobs WHERE id=%s",(jid,)).fetchone()
        if not row:return None
        keys=["id","kind","payload","status","created_at","updated_at","attempts","result","error"]
        return dict(zip(keys,row))
