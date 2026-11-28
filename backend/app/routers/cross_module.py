"""跨模块数据流API：暴露位置→迁徙、观测→分析、巡护→威胁等跨模块数据链路。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.cross_module import (
    analyze_behavior_for_data_analysis,
    build_annual_summary,
    build_migration_from_locations,
    check_device_signal_for_locations,
    link_genetic_to_research,
    link_rescue_to_species,
    trigger_threat_from_patrol,
    update_species_population_from_census,
)

router = APIRouter(prefix="/api/cross", tags=["跨模块数据流"])


@router.get("/migration/from-locations")
def get_migration_from_locations(track_individual: str):
    """将位置记录聚合为迁徙路线。"""
    result = build_migration_from_locations(track_individual)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/analysis/from-behavior")
def get_analysis_from_behavior(species_name: str):
    """从行为观测数据生成行为模式分析。"""
    result = analyze_behavior_for_data_analysis(species_name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/threat/from-patrol/{patrol_id}")
def create_threat_from_patrol(patrol_id: int):
    """根据巡护记录自动创建威胁评估。"""
    result = trigger_threat_from_patrol(patrol_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/species/from-census/{census_id}")
def update_species_from_census(census_id: int):
    """将普查数据同步更新到物种登记。"""
    result = update_species_population_from_census(census_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/species/from-rescue/{rescue_id}")
def link_species_from_rescue(rescue_id: int):
    """将救护记录关联到物种档案。"""
    result = link_rescue_to_species(rescue_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/locations/from-device")
def check_locations_by_device(device_code: str):
    """根据设备信号状态标注异常位置数据。"""
    result = check_device_signal_for_locations(device_code)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/research/from-genetic/{sample_id}")
def create_research_from_genetic(sample_id: int):
    """将遗传样本送检结果创建为研究成果。"""
    result = link_genetic_to_research(sample_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/annual-summary")
def get_annual_summary(year: int):
    """汇总全年多源数据生成年度总结。"""
    result = build_annual_summary(year)
    return result


@router.get("/verification/receipts")
def get_verification_receipts(route_id: int | None = None, decision: str | None = None):
    """现场验证清单：签认回执及其对应当前版次与纳入结论。"""
    from app.services import service_for

    service = service_for("migration_track")
    return service.receipt_ledger(route_id=route_id, decision=decision)


@router.get("/verification/route/{route_id}")
def get_route_evaluation(route_id: int):
    """单条路线的签认状态与本次可采用/需复核的版次。"""
    from app.services import service_for

    service = service_for("migration_track")
    evaluation = service.route_evaluation(route_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail=f"迁徙路径 {route_id} 不存在或已归档")
    return evaluation


@router.get("/verification/inclusions")
def get_verification_inclusions():
    """按路线去重的纳入清单，汇总与现场验证共用同一批回执。"""
    from app.services import service_for

    service = service_for("migration_track")
    return service.inclusion_snapshot()


@router.get("/overview/data-quality")
def get_data_quality_overview():
    """全系统数据质量概览：各模块异常率、完整性评估等。"""
    from app.services import service_for

    modules = [
        "species_register", "tracking_device", "location_record", "behavior_observe",
        "habitat_survey", "population_census", "migration_track", "rescue_record",
        "genetic_sample", "patrol_record", "photo_archive", "research_output",
        "threat_assessment", "equipment_mgmt", "public_education",
        "cooperation_project", "data_analysis", "annual_summary",
    ]
    quality = {}
    for mod in modules:
        svc = service_for(mod)
        if svc:
            snap = svc.domain_snapshot()
            total = snap["count"]
            abnormal = snap["abnormal"]
            quality[mod] = {
                "entity": snap["entity"],
                "total": total,
                "abnormal": abnormal,
                "quality": "正常" if total == 0 or abnormal / total < 0.3 else "需关注",
                "by_status": snap["by_status"],
            }

    total_all = sum(v["total"] for v in quality.values())
    total_abnormal = sum(v["abnormal"] for v in quality.values())

    return {
        "overall_quality": "正常" if total_all == 0 or total_abnormal / total_all < 0.2 else "需关注",
        "total_records": total_all,
        "total_abnormal": total_abnormal,
        "modules": quality,
    }