<template>
  <section class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :data-testid="`row-${row.id}`"
          :data-status="String(row.status)"
          :class="{ 'row-selected': Number(row.id) === selectedId }"
          @click="selectRoute(row)"
        >
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              :disabled="isBlocked(row, action)"
              :title="blockedReason(row, action)"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="meta.fields.length + 2" class="empty-state">
            暂无{{ meta.name }}数据，可先登记{{ meta.entity }}
          </td>
        </tr>
      </tbody>
    </table>

    <section v-if="meta.key === 'annual_summary' && reportDetail" class="detail-panel" data-testid="report-detail">
      <h3>报告详情 · 纳入凭据</h3>
      <p class="detail-note">
        {{ reportDetail.纳入依据 }}
        <span v-if="reportDetail.纳入清单">（纳入清单生成于 {{ reportDetail.纳入清单.compiled_at }}）</span>
      </p>
      <table v-if="reportDetail.纳入回执?.length" class="data-table">
        <thead>
          <tr><th>回执编号</th><th>路线编号</th><th>纳入版次</th><th>验证状态</th><th>来源</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in reportDetail.纳入回执" :key="item.回执编号" :data-testid="`report-receipt-${item.回执编号}`">
            <td>{{ item.回执编号 }}</td>
            <td>{{ item.路线编号 }}</td>
            <td>第 {{ item.纳入版次 }} 版</td>
            <td>{{ item.验证状态 }}</td>
            <td>{{ item.来源 }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-state">报告尚未提交，暂无验证签认回执</p>
      <div v-if="reportDetail.纳入清单?.pending_routes?.length" class="pending-block">
        <h4>未纳入 · 待复核或待签认</h4>
        <ul>
          <li v-for="item in reportDetail.纳入清单.pending_routes" :key="item.route_id">
            路线 #{{ item.route_id }}（{{ item.追踪个体 }}）：{{ item.纳入结论 }} — {{ item.说明 }}
          </li>
        </ul>
      </div>
    </section>

    <section v-if="meta.key === 'migration_track' && routeEvaluation" class="detail-panel" data-testid="route-evaluation">
      <h3>签认与纳入结论</h3>
      <p class="detail-note">{{ routeEvaluation.说明 }}</p>
      <p>
        当前状态 {{ routeEvaluation.当前状态 }} · 已绘制第 {{ routeEvaluation.已绘制版次 ?? '—' }} 版 ·
        已签认第 {{ routeEvaluation.已签认版次 ?? '—' }} 版 · 本次可采用第
        {{ routeEvaluation.纳入版次 ?? '—' }} 版
      </p>
      <p v-if="routeEvaluation.需复核" class="error-text">
        第 {{ routeEvaluation.待复核版次 }} 版需接办复核后再替换纳入版次
      </p>
      <p v-if="routeEvaluation.回执编号">回执 {{ routeEvaluation.回执编号 }}（{{ routeEvaluation.验证状态 }}）</p>
    </section>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createEntry,
  downloadEntries,
  getReportDetail,
  getRouteEvaluation,
  listEntries,
  moduleMeta,
  runAction as applyAction,
} from '@/api/backend-service'
import type { EntryRow, ReportDetail, RouteEvaluation } from '@/data/types'

const props = defineProps<{ moduleKey: string }>()
const meta = moduleMeta(props.moduleKey)
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = meta.fields.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const reportDetail = ref<ReportDetail | null>(null)
const routeEvaluation = ref<RouteEvaluation | null>(null)
const selectedId = ref(0)

// 验证入口只对「已绘制且点序完整」的路线开放；待绘制不允许跳级签认。
// 后端仍做最终校验，这里只是把明显不可执行的动作置灰并给出原因。
function isBlocked(row: EntryRow, action: string): boolean {
  if (meta.key !== 'migration_track' || action !== '验证路线') return false
  return String(row.status) === '待绘制'
}

function blockedReason(row: EntryRow, action: string): string {
  if (!isBlocked(row, action)) return ''
  return '路线尚未绘制，不能跳级验证；请先执行绘制路线'
}

function availableActions(row: EntryRow): string[] {
  if (meta.key === 'migration_track' && String(row.status) === '待绘制') {
    return meta.actions.filter((action) => action !== '验证路线')
  }
  return meta.actions
}

async function refreshDetail() {
  reportDetail.value = null
  routeEvaluation.value = null
  if (meta.key === 'annual_summary') {
    const candidate = rows.value.find((row) => Number(row.id) === selectedId.value) ?? rows.value[0]
    if (candidate) {
      selectedId.value = Number(candidate.id)
      reportDetail.value = await getReportDetail(Number(candidate.id)).catch(() => null)
    }
  }
  if (meta.key === 'migration_track') {
    const candidate = rows.value.find((row) => Number(row.id) === selectedId.value) ?? rows.value[0]
    if (candidate) {
      selectedId.value = Number(candidate.id)
      routeEvaluation.value = await getRouteEvaluation(Number(candidate.id)).catch(() => null)
    }
  }
}

async function selectRoute(row: EntryRow) {
  selectedId.value = Number(row.id)
  await refreshDetail()
}
const stats = computed(() => [
  { label: meta.metrics[0], value: total.value },
  { label: meta.metrics[1], value: rows.value.filter((row) => row.status === meta.statuses[1]).length },
  {
    label: meta.metrics[2],
    value: rows.value.filter((row) => row.status === meta.statuses[meta.statuses.length - 1]).length,
  },
])
const statusSummary = computed(() =>
  meta.statuses.map((status) => ({
    status,
    count: rows.value.filter((row) => String(row.status) === status).length,
  })),
)

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  try {
    await downloadEntries(meta.key, filters.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(meta.fields.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await createEntry(meta.key, createValues.value)
    if (!result.ok) throw new Error(result.message)
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: EntryRow) {
  errorMessage.value = ''
  try {
    const result = await applyAction(meta.key, Number(row.id), action)
    if (!result.ok) throw new Error(result.message)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await listEntries(meta.key, filters.value)
    rows.value = payload.items
    total.value = payload.total
    await refreshDetail()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '业务列表读取失败'
  }
}

onMounted(reload)
</script>
