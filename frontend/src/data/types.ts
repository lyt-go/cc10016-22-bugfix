/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  [field: string]: string | number | boolean
}

export type ReceiptPoint = {
  序号: number
  经纬度: string
  区域?: string
}

/** 验证签认回执：年度总结与现场验证共用同一份凭据。 */
export type VerificationReceipt = {
  回执编号: string
  路线编号: number
  追踪个体: string
  路线版次: number
  纳入版次: number
  签认状态: string
  验证状态: string
  签认人: string
  签认时间: string
  来源: string
  更新待复核?: boolean
  点序?: ReceiptPoint[]
}

/** 单条路线的纳入结论：本次可采用哪一版、哪一版要接办复核。 */
export type RouteEvaluation = {
  route_id: number
  追踪个体: string
  当前状态: string
  版次: number
  已绘制版次: number | null
  已签认版次: number | null
  纳入版次: number | null
  纳入结论: string
  复核状态: string
  需复核: boolean
  待复核版次: number | null
  说明: string
  回执编号: string | null
  验证状态: string | null
  receipt: VerificationReceipt | null
}

export type ReportBasis = {
  basis_version: string
  compiled_at: string
  route_count: number
  pending_count: number
  included_routes: RouteEvaluation[]
  pending_routes: RouteEvaluation[]
  included_versions: { route_id: number; version: number; receipt_no: string }[]
  receipt_numbers: string[]
  legacy?: boolean
}

export type ReportDetail = EntryRow & {
  纳入依据: string
  纳入路线数?: number
  纳入回执?: { 回执编号: string; 路线编号: number; 纳入版次: number; 来源: string; 验证状态: string }[]
  纳入清单?: ReportBasis | null
  待复核清单?: { route_id: number; track_individual: string; current_version: number; included_version: number | null; reason: string }[]
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}
