"""迁徙路线验证签认回执与年度总结纳入测试。

覆盖：
  - 待绘制路线跳级验证被拒绝
  - 已绘制且点序完整才能正式签认
  - 重复签认只产生一份回执
  - 已绘制版签认 + 现场补报更新并存时，报告可采用旧版并标记复核
  - 年度总结提交按路线去重，纳入版次与现场验证清单一致
  - 已发布报告仍能回查当时纳入的版次
  - 存量「已验证」路线兼容纳入
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cross_module import build_annual_summary
from app.services import service_for
from app.services.annual_summary import AnnualSummaryService
from app.services.migration_track import MigrationTrackService
from app.store import store
from app.verification import RECEIPTS, formal_receipts


def _create_route(name: str, points: list[dict] | None = None) -> int:
    service = service_for("migration_track")
    entry, missing = service.create_entry({
        "追踪个体": name,
        "起点区域": f"{name}-起点",
        "途经区域": f"{name}-途经",
        "终点区域": f"{name}-终点",
        "记录人": f"{name}-记录人",
        "记录时段": "2026-05-01",
        **({"轨迹点": points} if points else {}),
    })
    assert not missing and entry is not None
    return int(entry["id"])


def _create_report(year: str) -> int:
    service = service_for("annual_summary")
    entry, missing = service.create_entry({
        "报告年份": year,
        "覆盖物种": "全物种",
        "主要发现": "测试发现",
        "编制人": "测试编制员",
        "备注说明": "",
    })
    assert not missing and entry is not None
    return int(entry["id"])


class TestVerificationEntry(unittest.TestCase):
    """验证入口不得放行未绘制或点序不完整的路线。"""

    def test_pending_route_cannot_be_verified(self):
        """待绘制路线点击验证必须被拒绝，状态保持待绘制。"""
        track = service_for("migration_track")
        route_id = _create_route("跳级验证")
        entry, message = track.run_action(route_id, "验证路线")
        self.assertIsNone(entry)
        self.assertIn("尚未绘制", message)
        self.assertEqual(store.find("migration_track", route_id)["status"], "待绘制")
        self.assertEqual(formal_receipts(route_id), [])

    def test_incomplete_point_sequence_rejected(self):
        """已绘制但点序不连续/缺坐标时不能正式签认。"""
        track = service_for("migration_track")
        route_id = _create_route("点序不完整", [
            {"序号": 1, "经纬度": "30.0,120.0"},
            {"序号": 3, "经纬度": "30.2,120.2"},
        ])
        track.run_action(route_id, "绘制路线")
        entry, message = track.run_action(route_id, "验证路线")
        self.assertIsNone(entry)
        self.assertIn("点序不完整", message)
        self.assertEqual(formal_receipts(route_id), [])

    def test_drawn_route_with_complete_points_can_sign(self):
        """已绘制且点序完整的路线可办理正式签认。"""
        track = service_for("migration_track")
        route_id = _create_route("正常签认", [
            {"序号": 1, "经纬度": "30.0,120.0"},
            {"序号": 2, "经纬度": "30.1,120.1"},
            {"序号": 3, "经纬度": "30.2,120.2"},
        ])
        track.run_action(route_id, "绘制路线")
        entry, message = track.run_action(route_id, "验证路线")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "已验证")
        self.assertEqual(len(formal_receipts(route_id)), 1)
        evaluation = track.route_evaluation(route_id)
        self.assertEqual(evaluation["纳入结论"], "可采用")
        self.assertEqual(evaluation["纳入版次"], 1)

    def test_duplicate_signoff_keeps_single_receipt(self):
        """重复提交验证只记一次正式签认。"""
        track = service_for("migration_track")
        route_id = _create_route("重复签认")
        track.run_action(route_id, "绘制路线")
        track.run_action(route_id, "验证路线")
        before = len(formal_receipts(route_id))
        _, message = track.run_action(route_id, "验证路线")
        self.assertIn("未重复签发", message)
        self.assertEqual(len(formal_receipts(route_id)), before)
        self.assertEqual(before, 1)


class TestDualArrival(unittest.TestCase):
    """同一路线两个到达动作：已绘制版签认 + 现场补报更新。"""

    def _prepare_both_open(self, name: str, sign_first: bool) -> int:
        track = service_for("migration_track")
        route_id = _create_route(name)
        track.run_action(route_id, "绘制路线")
        actions = ["验证路线", "更新路线"] if sign_first else ["更新路线", "验证路线"]
        for action in actions:
            track.run_action(route_id, action)
        return route_id

    def test_either_arrival_order_supports_old_version(self):
        """两种到达顺序都保留已绘制版回执，并标出待复核版次。"""
        for sign_first in (True, False):
            route_id = self._prepare_both_open(f"先后-{sign_first}", sign_first)
            evaluation = service_for("migration_track").route_evaluation(route_id)
            self.assertEqual(evaluation["纳入结论"], "可采用")
            self.assertEqual(evaluation["复核状态"], "需复核")
            self.assertEqual(evaluation["纳入版次"], 1)
            self.assertEqual(evaluation["待复核版次"], 2)
            self.assertIsNotNone(evaluation["回执编号"])

    def test_redraw_and_sign_new_version(self):
        """重新绘制后新版本可以正式签认，纳入版次随之更新。"""
        track = service_for("migration_track")
        route_id = self._prepare_both_open("重新绘制", True)
        track.run_action(route_id, "绘制路线")
        entry, _ = track.run_action(route_id, "验证路线")
        self.assertIsNotNone(entry)
        evaluation = track.route_evaluation(route_id)
        self.assertEqual(evaluation["纳入结论"], "可采用")
        self.assertEqual(evaluation["纳入版次"], 2)
        self.assertEqual(evaluation["复核状态"], "无")
        self.assertEqual(len(formal_receipts(route_id)), 2)


class TestAnnualInclusion(unittest.TestCase):
    """年度总结提交处的纳入核对。"""

    def setUp(self):
        self.track = service_for("migration_track")
        self.annual: AnnualSummaryService = service_for("annual_summary")

    def _signed_route(self, name: str) -> int:
        route_id = _create_route(name)
        self.track.run_action(route_id, "绘制路线")
        self.track.run_action(route_id, "验证路线")
        return route_id

    def test_submit_uses_receipt_and_dedupes(self):
        """提交后按路线去重，条数与回执数一致，同一路线只计一次。"""
        signed_a = self._signed_route("报告-A")
        signed_b = self._signed_route("报告-B")
        self.track.run_action(signed_b, "更新路线")  # 现场补报，仍沿用旧版回执

        report_id = _create_report("2040")
        entry, message = self.annual.run_action(report_id, "提交报告")
        self.assertIsNotNone(entry)
        self.assertIn("去重", message)

        basis = self.annual.report_basis(store.find("annual_summary", report_id))
        route_ids = [item["route_id"] for item in basis["included_routes"]]
        self.assertEqual(len(route_ids), len(set(route_ids)), "同一路线不得重复计数")
        for route_id in (signed_a, signed_b):
            self.assertIn(route_id, route_ids)

        included_versions = {item["route_id"]: item["version"] for item in basis["included_versions"]}
        self.assertEqual(included_versions[signed_a], 1)
        self.assertEqual(included_versions[signed_b], 1)
        pending = {item["route_id"] for item in basis["pending_routes"]}
        self.assertNotIn(signed_a, pending)

    def test_submit_matches_on_site_verification_list(self):
        """汇总中的纳入版次与现场验证清单一致。"""
        route_id = self._signed_route("清单一致")
        self.track.run_action(route_id, "更新路线")

        report_id = _create_report("2041")
        self.annual.run_action(report_id, "提交报告")
        entry = store.find("annual_summary", report_id)

        on_site = self.track.receipt_ledger(route_id=route_id)["items"]
        current = [item for item in on_site if item.get("is_current") or item.get("是否现行")]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["路线版次"], 1)
        self.assertEqual(current[0]["纳入结论"], "可采用")

        frozen = {item["route_id"]: item["version"] for item in entry["纳入版次"]}
        self.assertEqual(frozen[route_id], current[0]["路线版次"])

    def test_unverified_and_pending_are_not_included(self):
        """未签认（已绘制/待更新）的路线不纳入。"""
        drawn_only = _create_route("未签认")
        self.track.run_action(drawn_only, "绘制路线")
        unsigned_update = _create_route("未签认更新")
        self.track.run_action(unsigned_update, "绘制路线")
        self.track.run_action(unsigned_update, "更新路线")

        report_id = _create_report("2042")
        self.annual.run_action(report_id, "提交报告")
        basis = self.annual.report_basis(store.find("annual_summary", report_id))
        included = {item["route_id"] for item in basis["included_routes"]}
        pending = {item["route_id"] for item in basis["pending_routes"]}
        self.assertNotIn(drawn_only, included)
        self.assertNotIn(unsigned_update, included)
        self.assertIn(drawn_only, pending)
        self.assertIn(unsigned_update, pending)

    def test_published_report_keeps_historical_version(self):
        """提交后路线再更新，已发布报告仍回查当时的纳入版次。"""
        route_id = self._signed_route("回查")
        report_id = _create_report("2043")
        self.annual.run_action(report_id, "提交报告")
        self.annual.run_action(report_id, "审核通过")
        self.annual.run_action(report_id, "发布报告")

        # 提交后现场补报并重新签认到第 2 版
        self.track.run_action(route_id, "更新路线")
        self.track.run_action(route_id, "绘制路线")
        self.track.run_action(route_id, "验证路线")

        detail = self.annual.report_detail(store.find("annual_summary", report_id))
        frozen = {item["route_id"]: item["version"] for item in detail["纳入版次"]}
        self.assertEqual(frozen[route_id], 1, "已发布报告应保留提交时的版次")
        self.assertEqual(detail["status"], "已发布")

    def test_resubmit_keeps_frozen_basis(self):
        """重复提交不改写已冻结的纳入清单。"""
        route_id = self._signed_route("重复提交")
        report_id = _create_report("2044")
        self.annual.run_action(report_id, "提交报告")
        before = self.annual.report_basis(store.find("annual_summary", report_id))

        self.track.run_action(route_id, "更新路线")
        self.annual.run_action(report_id, "提交报告")
        after = self.annual.report_basis(store.find("annual_summary", report_id))
        self.assertEqual(before["included_versions"], after["included_versions"])
        self.assertEqual(before["compiled_at"], after["compiled_at"])

    def test_same_receipt_used_for_source_and_status(self):
        """纳入清单中每条路线的来源、验证状态与回执编号来自同一份回执。"""
        route_id = self._signed_route("同源核对")
        report_id = _create_report("2045")
        self.annual.run_action(report_id, "提交报告")
        basis = self.annual.report_basis(store.find("annual_summary", report_id))
        item = next(i for i in basis["included_routes"] if i["route_id"] == route_id)
        receipt = next(r for r in RECEIPTS if r["回执编号"] == item["回执编号"])
        self.assertEqual(item["来源"], receipt["来源"])
        self.assertEqual(item["验证状态"], receipt["签认状态"])
        self.assertEqual(item["纳入版次"], receipt["纳入版次"])


class TestLegacyCompatibility(unittest.TestCase):
    """既有总结与历史「已验证」路线的兼容。"""

    def test_legacy_verified_route_included(self):
        """存量已验证路线补发历史回执后被纳入且可回查版次。"""
        track = service_for("migration_track")
        evaluation = track.route_evaluation(3)  # 种子数据中的已验证路线
        self.assertEqual(evaluation["纳入结论"], "可采用")
        self.assertIsNotNone(evaluation["回执编号"])
        self.assertEqual(evaluation["纳入版次"], 1)

    def test_legacy_report_detail_rebuilds_basis(self):
        """存量已提交报告没有冻结清单时，按当年已验证路线补出可回查版次。"""
        annual: AnnualSummaryService = service_for("annual_summary")
        entry = store.find("annual_summary", 2)  # 种子数据中的已提交报告
        self.assertEqual(entry["status"], "已提交")
        detail = annual.report_detail(entry)
        self.assertIsNotNone(detail["纳入清单"])
        self.assertGreaterEqual(detail["纳入路线数"], 1)
        self.assertTrue(detail["纳入回执"])

    def test_cross_module_summary_counts_receipts(self):
        """跨模块年度汇总按正式签认回执统计路线数。"""
        result = build_annual_summary(2046)
        self.assertIn("inclusions", result)
        self.assertEqual(
            result["summary"]["verified_migrations"],
            result["inclusions"]["route_count"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
