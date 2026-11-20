import sqlite3,json
from pathlib import Path
from app.config import DATA_DIR
from app.errors import DomainError
def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"records.db",timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,decision TEXT NOT NULL DEFAULT '待复核')")
    # 每张卡每个业务日只允许一份日账；(run_id,card,business_day) 唯一保证同源重跑不新增占额
    db.execute("""CREATE TABLE IF NOT EXISTS daily_ledgers (
        run_id TEXT NOT NULL,card TEXT NOT NULL,business_day TEXT NOT NULL,
        payload TEXT NOT NULL,created_version TEXT NOT NULL,
        PRIMARY KEY (run_id,card,business_day))""")
    return db
def save(run_id,payload):
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO runs(id,payload) VALUES (?,?)",(run_id,json.dumps(payload,ensure_ascii=False)))
        # 事务内写入卡日账；唯一键冲突时 INSERT OR IGNORE 静默复用，重跑同一批不会多出一笔
        settlement=payload["stages"][-1]
        for ledger in settlement.get("ledgers",[]):
            db.execute("""INSERT OR IGNORE INTO daily_ledgers(run_id,card,business_day,payload,created_version)
                          VALUES (?,?,?,?,?)""",
                       (run_id,ledger["card"],ledger["business_day"],json.dumps(ledger,ensure_ascii=False),
                        payload["manifest"]["rule_version"]))
    return get(run_id)
def get(run_id):
    with connect() as db: row=db.execute("SELECT payload,version,decision FROM runs WHERE id=?",(run_id,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","批次不存在",404)
    return {**json.loads(row[0]),"version":row[1],"decision":row[2]}
def latest():
    with connect() as db: row=db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return get(row[0]) if row else None
def history():
    with connect() as db: return [{"run_id":i,"version":v,"decision":d} for i,v,d in db.execute("SELECT id,version,decision FROM runs ORDER BY rowid DESC")]
def ledger_count(run_id=None):
    with connect() as db:
        if run_id is None: row=db.execute("SELECT COUNT(*) FROM daily_ledgers").fetchone()
        else: row=db.execute("SELECT COUNT(*) FROM daily_ledgers WHERE run_id=?",(run_id,)).fetchone()
    return row[0]
def review(run_id,version,decision):
    if decision not in {"已复核","退回复核"}: raise DomainError("BAD_DECISION","复核状态无效")
    with connect() as db:
        cursor=db.execute("UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?",(decision,run_id,version))
        if cursor.rowcount!=1:
            if not db.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): raise DomainError("NOT_FOUND","批次不存在",404)
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get(run_id)
