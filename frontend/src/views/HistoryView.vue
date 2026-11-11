<template>
  <main class="history-page" aria-label="识别历史">
    <section class="history-list" aria-label="识别记录列表" :aria-hidden="viewMode === 'detail' || isClosing" :inert="viewMode === 'detail' || isClosing">
      <h1 class="history-list-title">记录</h1>
      <p v-if="listLoading" class="history-feedback" role="status">正在加载识别历史…</p>
      <p v-else-if="listError" class="history-feedback history-feedback--error" role="alert">{{ listError }}</p>
      <p v-else-if="total === 0" class="history-feedback">暂无识别记录</p>
      <div v-else class="history-list-layout" :class="{ 'history-list-layout--no-arrows': !showArrows }">
        <button v-if="showArrows" class="history-page-arrow history-page-arrow--previous" type="button" aria-label="上一条记录" :disabled="startIndex === 0 || loadingMore" @click="shiftWindow(-1)">
          <span aria-hidden="true"></span>
        </button>
        <div ref="rollViewport" class="history-rolls" :class="{ 'history-rolls--short': !showArrows }">
          <div ref="rollTrack" class="history-roll-track" :style="{ transform: `translate3d(${-startIndex * trackStep}px, 0, 0)` }">
            <button v-for="(record, index) in records" :key="record.id" class="history-roll" type="button" :tabindex="isRecordVisible(index) ? 0 : -1" :aria-hidden="!isRecordVisible(index)" :aria-describedby="tooltipRecordId === record.id ? 'history-date-tooltip' : undefined" :aria-label="recordAriaLabel(record)" @focus="onRollFocus(record, $event)" @blur="hideTooltip" @click="openRecord(record.id)">
              <img src="/assets/scrolls/history_scroll_closed.png" alt="" aria-hidden="true" />
              <span class="history-roll-name">{{ recognitionLabel(record) }}</span>
              <time class="history-roll-time" :datetime="record.created_at" @mouseenter="showTooltip(record, $event)" @mouseleave="hideTooltip" @click.stop.prevent="showTooltip(record, $event)">{{ formatLunarTimestamp(record.created_at) }}</time>
            </button>
          </div>
        </div>
        <button v-if="showArrows" class="history-page-arrow history-page-arrow--next" type="button" aria-label="下一条记录" :disabled="startIndex >= maxStart || loadingMore" @click="shiftWindow(1)">
          <span aria-hidden="true"></span>
        </button>
      </div>
      <p v-if="moreError && !listLoading" class="history-load-error" role="alert">{{ moreError }}</p>
      <p v-else-if="loadingMore" class="history-load-error" role="status">正在加载更多记录…</p>
    </section>

    <Transition name="history-backdrop">
      <div v-if="viewMode === 'detail'" class="history-backdrop" aria-hidden="true"></div>
    </Transition>

    <Transition name="history-detail" @after-leave="finishReturnToList">
    <section v-if="viewMode === 'detail'" class="history-detail" aria-label="单条识别记录详情">
      <div class="history-detail-actions">
        <button type="button" :disabled="deleting" @click="returnToList">返回</button>
        <button type="button" :disabled="deleting || detailLoading || !detailRecord" @click="removeRecord">
          {{ deleting ? '正在删除…' : '删除记录' }}
        </button>
      </div>
      <p v-if="deleteError" class="history-action-error" role="alert">{{ deleteError }}</p>
      <p v-if="detailLoading" class="history-feedback" role="status">正在加载识别记录…</p>
      <p v-else-if="detailError" class="history-feedback history-feedback--error" role="alert">{{ detailError }}</p>
      <Transition name="history-scroll">
      <div v-if="detailRecord" class="history-scroll">
        <img class="history-scroll-background" src="/assets/scrolls/history_scroll_open.png" alt="" aria-hidden="true" />
        <div class="history-scroll-content">
          <header class="history-scroll-meta">
            <h1>{{ recognitionLabel(detailRecord) }}</h1>
            <time :datetime="detailRecord.created_at">{{ formatLunarTimestamp(detailRecord.created_at) }}</time>
          </header>
          <div class="history-scroll-upper" :class="{ 'history-scroll-upper--low-confidence': !detailIsRecognized }">
            <div v-if="detailIsRecognized" class="history-herb-image">
              <img v-if="detailHerb && !herbImageError" :key="detailHerb.id" :src="detailHerb.image_url" :alt="detailHerb.name" @error="herbImageError = true" />
              <p v-else-if="herbImageError" class="history-inline-error" role="alert">药材插画加载失败</p>
            </div>
            <div class="history-intro">
              <template v-if="detailIsRecognized">
                <h2>中药材简介</h2>
                <p v-if="herbLoading" role="status">正在加载药材简介…</p>
                <p v-else-if="herbError" class="history-inline-error" role="alert">{{ herbError }}</p>
                <p v-else>{{ detailHerb?.recognition_intro }}</p>
              </template>
              <template v-else>
                <h2>识别失败</h2>
                <p>{{ LOW_CONFIDENCE_MESSAGE }}</p>
              </template>
            </div>
          </div>
          <div class="history-scroll-lower">
            <div class="history-upload-image">
              <img v-if="!uploadImageError" :key="detailRecord.id" :src="getHistoryImageUrl(detailRecord.id)" alt="本次上传的原始图片" @error="uploadImageError = true" />
              <p v-else class="history-inline-error" role="alert">原始图片加载失败</p>
            </div>
            <div v-if="detailIsRecognized" class="history-top3">
              <h2>置信度排名</h2>
              <ol>
                <li v-for="(item, index) in rankedTop3" :key="`${item.class_name}-${index}`">
                  <span class="history-rank">{{ index + 1 }}.</span>
                  <span class="history-rank-name">{{ item.class_name }}</span>
                  <span class="history-confidence-track" aria-hidden="true">
                    <span class="history-confidence-fill" :class="{ 'history-confidence-fill--first': index === 0 }" :style="{ width: `${safeProbability(item.probability) * 100}%` }"></span>
                  </span>
                  <span class="history-percent">{{ formatPercent(item.probability) }}</span>
                </li>
              </ol>
            </div>
          </div>
        </div>
      </div>
      </Transition>
    </section>
    </Transition>
    <Teleport to="body">
      <div v-if="tooltipRecordId !== null && viewMode === 'list'" id="history-date-tooltip" ref="tooltipElement" class="history-date-tooltip" role="tooltip" :style="tooltipPosition">{{ tooltipTime }}</div>
    </Teleport>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { deleteHistoryRecord, getHerb, getHerbs, getHistory, getHistoryImageUrl, getHistoryRecord } from '../api/index.js'
import { maxHistoryStart, moveHistoryStart } from '../utils/historyWindow.js'
import { formatGregorianTimestamp, formatLunarTimestamp } from '../utils/lunarTime.js'
import { isRecognitionSuccessful, LOW_CONFIDENCE_MESSAGE } from '../utils/recognitionStatus.js'
import '../styles/history.css'

const pageSize = 8
const desktopVisibleCount = 4
const total = ref(0)
const records = ref([])
const loadedPage = ref(0)
const startIndex = ref(0)
const visibleCount = ref(desktopVisibleCount)
const trackStep = ref(0)
const rollViewport = ref(null)
const rollTrack = ref(null)
const listLoading = ref(true)
const listError = ref('')
const loadingMore = ref(false)
const moreError = ref('')
const viewMode = ref('list')
const detailRecord = ref(null)
const detailHerb = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const herbLoading = ref(false)
const herbError = ref('')
const herbImageError = ref(false)
const uploadImageError = ref(false)
const deleting = ref(false)
const deleteError = ref('')
const isClosing = ref(false)
const tooltipRecordId = ref(null)
const tooltipTime = ref('')
const tooltipElement = ref(null)
const tooltipPosition = ref({ left: '0px', top: '0px' })
const rankedTop3 = computed(() => [...(detailRecord.value?.top3 ?? [])].sort((a, b) => b.probability - a.probability).slice(0, 3))
const detailIsRecognized = computed(() => isRecognitionSuccessful(detailRecord.value?.confidence))
const showArrows = computed(() => total.value > desktopVisibleCount)
const maxStart = computed(() => maxHistoryStart(total.value, visibleCount.value))

let listController
let detailController
let listRequestId = 0
let detailRequestId = 0
let catalogPromise
let savedScrollY = 0
let isUnmounted = false
let navigationPending = false
let resizeObserver
let mobileQuery
let tooltipTarget
let leaveResolve

function hideTooltip() {
  tooltipRecordId.value = null
  tooltipTarget = undefined
}

function updateTooltipPosition() {
  if (!tooltipTarget?.isConnected || !tooltipElement.value) return
  const anchor = tooltipTarget.getBoundingClientRect()
  const tooltip = tooltipElement.value.getBoundingClientRect()
  const left = Math.max(8, Math.min(window.innerWidth - tooltip.width - 8, anchor.left + anchor.width / 2 - tooltip.width / 2))
  const above = anchor.top - tooltip.height - 8
  const top = above >= 8 ? above : Math.min(window.innerHeight - tooltip.height - 8, anchor.bottom + 8)
  tooltipPosition.value = { left: `${left}px`, top: `${Math.max(8, top)}px` }
}

function showTooltip(record, event) {
  if (viewMode.value !== 'list' || isClosing.value) return
  tooltipTarget = event.currentTarget.tagName === 'TIME'
    ? event.currentTarget
    : event.currentTarget.querySelector('time')
  tooltipRecordId.value = record.id
  tooltipTime.value = formatGregorianTimestamp(record.created_at)
  nextTick(updateTooltipPosition)
}

function onRollFocus(record, event) {
  if (event.currentTarget.matches(':focus-visible')) showTooltip(record, event)
}

function hideTooltipOnOutsidePointer(event) {
  if (tooltipRecordId.value === null) return
  if (tooltipTarget?.contains(event.target) || tooltipElement.value?.contains(event.target)) return
  hideTooltip()
}

function isRecordVisible(index) {
  return index >= startIndex.value && index < startIndex.value + (showArrows.value ? visibleCount.value : desktopVisibleCount)
}

function updateTrackStep() {
  const width = rollViewport.value?.getBoundingClientRect().width
  if (!width || !rollTrack.value) return
  const gap = Number.parseFloat(getComputedStyle(rollTrack.value).columnGap) || 0
  const count = showArrows.value ? visibleCount.value : desktopVisibleCount
  trackStep.value = (width + gap) / count
}

function updateVisibleCount() {
  visibleCount.value = mobileQuery?.matches ? 2 : desktopVisibleCount
  startIndex.value = Math.min(startIndex.value, maxStart.value)
  nextTick(updateTrackStep)
}

watch(rollViewport, (element) => {
  if (element) {
    resizeObserver?.observe(element)
    nextTick(updateTrackStep)
  }
})

watch(showArrows, () => nextTick(updateTrackStep))

function safeProbability(value) {
  const number = Number(value)
  return Number.isFinite(number) ? Math.min(1, Math.max(0, number)) : 0
}

function formatPercent(value) {
  return `${(safeProbability(value) * 100).toFixed(2)}%`
}

function recognitionLabel(record) {
  return isRecognitionSuccessful(record.confidence) ? record.predicted_class : '识别失败'
}

function recordAriaLabel(record) {
  const result = isRecognitionSuccessful(record.confidence)
    ? `${record.predicted_class}识别`
    : '识别失败'
  return `查看${result}记录，${formatLunarTimestamp(record.created_at)}`
}

async function loadInitialPage() {
  listController?.abort()
  const requestId = ++listRequestId
  listController = new AbortController()
  listLoading.value = true
  listError.value = ''
  loadingMore.value = false
  moreError.value = ''
  records.value = []
  loadedPage.value = 0
  startIndex.value = 0
  try {
    const response = await getHistory(1, pageSize, { signal: listController.signal })
    const data = response.data?.data
    if (!Array.isArray(data?.items) || !Number.isInteger(data.total) || data.page !== 1) throw new Error('Invalid history page')
    if (isUnmounted || requestId !== listRequestId) return
    records.value = data.items
    total.value = data.total
    loadedPage.value = 1
  } catch {
    if (!isUnmounted && requestId === listRequestId) listError.value = '识别历史暂时无法加载，请稍后重试。'
  } finally {
    if (!isUnmounted && requestId === listRequestId) listLoading.value = false
  }
}

async function loadNextPage() {
  if (loadingMore.value || records.value.length >= total.value) return false
  listController?.abort()
  const requestId = ++listRequestId
  listController = new AbortController()
  loadingMore.value = true
  moreError.value = ''
  try {
    const nextPage = loadedPage.value + 1
    const response = await getHistory(nextPage, pageSize, { signal: listController.signal })
    const data = response.data?.data
    if (!Array.isArray(data?.items) || !Number.isInteger(data.total) || data.page !== nextPage) throw new Error('Invalid history page')
    if (isUnmounted || requestId !== listRequestId) return false
    const existingIds = new Set(records.value.map((record) => record.id))
    const additions = data.items.filter((record) => !existingIds.has(record.id))
    if (!additions.length) throw new Error('No new history records')
    records.value = [...records.value, ...additions]
    total.value = data.total
    loadedPage.value = nextPage
    return true
  } catch {
    if (!isUnmounted && requestId === listRequestId) moreError.value = '后续记录暂时无法加载，请重试。'
    return false
  } finally {
    if (!isUnmounted && requestId === listRequestId) loadingMore.value = false
  }
}

async function shiftWindow(direction) {
  if (navigationPending || listLoading.value) return
  hideTooltip()
  const target = moveHistoryStart(startIndex.value, direction, total.value, visibleCount.value)
  if (target === startIndex.value) return
  navigationPending = true
  try {
    if (target + visibleCount.value > records.value.length && !await loadNextPage()) return
    startIndex.value = Math.min(target, maxStart.value)
  } finally {
    navigationPending = false
  }
}

function loadCatalog() {
  if (!catalogPromise) {
    catalogPromise = getHerbs().then((response) => {
      const herbs = response.data?.data
      if (!Array.isArray(herbs)) throw new Error('Invalid herbal atlas')
      return new Map(herbs.map((herb) => [herb.name, herb.id]))
    }).catch((error) => {
      catalogPromise = undefined
      throw error
    })
  }
  return catalogPromise
}

async function openRecord(recordId) {
  if (viewMode.value !== 'list' || isClosing.value) return
  hideTooltip()
  savedScrollY = window.scrollY
  viewMode.value = 'detail'
  detailController?.abort()
  detailController = new AbortController()
  const requestId = ++detailRequestId
  detailRecord.value = null
  detailHerb.value = null
  detailLoading.value = true
  detailError.value = ''
  herbLoading.value = false
  herbError.value = ''
  herbImageError.value = false
  uploadImageError.value = false
  deleteError.value = ''

  try {
    const response = await getHistoryRecord(recordId, { signal: detailController.signal })
    const record = response.data?.data
    if (record?.id !== recordId || !Array.isArray(record.top3) || record.top3.length < 3) {
      throw new Error('Invalid history record')
    }
    if (isUnmounted || requestId !== detailRequestId) return
    detailRecord.value = record
    detailLoading.value = false
    if (!isRecognitionSuccessful(record.confidence)) return
    herbLoading.value = true

    try {
      const catalog = await loadCatalog()
      if (isUnmounted || requestId !== detailRequestId) return
      const herbId = catalog.get(record.predicted_class)
      if (!herbId) throw new Error('Herb category missing')
      const herbResponse = await getHerb(herbId, { signal: detailController.signal })
      const herb = herbResponse.data?.data
      if (herb?.id !== herbId || herb.name !== record.predicted_class || !herb.recognition_intro || !herb.image_url) {
        throw new Error('Herb detail does not match history')
      }
      if (!isUnmounted && requestId === detailRequestId) detailHerb.value = herb
    } catch {
      if (!isUnmounted && requestId === detailRequestId) herbError.value = '药材简介暂时无法加载。'
    } finally {
      if (!isUnmounted && requestId === detailRequestId) herbLoading.value = false
    }
  } catch {
    if (!isUnmounted && requestId === detailRequestId) detailError.value = '识别记录暂时无法加载，请返回后重试。'
  } finally {
    if (!isUnmounted && requestId === detailRequestId) detailLoading.value = false
  }
}

async function returnToList() {
  if (deleting.value || viewMode.value !== 'detail' || isClosing.value) return
  ++detailRequestId
  detailController?.abort()
  detailController = undefined
  isClosing.value = true
  viewMode.value = 'list'
  await new Promise((resolve) => { leaveResolve = resolve })
}

function finishReturnToList() {
  detailRecord.value = null
  detailHerb.value = null
  isClosing.value = false
  window.scrollTo(0, savedScrollY)
  leaveResolve?.()
  leaveResolve = undefined
}

async function removeRecord() {
  if (!detailRecord.value || deleting.value) return
  if (!window.confirm('确定删除这条识别记录吗？')) return
  const recordId = detailRecord.value.id
  deleting.value = true
  deleteError.value = ''
  try {
    const response = await deleteHistoryRecord(recordId)
    if (response.data?.data?.id !== recordId || response.data?.data?.deleted !== true) {
      throw new Error('Delete was not confirmed by backend')
    }
    deleting.value = false
    await returnToList()
    await loadInitialPage()
  } catch {
    deleteError.value = '删除失败，记录已保留，请稍后重试。'
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  mobileQuery = window.matchMedia('(max-width: 800px)')
  mobileQuery.addEventListener('change', updateVisibleCount)
  resizeObserver = new ResizeObserver(updateTrackStep)
  window.addEventListener('pointerdown', hideTooltipOnOutsidePointer)
  window.addEventListener('scroll', hideTooltip, true)
  window.addEventListener('resize', hideTooltip)
  updateVisibleCount()
  loadInitialPage()
})
onBeforeUnmount(() => {
  isUnmounted = true
  window.removeEventListener('pointerdown', hideTooltipOnOutsidePointer)
  window.removeEventListener('scroll', hideTooltip, true)
  window.removeEventListener('resize', hideTooltip)
  leaveResolve?.()
  mobileQuery?.removeEventListener('change', updateVisibleCount)
  resizeObserver?.disconnect()
  ++listRequestId
  ++detailRequestId
  listController?.abort()
  detailController?.abort()
})
</script>
