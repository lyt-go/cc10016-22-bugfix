import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type {
  ActionResult,
  EntryRow,
  OverviewResult,
  PageResult,
  ReportDetail,
  RouteEvaluation,
} from '@/data/types'

export { moduleMeta }

// 验证签认回执与报告纳入详情走资源详情接口；年度总结详情已内含回执。
export async function getReportDetail(id: number): Promise<ReportDetail> {
  const result = await getEntry('annual_summary', id)
  return result as ReportDetail
}

export async function getRouteEvaluation(id: number): Promise<RouteEvaluation | null> {
  const response = await request(`/api/cross/verification/route/${id}`)
  if (response.status === 404) return null
  if (!response.ok) throw new Error('路线签认状态读取失败')
  return (await response.json()) as RouteEvaluation
}

export async function getVerificationReceipts(): Promise<{ items: unknown[]; total: number }> {
  const response = await request('/api/cross/verification/receipts')
  if (!response.ok) throw new Error('验证签认回执读取失败')
  return await response.json()
}

export async function getEntry(key: string, id: number): Promise<EntryRow> {
  const response = await request(`/api/${key}/${id}`)
  if (!response.ok) throw new Error('业务详情读取失败')
  return await response.json()
}

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

// 跨模块数据流 API
export async function buildMigrationFromLocations(trackIndividual: string): Promise<any> {
  const response = await request(`/api/cross/migration/from-locations?track_individual=${encodeURIComponent(trackIndividual)}`)
  if (!response.ok) throw new Error('迁徙路线生成失败')
  return await response.json()
}

export async function analyzeBehavior(speciesName: string): Promise<any> {
  const response = await request(`/api/cross/analysis/from-behavior?species_name=${encodeURIComponent(speciesName)}`)
  if (!response.ok) throw new Error('行为分析失败')
  return await response.json()
}

export async function triggerThreatFromPatrol(patrolId: number): Promise<any> {
  const response = await request(`/api/cross/threat/from-patrol/${patrolId}`, { method: 'POST' })
  if (!response.ok) throw new Error('威胁评估触发失败')
  return await response.json()
}

export async function updateSpeciesFromCensus(censusId: number): Promise<any> {
  const response = await request(`/api/cross/species/from-census/${censusId}`, { method: 'POST' })
  if (!response.ok) throw new Error('普查同步失败')
  return await response.json()
}

export async function linkRescueToSpecies(rescueId: number): Promise<any> {
  const response = await request(`/api/cross/species/from-rescue/${rescueId}`, { method: 'POST' })
  if (!response.ok) throw new Error('救护关联失败')
  return await response.json()
}

export async function checkDeviceLocations(deviceCode: string): Promise<any> {
  const response = await request(`/api/cross/locations/from-device?device_code=${encodeURIComponent(deviceCode)}`)
  if (!response.ok) throw new Error('设备信号检查失败')
  return await response.json()
}

export async function createResearchFromGenetic(sampleId: number): Promise<any> {
  const response = await request(`/api/cross/research/from-genetic/${sampleId}`, { method: 'POST' })
  if (!response.ok) throw new Error('研究成果生成失败')
  return await response.json()
}

export async function buildAnnualSummary(year: number): Promise<any> {
  const response = await request(`/api/cross/annual-summary?year=${year}`)
  if (!response.ok) throw new Error('年度总结生成失败')
  return await response.json()
}

export async function loadDataQuality(): Promise<any> {
  const response = await request('/api/cross/overview/data-quality')
  if (!response.ok) throw new Error('数据质量概览读取失败')
  return await response.json()
}
