import csv,io
from app.pipeline import execute,load_sample,calculate
from app import store

def test_full_sample_flow(client):
    r=client.post("/api/runs",json={"sample":"dirty.csv"});assert r.status_code==200
    p=r.get_json();assert len(p["stages"])==7
    assert p["stages"][5]["metrics"]["balanced"] is True

def test_idempotent_real_input(sample):
    a=execute(sample);b=execute(sample)
    assert a["run_id"]==b["run_id"] and len(store.history())==1

def test_rerun_does_not_add_ledger_quota(sample):
    "重新运行同一批不能多出一笔占额"
    execute(sample);first=store.ledger_count()
    execute(sample);execute(sample)
    assert store.ledger_count()==first
    run=store.latest()
    assert store.ledger_count(run["run_id"])==len(run["stages"][6]["ledgers"])

def test_direction_switch_failure_keeps_full_legacy_ledger(client,sample):
    "方向规则切换失败时继续沿用完整旧版日账，且不写新批次"
    before=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    history_before=len(store.history());ledgers_before=store.ledger_count()
    resp=client.post("/api/runs",json={"sample":"dirty.csv","parameters":{"direction_mode":"feeder"}})
    assert resp.status_code==200
    body=resp.get_json()
    assert body["fallback"]["active"] is True
    assert body["fallback"]["reused_run_id"]==before["run_id"]
    assert body["run_id"]==before["run_id"]
    assert len(store.history())==history_before
    assert store.ledger_count()==ledgers_before

def test_valid_direction_switch_produces_new_run_and_ledgers(client):
    first=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    second=client.post("/api/runs",json={"sample":"dirty.csv","parameters":{
        "direction_mode":"feeder","feeder_links":[["02","01"]]}}).get_json()
    assert "fallback" not in second
    assert second["run_id"]!=first["run_id"]
    assert second["stages"][4]["metrics"]["direction_mode"]=="feeder"
    # 新批次同样每卡一份日账，旧批次日账不受影响
    assert store.ledger_count(second["run_id"])==len(second["stages"][6]["ledgers"])
    assert store.ledger_count(first["run_id"])==len(first["stages"][6]["ledgers"])

def test_stale_review_409(client):
    "TRAP-26 陈旧复核不得覆盖新版本"
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json();u="/api/runs/"+p["run_id"]+"/review"
    assert client.post(u,json={"version":1,"decision":"已复核"}).status_code==200
    assert client.post(u,json={"version":1,"decision":"退回复核"}).status_code==409

def test_export_has_manifest_and_quarantine(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    r=client.get("/api/runs/"+p["run_id"]+"/archive")
    rows=list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert rows[0][1]=="input_sha256" and any(x[3]=="quarantine" for x in rows[1:])
    assert any(x[3]=="daily_ledger" for x in rows[1:])

def test_failed_import_is_atomic(client):
    assert client.post("/api/runs",json={"csv":"bad"}).status_code==422
    assert store.history()==[] and store.ledger_count()==0

def test_module_entrances(client):
    from app.config import MODULES
    for slug,name in MODULES:
        assert client.get("/api/"+slug).status_code==200
        assert client.get("/"+slug).status_code==200

def test_missing_run_404(client): assert client.get("/api/runs/missing").status_code==404

def test_pages_show_direction_and_ledgers(client):
    client.post("/api/runs",json={"sample":"dirty.csv"})
    m5=client.get("/discounts").data.decode()
    assert "方向规则" in m5 and "方向裁决/拒绝理由" in m5
    m7=client.get("/settlement").data.decode()
    assert "卡日账" in m7 and "封顶应收" in m7
