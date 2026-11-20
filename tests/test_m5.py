from app.modules.m5_discounts.rules import evaluate,direction_policy
from app.errors import DomainError
from decimal import Decimal
import pytest

def ride(id,minute,route="01",base="2.50",card="0001",day="2026-11-16"):
    return {"event_id":str(id),"card":card,"business_day":day,
            "at":f"2026-11-16T{8+minute//60:02d}:{minute%60:02d}:00Z","route":route,"base_fare":base}

# ---- 既有裁决保持（默认双向对称） ----
def test_real_day_cap(result): assert result["stages"][4]["metrics"]["expected_total"]=="48.00"
def test_exact_window_excluded():
    "TRAP-23 半开换乘窗"
    r=evaluate([ride(1,0),ride(2,60,"02")],{})["rows"];assert r[1]["transfer_discount"]=="0.00"
def test_within_window_discount(): assert evaluate([ride(1,0),ride(2,59,"02")],{})["rows"][1]["expected"]=="1.50"
def test_same_route_no_transfer(): assert evaluate([ride(1,0),ride(2,10)],{})["rows"][1]["expected"]=="2.50"
def test_zero_paid_not_anchor():
    r=evaluate([ride(1,0,base="1"),ride(2,30,"02",base="1"),ride(3,61,"03",base="1")],{})["rows"]
    assert r[1]["expected"]=="0.00" and r[2]["transfer_discount"]=="0.00"
def test_discount_before_cap_conservation():
    "TRAP-10 Decimal守恒"
    r=evaluate([ride(1,0),ride(2,10,"02"),ride(3,20,"03"),ride(4,90)],{})["rows"]
    assert sum(Decimal(x["expected"]) for x in r)==Decimal("6")
    assert all(Decimal(x["base_fare"])==Decimal(x["expected"])+Decimal(x["transfer_discount"])+Decimal(x["cap_discount"]) for x in r)
def test_negative_parameter_rejected():
    with pytest.raises(DomainError):evaluate([],{"parameters":{"daily_cap":"-1"}})
def test_input_order_invariant():
    rows=[ride(1,0),ride(2,10,"02")];assert evaluate(rows,{})["rows"]==evaluate(list(reversed(rows)),{})["rows"]

# ---- 接驳方向裁决 ----
def test_both_directions_enjoy_discount():
    "同一组接驳线路：支线→主干线与返程（主干线→支线）双向享受优惠"
    rows=[ride(1,0,"02",base="2.00"),ride(2,15,"01",base="2.00"),ride(3,40,"02",base="2.00")]
    params={"direction_mode":"both","feeder_links":[["02","01"]],"transfer_discount":"0.50"}
    r=evaluate(rows,{"parameters":params})["rows"]
    assert r[0]["transfer_discount"]=="0.00"
    assert r[1]["transfer_discount"]=="0.50" and r[1]["transfer_direction"]=="接驳方向"
    assert r[2]["transfer_discount"]=="0.50" and r[2]["transfer_direction"]=="返程方向"
    assert all("拒绝" not in x["transfer_reason"] for x in r[1:])

def test_feeder_only_mode_rejects_reverse():
    "只承认接驳方向：返程被同样减收时必须拒绝并落理由"
    rows=[ride(1,0,"02",base="2.00"),ride(2,15,"01",base="2.00"),ride(3,40,"02",base="2.00")]
    params={"direction_mode":"feeder","feeder_links":[["02","01"]],"transfer_discount":"0.50"}
    out=evaluate(rows,{"parameters":params})
    r=out["rows"]
    # 第二程 02支→01干 为接驳方向，享优惠；第三程 01干→02支 为返程，被拒绝
    assert r[1]["transfer_discount"]=="0.50" and r[1]["transfer_direction"]=="接驳方向"
    assert r[2]["transfer_discount"]=="0.00" and r[2]["transfer_direction"]=="—"
    assert "返程" in r[2]["transfer_reason"]
    assert out["metrics"]["direction_accepted"]==1 and out["metrics"]["direction_rejected"]==2

def test_feeder_mode_rejects_non_pair_cross_line():
    rows=[ride(1,0,"02"),ride(2,15,"03")]
    params={"direction_mode":"feeder","feeder_links":[["02","01"]]}
    r=evaluate(rows,{"parameters":params})["rows"]
    assert r[1]["transfer_discount"]=="0.00" and "同一组接驳线路" in r[1]["transfer_reason"]

def test_reason_codes_for_each_rejection():
    rows=[ride(1,0),ride(2,10),ride(3,70,"02"),ride(4,80,"03")]
    r=evaluate(rows,{})["rows"]
    assert r[0]["transfer_reason"].startswith("无上次付费行程")
    assert "同线路" in r[1]["transfer_reason"]
    assert "换乘窗" in r[2]["transfer_reason"]
    assert r[3]["transfer_anchor"]!="—"  # 锚点为001（付费），003零优惠不影响后续窗口

def test_invalid_direction_mode_fails_fast():
    with pytest.raises(DomainError) as e: direction_policy({"direction_mode":"oneway"})
    assert e.value.code=="BAD_DIRECTION_RULE"

def test_feeder_mode_requires_links():
    with pytest.raises(DomainError) as e: evaluate([ride(1,0)],{"parameters":{"direction_mode":"feeder"}})
    assert e.value.code=="BAD_DIRECTION_RULE"

def test_bad_link_shape_fails_fast():
    with pytest.raises(DomainError): direction_policy({"direction_mode":"feeder","feeder_links":[["02"]]})
    with pytest.raises(DomainError): direction_policy({"direction_mode":"feeder","feeder_links":[["01","01"]]})

def test_metrics_expose_actual_mode():
    out=evaluate([ride(1,0,"02"),ride(2,10,"01")],{"parameters":{"direction_mode":"both","feeder_links":[["02","01"]]}})
    assert out["metrics"]["direction_mode"]=="both"
    assert out["metrics"]["feeder_links"]==[["02","01"]]
