from app.modules.m7_settlement.rules import evaluate,build_daily_ledgers
from app.errors import DomainError
import pytest

def _rows():
    return [
        {"event_id":"1","card":"0001","business_day":"2026-11-16","base_fare":"2.50","transfer_discount":"0.00","cap_discount":"0.00","expected":"2.50","reported":"2.50","difference":"0.00","status":"通过","_sources":[1]},
        {"event_id":"2","card":"0001","business_day":"2026-11-16","base_fare":"2.50","transfer_discount":"1.00","cap_discount":"0.00","expected":"1.50","reported":"1.50","difference":"0.00","status":"通过","_sources":[2]},
        {"event_id":"3","card":"0002","business_day":"2026-11-16","base_fare":"2.50","transfer_discount":"0.00","cap_discount":"0.50","expected":"2.00","reported":"2.50","difference":"-0.50","status":"差异","_sources":[3]},
    ]

def test_real_sample_archive_ready(result): assert result["stages"][6]["metrics"]["ready"] is True
def test_real_sample_archive_source_count(result):
    assert result["stages"][6]["metrics"]["source_lines"]==result["stages"][5]["metrics"]["accepted_inputs"]
def test_real_sample_seal_stable(result):
    rows=result["stages"][5]["rows"];assert evaluate(rows,{})["metrics"]["sha256"]==evaluate(rows,{})["metrics"]["sha256"]
def test_unbalanced_blocked():
    with pytest.raises(DomainError) as e:evaluate([],{"reconcile":{"metrics":{"balanced":False}}})
    assert e.value.code=="UNBALANCED"
def test_duplicate_archive_key():
    with pytest.raises(DomainError):evaluate([{"event_id":"1"},{"event_id":"1"}],{})
def test_real_sample_manifest_has_hash(result): assert len(result["manifest"]["input_sha256"])==64
def test_real_sample_export_rows_match(result): assert result["stages"][6]["rows"]==result["stages"][5]["rows"]

# ---- 每卡每业务日一份日账 ----
def test_one_ledger_per_card_per_day():
    ledgers=build_daily_ledgers(_rows())
    keys=[(x["card"],x["business_day"]) for x in ledgers]
    assert keys==[("0001","2026-11-16"),("0002","2026-11-16")] and len(keys)==len(set(keys))
    first=ledgers[0]
    assert first["rides"]==2 and first["transfer_discount_total"]=="1.00"
    assert first["expected_total"]=="4.00" and first["source_lines"]==[1,2]

def test_ledger_contains_transfer_cap_and_charge(result):
    ledgers=result["stages"][6]["ledgers"]
    assert ledgers, "真实样例必须产出卡日账"
    for ledger in ledgers:
        assert {"transfer_discount_total","cap_discount_total","expected_total"} <= set(ledger)
        from decimal import Decimal
        assert Decimal(ledger["base_total"])==Decimal(ledger["transfer_discount_total"])+Decimal(ledger["cap_discount_total"])+Decimal(ledger["expected_total"])

def test_ledger_count_metric(result):
    m=result["stages"][6]["metrics"]
    assert m["daily_ledgers"]==len(result["stages"][6]["ledgers"])
    assert m["ledger_expected_total"]==result["stages"][5]["metrics"]["expected_total"]

def test_cross_module_mismatch_blocks_seal():
    rows=_rows()
    fake_context={"clearing":{"metrics":{"balanced":True,"expected_total":"99.00","reported_total":"6.50"}}}
    with pytest.raises(DomainError) as e: evaluate(rows,fake_context)
    assert e.value.code=="LEDGER_CROSS_CHECK"

def test_coin_conservation_violation_blocks_seal():
    rows=_rows();rows[0]["expected"]="9.99"
    with pytest.raises(DomainError) as e: evaluate(rows,{})
    assert e.value.code=="LEDGER_NOT_BALANCED"
