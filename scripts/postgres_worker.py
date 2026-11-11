"""Simple multi-process PostgreSQL queue worker.

Handlers must be explicitly registered in this file. Unknown job kinds are failed rather
than silently discarded. Add domain handlers here as application workflows are migrated.
"""
from __future__ import annotations
import json, os, time, traceback
from src.jobs.postgres_queue import PostgresJobQueue

def dispatch(kind,payload):
    if kind=="health_check": return {"ok":True,"echo":payload}
    raise ValueError(f"No handler registered for job kind: {kind}")

def main():
    dsn=os.environ["SMARTGRID_POSTGRES_DSN"]
    queue=PostgresJobQueue(dsn)
    idle=float(os.getenv("WORKER_IDLE_SECONDS","2"))
    while True:
        job=queue.claim()
        if not job:
            time.sleep(idle); continue
        try: queue.finish(job["id"],dispatch(job["kind"],job["payload"]))
        except Exception as exc:
            queue.fail(job["id"],f"{type(exc).__name__}: {exc}")
            print(traceback.format_exc(),flush=True)

if __name__=="__main__": main()
