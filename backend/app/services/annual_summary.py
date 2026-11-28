"""年度总结领域服务：提交时凭验证签认回执认定路线成果并冻结纳入清单。

报告提交处集中核对：同一路线只计一次、来源与验证状态取自同一份
回执、纳入版次与现场验证清单一致。已提交/已审核/已发布的报告保留
提交当时的路线版次与回执编号，回查不随路线后续更新而漂移。
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from app.store import store
from app.services.base import BaseModuleService
from app.verification import (
    compile_inclusions,
    evaluate_route,
    find_receipt,
    ensure_legacy_receipt,
    formal_receipts,
    route_version,
)
from app.services.migration_track import MigrationTrackService

ROUTE_MODULE = "migration_track"
FROZEN_STATUSES = {"已提交", "已审核", "已发布"}
REPORT_ACTION = "提交报告"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class AnnualSummaryService(BaseModuleService):
    MODULE = "annual_summary"
    ENTITY = "总结报告"
    OPERATION_TERM = "提交报告"
    LIST_FIELDS = ["报告年份", "覆盖物种", "主要发现", "数据总量", "保护建议", "编制人", "报告状态", "备注说明"]
    REQUIRED_FIELDS = ["报告年份", "覆盖物种", "主要发现"]
    STATUS_ORDER = ["编制中", "已提交", "已审核", "已发布"]
    ACTION_RULES = {"提交报告": "已提交", "审核通过": "已审核", "发布报告": "已发布"}
    NEGATIVE_ACTIONS = []

    # -- 动作 ---------------------------------------------------------------

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        if action == REPORT_ACTION:
            return self._submit(entry)
        if action == "审核通过" and entry.get("报告状态") != "已提交":
            return None, "报告尚未提交，不能审核通过"
        if action == "发布报告" and entry.get("报告状态") not in ("已提交", "已审核"):
            return None, "报告尚未提交或审核，不能发布"
        entry, message = super().run_action(entry_id, action)
        if entry is not None:
            entry["报告状态"] = entry.get("status", entry.get("报告状态"))
            if action in ("审核通过", "发布报告"):
                # 后续流转不得改写提交时冻结的纳入清单。
                self.report_basis(entry)
        return entry, message

    def _submit(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry.get("报告状态") in FROZEN_STATUSES:
            message = "报告已提交，纳入清单与签认回执保持不变"
            existing = self.report_basis(entry) or {}
            if existing:
                message += f"（纳入{existing.get('route_count', 0)}条已正式签认路线）"
            return entry, message

        compilation = compile_inclusions()
        for route in store.rows(ROUTE_MODULE):
            if route.get("status") == "已验证":
                ensure_legacy_receipt(route)

        included = compilation["included_routes"]
        frozen = {
            "basis_version": compilation["basis_version"],
            "compiled_at": compilation["compiled_at"],
            "route_count": len(included),
            "included_count": len(included),
            "pending_count": compilation["pending_count"],
            "included_routes": copy.deepcopy(included),
            "pending_routes": copy.deepcopy(compilation["pending_routes"]),
            "receipt_numbers": list(compilation["receipt_numbers"]),
            "included_versions": copy.deepcopy(compilation["included_versions"]),
            "route_status_source": {str(item["route_id"]): item["当前状态"] for item in included},
        }

        entry["纳入清单"] = frozen
        entry["纳入路线数"] = frozen["route_count"]
        entry["纳入回执"] = unique_receipts(included)
        entry["纳入版次"] = copy.deepcopy(compilation["included_versions"])
        entry["纳入依据"] = (
            f"验证签认回执：{frozen['route_count']}条已正式签认路线，"
            f"{frozen['pending_count']}条待复核/待签认未纳入"
        )
        entry["现场验证清单"] = copy.deepcopy(compilation["included_versions"])
        entry["待复核清单"] = [
            {
                "route_id": item["route_id"],
                "track_individual": item["追踪个体"],
                "current_version": item["当前状态"] and item["版次"],
                "included_version": item["可取得版次"],
                "reason": item["说明"],
            }
            for item in compilation["pending_routes"]
        ]
        entry["报告状态"] = "已提交"
        entry["status"] = "已提交"
        entry["pending"] = True
        entry["abnormal"] = False

        message = (
            f"{self.ENTITY}已提交，凭验证签认回执纳入{frozen['route_count']}条路线（去重后每条路线计一次）"
        )
        if frozen["pending_count"]:
            message += f"；另有{frozen['pending_count']}条待复核/待签认，暂不纳入"
        return entry, message

    # -- 回查 ---------------------------------------------------------------

    def report_basis(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """返回报告冻结的纳入依据；存量报告按当年路线补出可回查的版次。"""
        frozen = entry.get("纳入清单")
        if isinstance(frozen, dict) and "included_routes" in frozen:
            # 已冻结（哪怕是空清单）都直接回查，不再按当前路线重建。
            return frozen
        if entry.get("报告状态") in FROZEN_STATUSES or entry.get("status") in FROZEN_STATUSES:
            rebuilt = self._rebuild_legacy_basis(entry)
            if rebuilt is not None:
                entry["纳入清单"] = rebuilt
                return rebuilt
        return None

    def _rebuild_legacy_basis(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """兼容既有总结：从历史「已验证」路线补发回执并固定纳入版次。"""
        year = str(entry.get("报告年份", ""))
        included: list[dict[str, Any]] = []
        for route in sorted(store.rows(ROUTE_MODULE), key=lambda row: int(row.get("id", 0))):
            if route.get("status") != "已验证":
                continue
            receipt = ensure_legacy_receipt(route)
            if receipt is None:
                continue
            evaluation = evaluate_route(route)
            included.append(evaluation)
        if not included:
            return None
        return {
            "basis_version": "legacy-receipt-v1",
            "compiled_at": str(entry.get("提交时间") or entry.get("报告年份") or "历史报告"),
            "year": year,
            "route_count": len(included),
            "included_count": len(included),
            "pending_count": 0,
            "included_routes": included,
            "pending_routes": [],
            "receipt_numbers": [item["回执编号"] for item in included if item.get("回执编号")],
            "included_versions": [
                {"route_id": item["route_id"], "version": item["纳入版次"], "receipt_no": item["回执编号"]}
                for item in included
            ],
            "route_status_source": {str(item["route_id"]): item["当前状态"] for item in included},
            "legacy": True,
        }

    def report_detail(self, entry: dict[str, Any]) -> dict[str, Any]:
        """报告详情：返回同一份验证签认回执作为纳入凭据及当时的版次。"""
        basis = self.report_basis(entry)
        detail = copy.deepcopy(entry)
        detail["纳入清单"] = basis
        if basis:
            routes = basis.get("included_routes", [])
            for item in routes:
                receipt = find_receipt(item.get("回执编号") or "")
                item["回执"] = copy.deepcopy(receipt) if receipt else item.get("receipt")
            detail["纳入路线数"] = basis.get("route_count", 0)
            detail["纳入版次"] = basis.get("included_versions", [])
            detail["纳入回执"] = [
                {
                    "回执编号": item.get("回执编号"),
                    "路线编号": item.get("route_id"),
                    "纳入版次": item.get("纳入版次"),
                    "来源": item.get("来源"),
                    "验证状态": item.get("验证状态"),
                }
                for item in routes
            ]
            detail["现场验证清单"] = basis.get("included_versions", [])
            detail["纳入依据"] = (
                f"验证签认回执：纳入{basis['route_count']}条路线，"
                f"清单与现场验证一致"
            )
        else:
            detail["纳入依据"] = "报告尚未提交，暂无纳入凭据"
        return detail

    def evidence_for_year(self, year: int) -> dict[str, Any]:
        """现场验证清单的纳入版次：供报告提交处与回查共用。"""
        compilation = compile_inclusions()
        return {
            "year": year,
            "included_versions": compilation["included_versions"],
            "route_count": compilation["route_count"],
            "pending_count": compilation["pending_count"],
        }


def unique_receipts(included: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一路线只保留一份现行回执，防止重复签认被计多次。"""
    seen: dict[str, dict[str, Any]] = {}
    for item in included:
        number = item.get("回执编号")
        if number and number not in seen:
            receipt = find_receipt(number)
            seen[number] = copy.deepcopy(receipt) if receipt else {
                "回执编号": number,
                "路线编号": item.get("route_id"),
                "纳入版次": item.get("纳入版次"),
            }
    return list(seen.values())
