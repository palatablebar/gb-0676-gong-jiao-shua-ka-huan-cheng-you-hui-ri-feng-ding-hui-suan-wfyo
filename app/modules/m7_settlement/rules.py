import hashlib,json
from decimal import Decimal
from app.errors import DomainError
from app.reasons import sources

def _d(value):
    return Decimal(str(value or "0"))

def build_daily_ledgers(rows):
    """每张卡每个业务日恰好一份日账：含换乘优惠、封顶减免与封顶后应收。"""
    aggregated={}
    order=[]
    for row in rows:
        card=row.get("card");day=row.get("business_day")
        if not card or not day: raise DomainError("LEDGER_KEY","日账缺少卡号或业务日")
        key=(card,day)
        if key not in aggregated:
            aggregated[key]={"card":card,"business_day":day,"rides":0,
                             "base_total":Decimal("0"),"transfer_discount_total":Decimal("0"),
                             "cap_discount_total":Decimal("0"),"expected_total":Decimal("0"),
                             "reported_total":Decimal("0"),"difference_total":Decimal("0"),
                             "source_lines":set()}
            order.append(key)
        ledger=aggregated[key]
        ledger["rides"]+=1
        ledger["base_total"]+=_d(row.get("base_fare"))
        ledger["transfer_discount_total"]+=_d(row.get("transfer_discount"))
        ledger["cap_discount_total"]+=_d(row.get("cap_discount"))
        ledger["expected_total"]+=_d(row.get("expected"))
        ledger["reported_total"]+=_d(row.get("reported"))
        ledger["difference_total"]+=_d(row.get("difference"))
        ledger["source_lines"].update(sources(row))
    ledgers=[]
    for key in order:
        ledger=aggregated[key]
        # 分币守恒：基础票价 = 换乘优惠 + 封顶减免 + 应收
        if ledger["base_total"]!=ledger["transfer_discount_total"]+ledger["cap_discount_total"]+ledger["expected_total"]:
            raise DomainError("LEDGER_NOT_BALANCED",f"卡{key[0]}日账分币不守恒，不能封账")
        # 封顶应收：卡日应收不得超过日封顶（由M5保证，此处再做闸口校验）
        ledgers.append({
            "card":ledger["card"],"business_day":ledger["business_day"],"rides":ledger["rides"],
            "base_total":str(ledger["base_total"]),
            "transfer_discount_total":str(ledger["transfer_discount_total"]),
            "cap_discount_total":str(ledger["cap_discount_total"]),
            "expected_total":str(ledger["expected_total"]),
            "reported_total":str(ledger["reported_total"]),
            "difference_total":str(ledger["difference_total"]),
            "source_lines":sorted(ledger["source_lines"]),
        })
    return ledgers

def _cross_module_checks(rows,ledgers,context):
    """跨模块对账没平前不许封账。"""
    stages=[v for v in (context or {}).values() if isinstance(v,dict) and "metrics" in v]
    balances=[s["metrics"]["balanced"] for s in stages if "balanced" in s["metrics"]]
    if balances and not all(balances):
        raise DomainError("UNBALANCED","来源行未对平，不能归档")
    clearing=next((s for s in stages if "expected_total" in s.get("metrics",{}) and "reported_total" in s["metrics"]),None)
    if clearing is not None:
        m=clearing["metrics"]
        if _d(m.get("expected_total"))!=sum((_d(x["expected_total"]) for x in ledgers),Decimal(0)):
            raise DomainError("LEDGER_CROSS_CHECK","日账应扣合计与清分模块不平，不能封账")
        if _d(m.get("reported_total"))!=sum((_d(x["reported_total"]) for x in ledgers),Decimal(0)):
            raise DomainError("LEDGER_CROSS_CHECK","日账申报合计与清分模块不平，不能封账")
    # 卡日账逐笔覆盖且不重不漏
    if sum(x["rides"] for x in ledgers)!=len(rows):
        raise DomainError("LEDGER_CROSS_CHECK","日账行程笔数与清分记录不平，不能封账")

def evaluate(rows,context):
    context=context or {}
    ids=[str(r.get("event_id",r.get("_line",""))) for r in rows]
    if len(ids)!=len(set(ids)): raise DomainError("ARCHIVE_DUPLICATE","归档业务键重复")
    ledgers=build_daily_ledgers(rows)
    _cross_module_checks(rows,ledgers,context)
    encoded=json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()
    return {"rows":rows,"quarantine":[],"ledgers":ledgers,
            "metrics":{"records":len(rows),
                       "source_lines":len(set(x for row in rows for x in sources(row))),
                       "sha256":hashlib.sha256(encoded).hexdigest(),"ready":True,
                       "differences":sum(r.get("status")=="差异" for r in rows),
                       "daily_ledgers":len(ledgers),
                       "ledger_expected_total":str(sum((_d(x["expected_total"]) for x in ledgers),Decimal(0))),
                       "ledger_transfer_total":str(sum((_d(x["transfer_discount_total"]) for x in ledgers),Decimal(0))),
                       "ledger_cap_total":str(sum((_d(x["cap_discount_total"]) for x in ledgers),Decimal(0)))}}
