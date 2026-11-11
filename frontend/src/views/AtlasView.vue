<template>
  <main class="atlas-page" aria-label="中药材图鉴">
    <Transition name="atlas-mode" mode="out-in">
      <div v-if="viewMode === 'browse'" key="browse" class="atlas-scene">
        <p v-if="isLoading" class="atlas-feedback" role="status">正在加载药材图鉴…</p>
        <p v-else-if="loadError" class="atlas-feedback atlas-feedback--error" role="alert">
          {{ loadError }}
        </p>

        <template v-else-if="selectedHerb">
          <img
            class="atlas-book"
            src="/assets/books/atlas_open_book.png"
            alt=""
            aria-hidden="true"
          />

          <div class="atlas-stage" :aria-label="`当前药材：${selectedHerb.name}`" aria-live="polite">
            <img
              v-for="item in positionedHerbs"
              v-show="!failedImages.has(item.herb.id)"
              :key="item.herb.id"
              class="atlas-item"
              :class="`atlas-item--${item.slot}`"
              :src="item.herb.image_url"
              :data-herb-id="item.herb.id"
              :alt="item.slot === 'center' ? item.herb.name : ''"
              :aria-hidden="item.slot !== 'center'"
              :role="item.slot === 'center' ? 'button' : undefined"
              :tabindex="item.slot === 'center' && !failedImages.has(item.herb.id) ? 0 : -1"
              :aria-label="item.slot === 'center' ? `查看${item.herb.name}详情` : undefined"
              @click="openDetail(item)"
              @keydown.enter.prevent="openDetail(item)"
              @keydown.space.prevent="openDetail(item)"
              @error="markImageFailed(item.herb.id)"
            />
            <p v-if="failedImages.has(selectedHerb.id)" class="atlas-image-error" role="alert">
              药材插画加载失败
            </p>
          </div>

          <button class="atlas-arrow atlas-arrow--previous" type="button" aria-label="上一种药材" :aria-disabled="isAnimating" @click="shift(-1)">
            <span aria-hidden="true"></span>
          </button>
          <button class="atlas-arrow atlas-arrow--next" type="button" aria-label="下一种药材" :aria-disabled="isAnimating" @click="shift(1)">
            <span aria-hidden="true"></span>
          </button>
        </template>
      </div>
      <section v-else key="detail" class="atlas-detail" :aria-label="`${selectedHerb?.name ?? ''}药材详情`">
        <button class="atlas-detail-back" type="button" @click="returnToBrowse">返回</button>
        <p v-if="detailBookFailed" class="atlas-detail-book-error" role="alert">古书图片加载失败</p>
        <div class="atlas-detail-book" :class="{ 'atlas-detail-book--missing': detailBookFailed }">
          <img v-show="!detailBookFailed" class="atlas-detail-book-image" src="/assets/books/book_detail_open.png" alt="" aria-hidden="true" @error="detailBookFailed = true" />
          <div class="atlas-detail-page atlas-detail-page--left">
            <h1 class="atlas-detail-name">{{ selectedHerb?.name }}</h1>
            <img
              v-if="selectedHerb && !failedImages.has(selectedHerb.id)"
              class="atlas-detail-herb-image"
              :src="detailHerb?.image_url ?? selectedHerb.image_url"
              :alt="selectedHerb.name"
              @error="markImageFailed(selectedHerb.id)"
            />
            <p v-else class="atlas-detail-feedback" role="alert">药材插画加载失败</p>
          </div>
          <div class="atlas-detail-page atlas-detail-page--right">
            <p v-if="detailLoading" class="atlas-detail-feedback" role="status">正在加载药材资料…</p>
            <p v-else-if="detailError" class="atlas-detail-feedback atlas-detail-feedback--error" role="alert">{{ detailError }}</p>
            <div v-else-if="detailHerb" class="atlas-detail-fields">
              <section>
                <h2>外貌描述</h2>
                <p>{{ detailHerb.appearance }}</p>
              </section>
              <section>
                <h2>传统功效</h2>
                <p>{{ detailHerb.traditional_effects }}</p>
              </section>
              <section>
                <h2>本草典故</h2>
                <p>{{ detailHerb.allusion }}</p>
              </section>
            </div>
          </div>
        </div>
      </section>
    </Transition>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getHerb, getHerbs } from '../api/index.js'
import '../styles/atlas.css'

const viewMode = ref('browse')
const herbs = ref([])
const selectedIndex = ref(0)
const isLoading = ref(true)
const loadError = ref('')
const failedImages = ref(new Set())
const isAnimating = ref(false)
const detailHerb = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const detailBookFailed = ref(false)
const transitionDuration = 650
let animationTimer
let detailController
let detailRequestId = 0
let isUnmounted = false

const selectedHerb = computed(() => herbs.value[selectedIndex.value] ?? null)
const positionedHerbs = computed(() => {
  const count = herbs.value.length
  return herbs.value.map((herb, index) => {
    const offset = (index - selectedIndex.value + count) % count
    let slot = 'hidden-next'
    if (offset === 0) slot = 'center'
    else if (offset === 1) slot = 'next'
    else if (offset === 2) slot = 'far-next'
    else if (offset === count - 1) slot = 'previous'
    else if (offset === count - 2) slot = 'far-previous'
    else if (offset > count / 2) slot = 'hidden-previous'
    return { herb, slot }
  })
})

function shift(direction) {
  if (!herbs.value.length || isAnimating.value) return
  selectedIndex.value = (selectedIndex.value + direction + herbs.value.length) % herbs.value.length
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  isAnimating.value = true
  animationTimer = window.setTimeout(() => {
    isAnimating.value = false
    animationTimer = undefined
  }, transitionDuration)
}

async function openDetail(item) {
  if (viewMode.value !== 'browse' || isAnimating.value || item.slot !== 'center' ||
      item.herb.id !== selectedHerb.value?.id || failedImages.value.has(item.herb.id)) return

  detailController?.abort()
  const requestId = ++detailRequestId
  const herbId = item.herb.id
  detailController = new AbortController()
  detailHerb.value = null
  detailError.value = ''
  detailLoading.value = true
  detailBookFailed.value = false
  viewMode.value = 'detail'
  try {
    const response = await getHerb(herbId, { signal: detailController.signal })
    const record = response.data?.data
    if (record?.id !== herbId || !record.appearance || !record.traditional_effects || !record.allusion) {
      throw new Error('Incomplete herbal detail')
    }
    if (!isUnmounted && requestId === detailRequestId && viewMode.value === 'detail') {
      detailHerb.value = record
    }
  } catch {
    if (!isUnmounted && requestId === detailRequestId && viewMode.value === 'detail') {
      detailError.value = '药材资料暂时无法加载，请返回后重试。'
    }
  } finally {
    if (!isUnmounted && requestId === detailRequestId) detailLoading.value = false
  }
}

function returnToBrowse() {
  ++detailRequestId
  detailController?.abort()
  detailController = undefined
  detailHerb.value = null
  detailError.value = ''
  detailLoading.value = false
  viewMode.value = 'browse'
}

function markImageFailed(id) {
  if (isUnmounted) return
  failedImages.value = new Set([...failedImages.value, id])
}

function preloadHerbs(records) {
  return Promise.all(records.map((herb) => new Promise((resolve) => {
    const image = new Image()
    image.onload = () => resolve()
    image.onerror = () => {
      markImageFailed(herb.id)
      resolve()
    }
    image.src = herb.image_url
  })))
}

onMounted(async () => {
  try {
    const response = await getHerbs()
    const records = response.data?.data
    if (!Array.isArray(records) || records.length === 0) throw new Error('Empty herbal atlas')
    await preloadHerbs(records)
    if (isUnmounted) return
    herbs.value = records
    selectedIndex.value = records.findIndex((herb) => herb.name === '人参')
    if (selectedIndex.value < 0) selectedIndex.value = 0
  } catch {
    if (!isUnmounted) loadError.value = '药材图鉴暂时无法加载，请稍后重试。'
  } finally {
    if (!isUnmounted) isLoading.value = false
  }
})

onBeforeUnmount(() => {
  isUnmounted = true
  ++detailRequestId
  detailController?.abort()
  if (animationTimer) window.clearTimeout(animationTimer)
})
</script>
