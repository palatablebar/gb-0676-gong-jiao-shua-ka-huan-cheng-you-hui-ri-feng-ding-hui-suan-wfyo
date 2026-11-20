import csv,io,json
def build_archive(run):
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(["run_id","input_sha256","rule_version","kind","source_lines","reason","evidence"])
    meta=run["manifest"]
    if run.get("fallback"):
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"fallback","",
                         run["fallback"].get("code",""),json.dumps(run["fallback"],ensure_ascii=False)])
    for row in run["stages"][-1]["rows"]:
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"accepted",json.dumps(row.get("_sources",[])),row.get("status",""),json.dumps(row,ensure_ascii=False)])
    for ledger in run["stages"][-1].get("ledgers",[]):
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"daily_ledger",
                         json.dumps(ledger.get("source_lines",[])),"每卡每业务日一份",json.dumps(ledger,ensure_ascii=False)])
    for row in run["stages"][-1].get("cumulative_quarantine",[]):
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"quarantine",json.dumps(row.get("_sources",[])),row.get("reason",""),json.dumps(row,ensure_ascii=False)])
    return "﻿"+stream.getvalue()
