from decimal import Decimal
from app.values import number,instant,money
from app.errors import DomainError

DIRECTION_MODES={"both","feeder"}
# 拒绝理由：页面与导出均需展示实际采用的方向和拒绝依据
REASON_FIRST_RIDE="无上次付费行程，不构成换乘"
REASON_OUTSIDE_WINDOW="超出半开换乘窗（恰好60分钟排除）"
REASON_SAME_ROUTE="同线路乘车不享换乘优惠"
REASON_WRONG_DIRECTION="仅承认接驳方向：返程不享换乘优惠"
REASON_NOT_FEEDER_PAIR="两线不属于同一组接驳线路"

def _normalise_links(raw_links):
    """归一化接驳配对：[(支线, 主干线), ...]，保留接驳方向顺序。"""
    if raw_links is None: return []
    if not isinstance(raw_links,list): raise DomainError("BAD_DIRECTION_RULE","接驳配对需要列表")
    links=[]
    for item in raw_links:
        if not isinstance(item,(list,tuple)) or len(item)!=2:
            raise DomainError("BAD_DIRECTION_RULE","每条接驳配对需为[支线,主干线]")
        feeder,trunk=str(item[0]).strip(),str(item[1]).strip()
        if not feeder or not trunk: raise DomainError("BAD_DIRECTION_RULE","接驳线路编号不能为空")
        if feeder==trunk: raise DomainError("BAD_DIRECTION_RULE","接驳支线与主干线不能相同")
        pair=(feeder,trunk)
        if pair not in links: links.append(pair)
    return links

def direction_policy(parameters):
    params=parameters or {}
    mode=params.get("direction_mode","both")
    if mode not in DIRECTION_MODES:
        raise DomainError("BAD_DIRECTION_RULE",f"方向规则无效，仅支持：{sorted(DIRECTION_MODES)}")
    links=_normalise_links(params.get("feeder_links"))
    if mode=="feeder" and not links:
        raise DomainError("BAD_DIRECTION_RULE","接驳方向模式必须提供接驳配对 feeder_links")
    return mode,links

def _pair_index(prev_route,route,links):
    """返回配对内方向：forward=支线→主干线，backward=主干线→支线，None=非同一接驳组。"""
    for feeder,trunk in links:
        if prev_route==feeder and route==trunk: return "forward"
        if prev_route==trunk and route==feeder: return "backward"
    return None

def evaluate(rows,context):
    params=(context or {}).get("parameters",{}) or {}
    cap=number(params.get("daily_cap","6.00"));off=number(params.get("transfer_discount","1.00"));window=number(params.get("transfer_minutes","60"))
    if cap<0 or off<0 or window<0:raise DomainError("BAD_DISCOUNT","优惠参数不能为负")
    mode,links=direction_policy(params)
    spent={};anchor={};good=[]
    for row in sorted(rows,key=lambda r:(r["card"],instant(r["at"]),r["event_id"])):
        key=(row["card"],row["business_day"]);base=number(row["base_fare"]);previous=anchor.get(key)
        eligible=False;direction="—";deny_reason=""
        if previous is None:
            deny_reason=REASON_FIRST_RIDE
        else:
            delta=Decimal(str((instant(row["at"])-instant(previous["at"])).total_seconds()))/60
            if previous["route"]==row["route"]:
                deny_reason=REASON_SAME_ROUTE
            elif not (Decimal(0)<=delta<window):
                deny_reason=REASON_OUTSIDE_WINDOW
            else:
                pair_direction=_pair_index(previous["route"],row["route"],links)
                if mode=="feeder":
                    # 只承认接驳方向（支线→主干线）；返程与非接驳组跨线均拒绝
                    if pair_direction is None:
                        deny_reason=REASON_NOT_FEEDER_PAIR
                    elif pair_direction=="backward":
                        deny_reason=REASON_WRONG_DIRECTION
                    else:
                        eligible=True;direction="接驳方向"
                else:
                    # 双向对称：同一组接驳线路的返程同样享受优惠
                    if pair_direction=="forward": direction="接驳方向"
                    elif pair_direction=="backward": direction="返程方向"
                    else: direction="跨线换乘"
                    eligible=True
        transfer=min(base,off) if eligible else Decimal(0)
        after_transfer=base-transfer;remaining=max(Decimal(0),cap-spent.get(key,Decimal(0)));charge=min(after_transfer,remaining)
        cap_discount=after_transfer-charge;spent[key]=spent.get(key,Decimal(0))+charge
        good.append({**row,
                     "direction_mode":mode,
                     "transfer_direction":direction if eligible else "—",
                     "transfer_anchor":previous["event_id"] if eligible else "—",
                     "transfer_reason":("享受换乘优惠·"+direction) if eligible else deny_reason,
                     "transfer_discount":money(transfer),"cap_discount":money(cap_discount),
                     "expected":money(charge),"day_paid":money(spent[key])})
        if charge>0:anchor[key]=row
    metrics={"expected_total":money(sum((number(r["expected"]) for r in good),Decimal(0))),
             "daily_caps":len(spent),
             "transfer_hits":sum(r["transfer_anchor"]!="—" for r in good),
             "direction_mode":mode,
             "feeder_links":[list(p) for p in links],
             "direction_accepted":sum(1 for r in good if r["transfer_anchor"]!="—"),
             "direction_rejected":sum(1 for r in good if r["transfer_anchor"]=="—")}
    return {"rows":good,"quarantine":[],"metrics":metrics}
