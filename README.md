# 野生动物追踪与研究系统

生态学家、野外考察队员和数据分析师共同追踪野生动物活动轨迹，记录行为观测数据，分析种群迁徙规律后按研究周期汇总报告。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 物种登记 | `species_register` | 物种档案 | 物种名称、保护等级、分布区域 |
| 追踪设备 | `tracking_device` | 设备档案 | 设备编号、设备类型、佩戴对象 |
| 位置记录 | `location_record` | 位置数据 | 设备编号、经纬度、海拔高度 |
| 行为观测 | `behavior_observe` | 观测记录 | 观测对象、行为类型、起止时间 |
| 栖息地调查 | `habitat_survey` | 调查数据 | 调查区域、植被类型、水源距离 |
| 种群普查 | `population_census` | 普查记录 | 普查区域、目标物种、调查方法 |
| 迁徙路线 | `migration_track` | 迁徙路径 | 追踪个体、起点区域、途经区域 |
| 救护记录 | `rescue_record` | 救护档案 | 救护对象、发现地点、伤病情況 |
| 遗传样本 | `genetic_sample` | 样本档案 | 样本编号、来源个体、样本类型 |
| 巡护记录 | `patrol_record` | 巡护日志 | 巡护路线、巡护人员、发现情况 |
| 影像档案 | `photo_archive` | 影像记录 | 拍摄对象、拍摄地点、影像类型 |
| 研究成果 | `research_output` | 研究产出 | 成果标题、研究主题、作者团队 |
| 威胁评估 | `threat_assessment` | 评估报告 | 评估对象、威胁类别、威胁程度 |
| 装备管理 | `equipment_mgmt` | 装备档案 | 装备名称、装备类型、购入日期 |
| 公众宣教 | `public_education` | 宣教资料 | 资料名称、宣教主题、目标受众 |
| 合作项目 | `cooperation_project` | 项目档案 | 项目名称、合作机构、项目周期 |
| 数据分析 | `data_analysis` | 分析记录 | 分析主题、数据来源、分析方法 |
| 年度总结 | `annual_summary` | 总结报告 | 报告年份、覆盖物种、主要发现 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

领域：应用开发
子方向：web前端/全栈开发

## 迁徙路线验证签认与年度总结纳入

- `验证路线` 只能对「已绘制且完整点序」的版次办理；从 `待绘制` 直接验证会被拒绝，
  点序不连续或缺经纬度也不会签发回执。每办理一次签认产生一份
  `验证签认回执`（编号 `VR-<年>-<序号>`），重复提交沿用同一份回执。
- 同一路线可以有两张到达：一张是已绘制版签认，一张是现场补报点引起的 `更新路线`。
  补报点会开出新的工作版次，旧版回执继续有效；路线评估给出「本次可采用第 N 版」
  与「第 M 版需接办复核」，两种到达顺序结论一致。
- `年度总结` 的 `提交报告` 凭回执冻结纳入清单：同一路线只计一次，纳入版次与
  `/api/cross/verification/inclusions`（现场验证清单）一致；已提交/已审核/已发布
  的报告回查时仍显示提交当时的版次与回执编号。存量 `已验证` 路线会补发
  `历史存量认定` 回执，兼容既有总结。
- 接口：
  - `GET /api/cross/verification/route/{id}` 单条路线签认与纳入结论
  - `GET /api/cross/verification/receipts` 现场验证回执清单
  - `GET /api/cross/verification/inclusions` 按路线去重的纳入清单
  - `GET /api/annual_summary/{id}` 报告详情（含纳入回执与版次）
  - `GET /api/cross/annual-summary?year=YYYY` 年度汇总（含 `inclusions`）

测试：`backend/.venv/bin/python backend/tests/test_migration_verification.py`
（以及原有的 `backend/tests/test_cross_module.py`）。
