"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import cross_module, resource

# 跨模块固定路径先注册，避免 /api/cross/annual-summary 被 /api/{module}/{entry_id} 抢先匹配。
ROUTERS = [cross_module, resource]
