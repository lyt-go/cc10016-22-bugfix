"""迁徙路线验证签认回执与年度总结纳入判定。

一条迁徙路线可以有多个版次：现场补报点会形成新的待更新版次，而
已绘制且点序完整的版次可以办理一次正式签认，产生一份不可篡改的
「验证签认回执」。年度总结只能凭这些回执纳入路线，且同一路线在
同一份报告里只计一次，并记录当次签认的版次与回执编号，供已发布
报告回查。

回执不放在 ``store`` 的 18 张业务表里，避免改变模块清单；它是验证
动作产生的旁路审计凭据，生命周期与进程一致。
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Iterable

from app.store import store

# 正式签认回执（含历史存量认定），按产生顺序追加，永不覆盖。
RECEIPTS: list[dict[str, Any]] = []
_SEQUENCE = 0

ROUTE_MODULE = "migration_track"


# ---------------------------------------------------------------------------
# 版次与点序
# ---------------------------------------------------------------------------

def route_version(route: dict[str, Any]) -> int:
    try:
        return max(1, int(route.get("版次") or 1))
    except (TypeError, ValueError):
        return 1


def ensure_route_versions(route: dict[str, Any]) -> dict[str, Any]:
    """为存量路线补齐版次字段，但不改变其业务状态。"""
    version = route_version(route)
    route.setdefault("版次", version)
    if route.get("已绘制版次") in (None, "") and route.get("status") in ("已绘制", "已验证", "待更新"):
        route["已绘制版次"] = version
    if route.get("已签认版次") in (None, "") and route.get("status") == "已验证":
        # 存量「已验证」在补发历史认定回执前先占位，回执版次以历史认定为准。
        pass
    route.setdefault("待办请求", [])
    return route


_POINT_SEQ_KEYS = ("序号", "index", "seq", "点序", "order")
_POINT_COORD_KEYS = ("经纬度", "坐标", "lnglat", "coordinate", "coord")
_POINT_REGION_KEYS = ("区域", "region", "地点", "location")
_POINT_SOURCE_KEYS = ("来源记录", "来源", "source", "record_id")


def _first(raw: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_points(raw_points: Any) -> list[dict[str, Any]]:
    """把接口传入的各种点序写法归一为带序号的轨迹点。"""
    if raw_points in (None, ""):
        return []
    if isinstance(raw_points, str):
        import json

        try:
            raw_points = json.loads(raw_points)
        except (TypeError, ValueError):
            raw_points = [chunk for chunk in raw_points.replace("；", ";").split(";") if chunk.strip()]
    if not isinstance(raw_points, (list, tuple)):
        return []

    points: list[dict[str, Any]] = []
    for index, item in enumerate(raw_points, start=1):
        if isinstance(item, dict):
            seq = _first(item, _POINT_SEQ_KEYS)
            coord = _first(item, _POINT_COORD_KEYS)
            region = _first(item, _POINT_REGION_KEYS)
            source = _first(item, _POINT_SOURCE_KEYS)
        elif isinstance(item, (list, tuple)):
            if len(item) >= 2 and all(isinstance(v, (int, float)) for v in item[:2]):
                seq, coord, region, source = index, f"{item[0]},{item[1]}", None, None
            else:
                seq, coord, region, source = (item[0] if item else index), (
                    item[1] if len(item) > 1 else None), None, None
        else:
            seq, coord, region, source = index, str(item), None, None

        try:
            seq = int(seq) if seq not in (None, "") else index
        except (TypeError, ValueError):
            seq = index
        point: dict[str, Any] = {"序号": seq, "经纬度": "" if coord is None else str(coord)}
        if region not in (None, ""):
            point["区域"] = str(region)
        if source not in (None, ""):
            point["来源记录"] = source
        points.append(point)

    points.sort(key=lambda point: point["序号"])
    return points


def _derived_points(route: dict[str, Any]) -> list[dict[str, Any]]:
    """未显式存点序时，用起点/途经/终点推导出的有序点列。"""
    regions = [route.get("起点区域"), route.get("途经区域"), route.get("终点区域")]
    if any(str(value or "").strip() == "" for value in regions):
        return []
    return [
        {"序号": index, "经纬度": str(value), "区域": str(value), "来源记录": "路线字段"}
        for index, value in enumerate(regions, start=1)
    ]


def route_points(route: dict[str, Any]) -> list[dict[str, Any]]:
    """路线当前报送的点序（可能是现场补报点）。"""
    for key in ("轨迹点", "点序", "点序列", "points"):
        if route.get(key):
            normalized = normalize_points(route[key])
            if normalized:
                return normalized
    return _derived_points(route)


def inspect_points(points: list[dict[str, Any]]) -> tuple[bool, str]:
    if len(points) < 2:
        return False, "轨迹点不足两点，点序不完整"
    expected = list(range(1, len(points) + 1))
    actual = [point.get("序号") for point in points]
    if actual != expected:
        return False, "轨迹点序号不连续，点序不完整"
    if any(not str(point.get("经纬度") or "").strip() for point in points):
        return False, "存在缺少经纬度的轨迹点，点序不完整"
    return True, ""


def inspect_point_sequence(route: dict[str, Any]) -> tuple[bool, str, list[dict[str, Any]]]:
    """校验「完整点序」：至少两点、序号从 1 连续、每点带位置。"""
    points = drawn_points(route)
    complete, reason = inspect_points(points)
    return complete, reason, points


def drawn_points(route: dict[str, Any]) -> list[dict[str, Any]]:
    """已绘制版次的点序快照；现场补报点不会覆盖它。"""
    for key in ("已绘制点序", "轨迹点", "点序", "点序列", "points"):
        if route.get(key):
            normalized = normalize_points(route[key])
            if normalized:
                return normalized
    return _derived_points(route)


def record_drawn_points(route: dict[str, Any], points: Any = None) -> list[dict[str, Any]]:
    """把本次绘制的点序固定为已绘制版快照，后续补报点不覆盖。"""
    normalized = normalize_points(points) if points not in (None, "") else []
    if not normalized:
        normalized = route_points(route)
    route["已绘制点序"] = copy.deepcopy(normalized)
    return normalized


# ---------------------------------------------------------------------------
# 回执签发
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_receipt_no() -> str:
    global _SEQUENCE
    _SEQUENCE += 1
    return f"VR-{datetime.now().year}-{_SEQUENCE:04d}"


def _new_receipt(
    route: dict[str, Any],
    points: list[dict[str, Any]],
    *,
    version: int,
    source: str,
    signer: str,
    receipt_no: str | None = None,
    signed_at: str | None = None,
    legacy: bool = False,
    update_pending: bool = False,
) -> dict[str, Any]:
    route_id = int(route.get("id", 0))
    number = receipt_no or _next_receipt_no()
    timestamp = signed_at or _now()
    individual = str(route.get("追踪个体", ""))
    receipt: dict[str, Any] = {
        # 中文主字段
        "回执编号": number,
        "路线编号": route_id,
        "追踪个体": individual,
        "路线版次": version,
        "纳入版次": version,
        "签认状态": "正式签认",
        "验证状态": "已验证",
        "验证结论": "通过",
        "签认人": signer,
        "签认时间": timestamp,
        "点序": copy.deepcopy(points),
        "来源": source,
        "更新待复核": update_pending,
        # 英文别名，便于跨模块接口与外部系统读取
        "receipt_no": number,
        "receipt_id": number,
        "route_id": route_id,
        "track_individual": individual,
        "version": version,
        "route_version": version,
        "included_version": version,
        "signoff_status": "formal",
        "signer": signer,
        "signed_at": timestamp,
        "points": copy.deepcopy(points),
        "source": source,
        "legacy": legacy,
        "review_pending": update_pending,
    }
    RECEIPTS.append(receipt)
    _attach_receipt_to_route(route, receipt)
    return receipt


def _attach_receipt_to_route(route: dict[str, Any], receipt: dict[str, Any]) -> None:
    numbers = route.setdefault("验证回执", [])
    if receipt["回执编号"] not in numbers:
        numbers.append(receipt["回执编号"])
    route["最近签认回执"] = copy.deepcopy(receipt)
    if route.get("status") == "已验证":
        route["已签认版次"] = receipt["路线版次"]
    if route.get("已绘制版次") in (None, ""):
        route["已绘制版次"] = receipt["路线版次"]


def formal_receipts(route_id: int) -> list[dict[str, Any]]:
    return [receipt for receipt in RECEIPTS if int(receipt.get("路线编号", 0)) == int(route_id)]


def receipt_for_version(route_id: int, version: int) -> dict[str, Any] | None:
    matches = [r for r in formal_receipts(route_id) if int(r.get("路线版次", 0)) == int(version)]
    return matches[-1] if matches else None


def find_receipt(receipt_no: str) -> dict[str, Any] | None:
    for receipt in RECEIPTS:
        if receipt["回执编号"] == receipt_no:
            return receipt
    return None


def latest_receipt(route_id: int) -> dict[str, Any] | None:
    receipts = formal_receipts(route_id)
    if not receipts:
        return None
    return max(receipts, key=lambda r: (int(r.get("路线版次", 0)), RECEIPTS.index(r)))


def issue_signoff(
    route: dict[str, Any],
    points: list[dict[str, Any]],
    *,
    signer: str,
    source: str = "已绘制版签认",
    update_pending: bool = False,
    version: int | None = None,
) -> dict[str, Any]:
    """为指定版次签发正式签认回执；同一版次重复签认沿用已有回执。"""
    version = int(version if version is not None else route_version(route))
    existing = receipt_for_version(int(route.get("id", 0)), version)
    if existing is not None:
        return existing
    return _new_receipt(
        route,
        points,
        version=version,
        source=source,
        signer=signer,
        update_pending=update_pending,
    )


def ensure_legacy_receipt(route: dict[str, Any]) -> dict[str, Any] | None:
    """存量「已验证」路线没有回执时补发历史认定回执，兼容既有总结。"""
    if route.get("status") != "已验证":
        return None
    route_id = int(route.get("id", 0))
    existing = receipt_for_version(route_id, route_version(route))
    if existing is not None:
        return existing
    points = route_points(route)
    if not points:
        points = _derived_points(route)
    receipt = _new_receipt(
        route,
        points,
        version=route_version(route),
        source="历史存量认定",
        signer=str(route.get("记录人") or "历史数据"),
        receipt_no=f"VR-LEGACY-{route_id:03d}",
        signed_at=str(route.get("记录时段") or "历史存量"),
        legacy=True,
    )
    return receipt


# ---------------------------------------------------------------------------
# 纳入判定
# ---------------------------------------------------------------------------

def _has_pending_update(route: dict[str, Any]) -> bool:
    if route.get("status") == "待更新":
        return True
    return any(
        isinstance(request, dict)
        and request.get("动作") == "更新路线"
        and request.get("状态") == "待办理"
        for request in route.get("待办请求", [])
    )


def _is_pending_update(route: dict[str, Any]) -> bool:
    return _has_pending_update(route)


# 供 migration_track 服务按「现场补报点」语义判定更新请求。
is_update_pending = _has_pending_update


def evaluate_route(route: dict[str, Any]) -> dict[str, Any]:
    """给出一条路线当前的签认与纳入结论（同一路线只返回一条）。"""
    ensure_route_versions(route)
    route_id = int(route.get("id", 0))
    status = str(route.get("status", ""))
    current_version = route_version(route)
    drawn_version = route.get("已绘制版次")
    signed_version = route.get("已签认版次")

    if status == "已验证":
        ensure_legacy_receipt(route)
        signed_version = route.get("已签认版次") or signed_version

    receipt = latest_receipt(route_id)
    if receipt is not None and signed_version in (None, ""):
        signed_version = receipt["路线版次"]
    pending_update = _has_pending_update(route)
    decision = "暂不纳入"
    review_state = "无"
    reason = ""
    obtainable_version: int | None = None
    review_version: int | None = None

    if receipt is not None:
        obtainable_version = int(receipt["路线版次"])
        signed_matches = int(signed_version or 0) == obtainable_version
        if not signed_matches:
            decision = "需复核"
            reason = "最新签认回执的版次与路线已签认版次不一致，需人工复核"
            review_version = obtainable_version
        elif pending_update and current_version > obtainable_version:
            decision = "可采用"
            review_state = "需复核"
            review_version = current_version
            reason = (
                f"现场补报点已登记为第{current_version}版，尚未重新绘制并签认；"
                f"本次报告沿用第{obtainable_version}版正式签认回执，"
                f"第{current_version}版需接办复核后再替换。"
            )
        elif pending_update:
            decision = "需复核"
            review_version = current_version
            reason = "路线存在待办理的更新请求，签认版次尚未确定，需接办复核"
        elif status == "已验证":
            decision = "可采用"
            reason = f"已取得第{obtainable_version}版正式签认回执"
        elif status == "已绘制":
            decision = "可采用"
            review_state = "需复核" if current_version > obtainable_version else "无"
            if current_version > obtainable_version:
                review_version = current_version
                reason = (
                    f"第{current_version}版已重新绘制但尚未签认，"
                    f"本次沿用第{obtainable_version}版正式签认回执，第{current_version}版需复核"
                )
            else:
                reason = f"已取得第{obtainable_version}版正式签认回执"
        else:
            decision = "可采用"
            reason = f"已取得第{obtainable_version}版正式签认回执"
    else:
        if status == "待更新":
            decision = "需复核"
            review_version = current_version
            reason = "现场补报点形成的更新尚未完成，且无正式签认回执，需重新绘制并签认"
        elif status == "已绘制":
            decision = "待签认"
            review_version = current_version
            reason = "路线已绘制但尚未办理正式签认，本次不纳入"
        else:
            decision = "暂不纳入"
            reason = "路线尚未绘制，不能纳入年度总结"

    return {
        "route_id": route_id,
        "route_no": route_id,
        "追踪个体": str(route.get("追踪个体", "")),
        "track_individual": str(route.get("追踪个体", "")),
        "当前状态": status,
        "status": status,
        "版次": current_version,
        "current_version": current_version,
        "已绘制版次": drawn_version,
        "drawn_version": drawn_version,
        "已签认版次": signed_version,
        "signed_version": signed_version,
        "纳入版次": obtainable_version,
        "included_version": obtainable_version,
        "可取得版次": obtainable_version,
        "obtainable_version": obtainable_version,
        "纳入结论": decision,
        "decision": decision,
        "复核状态": review_state,
        "review_state": review_state,
        "需复核": review_state == "需复核",
        "待复核版次": review_version if review_state == "需复核" else None,
        "pending_version": review_version if review_state == "需复核" else None,
        "说明": reason,
        "reason": reason,
        "回执编号": receipt["回执编号"] if receipt else None,
        "receipt_no": receipt["回执编号"] if receipt else None,
        "来源": receipt["来源"] if receipt else None,
        "source": receipt["来源"] if receipt else None,
        "验证状态": receipt["签认状态"] if receipt else None,
        "verification_status": receipt["签认状态"] if receipt else None,
        "receipt": copy.deepcopy(receipt) if receipt else None,
    }


def _is_report_candidate(route: dict[str, Any]) -> bool:
    """报告考察已正式签认、或已进入绘制/验证/更新环节的路线。

    尚未绘制的草稿不会出现在报告里，避免把未纳入的路线误当成报告路线。
    """
    if formal_receipts(int(route.get("id", 0))):
        return True
    return str(route.get("status", "")) in ("已绘制", "已验证", "待更新")


def compile_inclusions() -> dict[str, Any]:
    """按路线去重，汇总当前可纳入与待复核的路线，供报告提交冻结。"""
    included: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    for route in sorted(store.rows(ROUTE_MODULE), key=lambda row: int(row.get("id", 0))):
        if not _is_report_candidate(route):
            continue
        evaluation = evaluate_route(route)
        if evaluation["纳入结论"] == "可采用":
            included.append(evaluation)
        else:
            pending.append(evaluation)

    return {
        "included_routes": included,
        "pending_routes": pending,
        "route_count": len(included),
        "included_count": len(included),
        "pending_count": len(pending),
        "candidate_count": len(included) + len(pending),
        "receipt_numbers": [item["回执编号"] for item in included if item.get("回执编号")],
        "included_versions": [
            {
                "route_id": item["route_id"],
                "version": item["纳入版次"],
                "receipt_no": item["回执编号"],
            }
            for item in included
        ],
        "compiled_at": _now(),
        "basis_version": "verification-receipt-v1",
    }


def list_receipts(
    *,
    route_id: int | None = None,
    decision: str | None = None,
) -> dict[str, Any]:
    """现场验证清单：返回回执及其对应路线当前的纳入结论。"""
    if route_id is not None:
        route = store.find(ROUTE_MODULE, route_id)
        if route is not None:
            ensure_route_versions(route)
            if route.get("status") == "已验证":
                ensure_legacy_receipt(route)

    items: list[dict[str, Any]] = []
    for receipt in RECEIPTS:
        if route_id is not None and int(receipt.get("路线编号", 0)) != int(route_id):
            continue
        route = store.find(ROUTE_MODULE, int(receipt.get("路线编号", 0)))
        evaluation = evaluate_route(route) if route else None
        current_no = evaluation.get("回执编号") if evaluation else None
        view = copy.deepcopy(receipt)
        if evaluation is not None:
            view.update({
                "纳入结论": evaluation["纳入结论"],
                "decision": evaluation["纳入结论"],
                "复核状态": evaluation["复核状态"],
                "review_state": evaluation["复核状态"],
                "说明": evaluation["说明"],
                "reason": evaluation["说明"],
                "是否现行": receipt["回执编号"] == current_no,
                "is_current": receipt["回执编号"] == current_no,
                "路线当前状态": evaluation["当前状态"],
                "route_status": evaluation["当前状态"],
            })
        if decision is not None and view.get("纳入结论") != decision:
            continue
        items.append(view)

    items.sort(key=lambda view: (int(view.get("路线编号", 0)), int(view.get("路线版次", 0))))
    return {"items": items, "total": len(items)}
