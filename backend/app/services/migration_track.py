"""迁徙路线领域服务：绘制、验证签认、现场补报更新与纳入回执。

状态流转只在这里改。验证入口必须校验「已绘制 + 完整点序」，
不允许从待绘制跳级签认；同一路线允许同时存在一份已绘制版签认
和一份现场补报点引起的更新请求，二者都不结束签认时，报告编制员
可从回执得知本次可采用哪一版、第几版需要接办复核。
"""
from __future__ import annotations

from typing import Any

from app.store import store
from app.verification import (
    compile_inclusions,
    drawn_points,
    evaluate_route,
    ensure_route_versions,
    ensure_legacy_receipt,
    inspect_points,
    is_update_pending,
    issue_signoff,
    list_receipts,
    normalize_points,
    receipt_for_version,
    record_drawn_points,
    route_version,
)
from app.services.base import BaseModuleService

# 签认类动作与入口动作分开登记，避免验证入口被通用规则直接放行。
SIGN_OFF_ACTION = "验证路线"
REQUEST_SIGN_OFF_ACTION = "验证签认"
REQUEST_UPDATE_ACTION = "更新路线"
DRAW_ACTION = "绘制路线"


class MigrationTrackService(BaseModuleService):
    MODULE = "migration_track"
    ENTITY = "迁徙路径"
    OPERATION_TERM = "绘制路线"
    LIST_FIELDS = ["追踪个体", "起点区域", "途经区域", "终点区域", "迁徙距离", "记录人", "记录时段", "备注说明"]
    REQUIRED_FIELDS = ["追踪个体", "起点区域", "途经区域"]
    STATUS_ORDER = ["待绘制", "已绘制", "已验证", "待更新"]
    ACTION_RULES = {"绘制路线": "已绘制", "验证路线": "已验证", "更新路线": "待更新"}
    NEGATIVE_ACTIONS = []

    # -- 读取 ---------------------------------------------------------------

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None
        self._hydrate(entry)
        return entry

    def list_entries(self, **kwargs: Any):
        rows, total = super().list_entries(**kwargs)
        for row in rows:
            self._hydrate(row)
        return rows, total

    def _hydrate(self, route: dict[str, Any]) -> None:
        ensure_route_versions(route)
        if route.get("status") == "已验证":
            ensure_legacy_receipt(route)

    # -- 登记 ---------------------------------------------------------------

    def create_entry(self, values: dict[str, Any]):
        entry, missing = super().create_entry(values)
        if missing or entry is None:
            return entry, missing
        points = normalize_points(values.get("轨迹点") or values.get("点序"))
        if points:
            entry["轨迹点"] = points
        entry["版次"] = 1
        entry["待办请求"] = []
        entry["验证回执"] = []
        return entry, []

    # -- 动作 ---------------------------------------------------------------

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        route = store.find(self.MODULE, entry_id)
        if route is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        self._hydrate(route)

        if action in (SIGN_OFF_ACTION, REQUEST_SIGN_OFF_ACTION):
            return self._sign_off(route)
        if action == DRAW_ACTION:
            return self._draw(route)
        if action == REQUEST_UPDATE_ACTION:
            return self._request_update(route)
        return super().run_action(entry_id, action)

    # 兼容基类调用同名动作
    def verify_signoff(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        return self.run_action(entry_id, SIGN_OFF_ACTION)

    def _sign_off(self, route: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = str(route.get("status", ""))
        drawn_version = route.get("已绘制版次")
        current_version = route_version(route)

        # 跳级验证：路线从未绘制过。
        if status == "待绘制" or drawn_version in (None, ""):
            return None, "迁徙路径尚未绘制，不能办理验证签认；请先完成绘制路线"
        if int(drawn_version) == current_version and status == "待更新":
            # 当前待更新版次尚未重新绘制，没有可签认的已绘制版。
            return None, (
                f"第{current_version}版为现场补报点形成的待更新版次，尚未重新绘制，不能直接签认；"
                f"请先重新绘制路线"
            )

        points = drawn_points(route)
        complete, reason = inspect_points(points)
        if not complete:
            return None, f"路线点序不完整，不能办理正式签认：{reason}"

        update_pending = is_update_pending(route)
        existing = receipt_for_version(int(route.get("id", 0)), int(drawn_version))
        receipt = issue_signoff(
            route,
            points,
            signer=str(route.get("记录人") or "记录人"),
            source="已绘制版签认",
            update_pending=update_pending,
            version=int(drawn_version),
        )
        duplicate = existing is not None
        route["已签认版次"] = int(drawn_version)
        route["验证状态"] = "已验证"
        if update_pending and current_version > int(drawn_version):
            # 现场补报点到达后签认的是已绘制版，更新请求保持待办理。
            route["status"] = "待更新"
        else:
            route["status"] = "已验证"
            self._settle_request(route, REQUEST_UPDATE_ACTION)
        route["pending"] = True
        route["abnormal"] = False

        prefix = "已存在正式签认，未重复签发" if duplicate else "已验证签认"
        message = f"{self.ENTITY}{prefix}，回执 {receipt['回执编号']}（第{receipt['路线版次']}版）"
        if update_pending and current_version > int(drawn_version):
            message += (
                f"；第{current_version}版为现场补报待更新，本次签认仅覆盖第{drawn_version}版，"
                f"需接办复核"
            )
        return route, message

    def _draw(self, route: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = str(route.get("status", ""))
        if status == "已验证" and not is_update_pending(route):
            return route, "路线已正式签认，无需重复绘制"
        # 重新绘制落在当前工作版次上：现场补报点已经开出下一个版次，
        # 就绘制该新版；没有待更新版次时沿用当前版次。
        route["已绘制版次"] = route_version(route)
        record_drawn_points(route)
        route["status"] = "已绘制"
        route["pending"] = True
        route["abnormal"] = False
        self._settle_request(route, REQUEST_UPDATE_ACTION)
        return route, f"{self.ENTITY}已绘制（第{route['版次']}版），可办理验证签认"

    def _request_update(self, route: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        requests = route.setdefault("待办请求", [])
        duplicate = any(
            req.get("动作") == REQUEST_UPDATE_ACTION and req.get("状态") == "待办理"
            for req in requests
        )
        status = str(route.get("status", ""))
        signed_version = route.get("已签认版次")

        if status == "待更新":
            if not duplicate:
                requests.append({"动作": REQUEST_UPDATE_ACTION, "状态": "待办理", "版次": route_version(route)})
            return route, "现场补报更新已在待办理队列，未重复登记"

        if status == "已验证" or signed_version not in (None, ""):
            # 已签认版继续有效，现场补报点另起一个待更新版次并行处理。
            if duplicate:
                return route, "现场补报更新已在待办理队列，未重复登记"
            next_version = max(route_version(route), int(signed_version or 0)) + 1
            route["版次"] = next_version
            route["status"] = "待更新"
            route["pending"] = True
            route["abnormal"] = False
            requests.append({"动作": REQUEST_UPDATE_ACTION, "状态": "待办理", "版次": next_version})
            return route, (
                f"现场补报点已登记为第{next_version}版，路线转为待更新；"
                f"第{signed_version}版签认回执继续有效，待重新绘制后接办复核"
            )

        if status == "已绘制":
            # 已绘制未签认：补报点开出一个新的工作版次，已绘制版仍可签认，
            # 两张到达顺序不同，结论保持一致。
            if duplicate:
                return route, "现场补报更新已在待办理队列，未重复登记"
            next_version = route_version(route) + 1
            route["版次"] = next_version
            route["status"] = "待更新"
            route["pending"] = True
            route["abnormal"] = False
            requests.append({"动作": REQUEST_UPDATE_ACTION, "状态": "待办理", "版次": next_version})
            return route, (
                f"现场补报点已登记为第{next_version}版，路线转为待更新；"
                f"第{next_version - 1}版仍可办理签认，第{next_version}版需重新绘制后接办复核"
            )

        # 尚未绘制：补报点只是登记为待办，绘制时一并纳入。
        if not duplicate:
            requests.append({"动作": REQUEST_UPDATE_ACTION, "状态": "待办理", "版次": route_version(route)})
        return route, f"现场补报更新申请已登记，待绘制后一并纳入第{route_version(route)}版"

    def _settle_request(self, route: dict[str, Any], action: str) -> None:
        for request in route.get("待办请求", []):
            if request.get("动作") == action and request.get("状态") == "待办理":
                request["状态"] = "已办理"

    # -- 跨模块读取 ---------------------------------------------------------

    def route_evaluation(self, entry_id: int) -> dict[str, Any] | None:
        entry = self.get_entry(entry_id)
        if entry is None:
            return None
        return evaluate_route(entry)

    def inclusion_snapshot(self) -> dict[str, Any]:
        for route in store.rows(self.MODULE):
            ensure_route_versions(route)
        return compile_inclusions()

    def receipt_ledger(self, route_id: int | None = None, decision: str | None = None) -> dict[str, Any]:
        return list_receipts(route_id=route_id, decision=decision)

    def domain_snapshot(self) -> dict[str, Any]:
        snapshot = super().domain_snapshot()
        inclusions = compile_inclusions()
        snapshot["receipts"] = len(inclusions["included_routes"]) + len(inclusions["pending_routes"])
        snapshot["included_routes"] = inclusions["route_count"]
        snapshot["pending_routes"] = inclusions["pending_count"]
        return snapshot
