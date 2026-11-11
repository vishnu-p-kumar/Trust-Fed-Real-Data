"""Local append-only hash-linked ledger baseline; not a distributed blockchain."""
from __future__ import annotations
import hashlib, json, sqlite3, time
from pathlib import Path

class HashLinkedLedger:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS blocks (height INTEGER PRIMARY KEY, timestamp REAL NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL, block_hash TEXT NOT NULL UNIQUE)")
    @staticmethod
    def _hash(height,timestamp,payload,previous):
        raw=json.dumps({"height":height,"timestamp":timestamp,"payload":json.loads(payload),"previous_hash":previous},sort_keys=True,separators=(",",":"))
        return hashlib.sha256(raw.encode()).hexdigest()
    def append(self,payload):
        body=json.dumps(payload,sort_keys=True,separators=(",",":"))
        with sqlite3.connect(self.path) as db:
            row=db.execute("SELECT height,block_hash FROM blocks ORDER BY height DESC LIMIT 1").fetchone()
            height=0 if row is None else row[0]+1; previous="0"*64 if row is None else row[1]
            ts=time.time(); digest=self._hash(height,ts,body,previous)
            db.execute("INSERT INTO blocks VALUES(?,?,?,?,?)",(height,ts,body,previous,digest))
        return {"height":height,"hash":digest}
    def verify(self):
        with sqlite3.connect(self.path) as db: rows=db.execute("SELECT height,timestamp,payload,previous_hash,block_hash FROM blocks ORDER BY height").fetchall()
        previous="0"*64
        for expected,(height,ts,payload,prev,digest) in enumerate(rows):
            if height!=expected or prev!=previous or self._hash(height,ts,payload,prev)!=digest: return False
            previous=digest
        return True
    def records(self):
        with sqlite3.connect(self.path) as db: rows=db.execute("SELECT height,timestamp,payload,previous_hash,block_hash FROM blocks ORDER BY height").fetchall()
        return [{"height":h,"timestamp":t,"payload":json.loads(p),"previous_hash":ph,"hash":d} for h,t,p,ph,d in rows]
