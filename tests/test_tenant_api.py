import asyncio
from fastapi.testclient import TestClient
from api import main as api_main

async def idle():
    while True: await asyncio.sleep(60)

def test_admin_creates_client_and_client_has_isolated_session(tmp_path,monkeypatch):
    monkeypatch.setenv("SMARTGRID_SESSION_SECRET","x"*48)
    monkeypatch.setenv("SMARTGRID_COOKIE_SECURE","0")
    monkeypatch.setenv("TRUSTFED_DB_PATH",str(tmp_path/"api_clients.sqlite3"))
    monkeypatch.setattr(api_main.runtime,"bootstrap",lambda:None)
    monkeypatch.setattr(api_main.runtime,"send_telegram_status",lambda *a,**k:{"status":"skipped"})
    monkeypatch.setattr(api_main.runtime,"simulation_loop",idle)
    with TestClient(api_main.app) as admin:
        monkeypatch.setattr(api_main,"_require_role",lambda req,role:{"role":role})
        created=admin.post("/api/clients",json={"organization":"North Utility","name":"Client Admin",
          "email":"north@example.com","username":"north","password":"StrongPass12345","region":"Karnataka","location":"Bengaluru"})
        assert created.status_code==200,created.text
        client=created.json()["client"]
        monkeypatch.undo()
        # Restore test-only startup stubs and authenticate through the real client login.
        monkeypatch.setenv("SMARTGRID_SESSION_SECRET","x"*48)
        monkeypatch.setenv("SMARTGRID_COOKIE_SECURE","0")
        monkeypatch.setenv("TRUSTFED_DB_PATH",str(tmp_path/"api_clients.sqlite3"))
        monkeypatch.setattr(api_main.runtime,"bootstrap",lambda:None)
        monkeypatch.setattr(api_main.runtime,"send_telegram_status",lambda *a,**k:{"status":"skipped"})
        monkeypatch.setattr(api_main.runtime,"simulation_loop",idle)
        login=admin.post("/client/auth/login",json={"identifier":"north","password":"StrongPass12345"})
        assert login.status_code==200,login.text
        profile=admin.get("/api/client/me")
        assert profile.status_code==200,profile.text
        assert profile.json()["client"]["client_id"]==client["client_id"]
        assert admin.get("/api/clients").status_code==403
