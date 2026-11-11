<template>
  <main class="analysis-page">
    <h1 class="analysis-page-title">模型分析</h1>

    <section class="analysis-panel" aria-labelledby="analysis-overview-title">
      <h2 id="analysis-overview-title" class="analysis-section-title">模型概览</h2>
      <p v-if="infoLoading" class="analysis-feedback" role="status">正在加载模型概览…</p>
      <p v-else-if="infoError" class="analysis-feedback analysis-feedback--error" role="alert">{{ infoError }}</p>
      <dl v-else class="analysis-overview-grid">
        <div v-for="item in overviewItems" :key="item.label" class="analysis-overview-item">
          <dt>{{ item.label }}</dt>
          <dd>{{ item.value }}</dd>
        </div>
      </dl>
    </section>

    <section class="analysis-panel" aria-labelledby="analysis-performance-title">
      <h2 id="analysis-performance-title" class="analysis-section-title">模型性能</h2>
      <p v-if="metricsLoading" class="analysis-feedback" role="status">正在加载最终测试集指标…</p>
      <p v-else-if="metricsError" class="analysis-feedback analysis-feedback--error" role="alert">{{ metricsError }}</p>
      <dl v-else class="analysis-metrics-grid">
        <div v-for="item in metricItems" :key="item.english" class="analysis-metric-item">
          <dt>{{ item.chinese }}<small>{{ item.english }}</small></dt>
          <dd>{{ item.value }}</dd>
        </div>
      </dl>
    </section>

    <div class="analysis-charts">
      <section class="analysis-panel analysis-chart-panel" aria-labelledby="analysis-curve-title">
        <h2 id="analysis-curve-title" class="analysis-section-title">训练曲线</h2>
        <p v-if="curveError" class="analysis-feedback analysis-feedback--error" role="alert">Accuracy 曲线暂时无法加载。</p>
        <img v-else class="analysis-chart-image" :src="curveUrl" alt="Run02 训练与验证 Accuracy 曲线，横轴为原始训练轮次" @error="curveError = true" />
      </section>
      <section class="analysis-panel analysis-chart-panel" aria-labelledby="analysis-matrix-title">
        <h2 id="analysis-matrix-title" class="analysis-section-title">混淆矩阵</h2>
        <p v-if="matrixError" class="analysis-feedback analysis-feedback--error" role="alert">归一化混淆矩阵暂时无法加载。</p>
        <div v-else class="analysis-matrix-scroll" role="region" aria-label="横向滚动查看完整混淆矩阵" tabindex="0">
          <img class="analysis-chart-image" :src="matrixUrl" alt="最终独立测试集的18类归一化混淆矩阵，包含原始类别、刻度和色条" @error="matrixError = true" />
        </div>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getModelChartUrl, getModelInfo, getModelMetrics } from '../api/index.js'
import '../styles/analysis.css'

const info = ref(null)
const finalTest = ref(null)
const infoLoading = ref(true)
const metricsLoading = ref(true)
const infoError = ref('')
const metricsError = ref('')
const curveError = ref(false)
const matrixError = ref(false)

const curveUrl = getModelChartUrl('accuracy_curve')
const matrixUrl = getModelChartUrl('confusion_matrix_normalized')

const modelName = computed(() =>
  info.value.model_name === 'convnext_tiny' ? 'ConvNeXt-Tiny' : info.value.model_name,
)
const overviewItems = computed(() => [
  { label: '模型名称', value: modelName.value },
  { label: '中药材类别', value: `${info.value.num_classes}类` },
  { label: '模型参数量', value: `${(info.value.parameter_count / 1_000_000).toFixed(2)}M` },
  { label: '输入图像尺寸', value: `${info.value.input_size} × ${info.value.input_size}` },
])
const metricItems = computed(() => [
  { chinese: '准确率', english: 'Accuracy', value: percent(finalTest.value.accuracy) },
  { chinese: '宏平均精确率', english: 'Macro-Precision', value: percent(finalTest.value.macro_precision) },
  { chinese: '宏平均召回率', english: 'Macro-Recall', value: percent(finalTest.value.macro_recall) },
  { chinese: '宏平均F1', english: 'Macro-F1', value: percent(finalTest.value.macro_f1) },
])

function percent(ratio) {
  return `${(ratio * 100).toFixed(2)}%`
}

function validInfo(data) {
  return data && typeof data.model_name === 'string' && data.model_name.length > 0
    && Number.isInteger(data.num_classes) && data.num_classes > 0
    && Number.isFinite(data.parameter_count) && data.parameter_count > 0
    && Number.isInteger(data.input_size) && data.input_size > 0
}

function validFinalTest(data) {
  return data && ['accuracy', 'macro_precision', 'macro_recall', 'macro_f1']
    .every((key) => typeof data[key] === 'number' && Number.isFinite(data[key]) && data[key] >= 0 && data[key] <= 1)
}

async function loadInfo() {
  try {
    const data = (await getModelInfo()).data?.data
    if (!validInfo(data)) throw new Error('Invalid model info')
    info.value = data
  } catch {
    infoError.value = '模型概览暂时无法加载。'
  } finally {
    infoLoading.value = false
  }
}

async function loadMetrics() {
  try {
    const data = (await getModelMetrics()).data?.data?.final_test
    if (!validFinalTest(data)) throw new Error('Invalid final test metrics')
    finalTest.value = data
  } catch {
    metricsError.value = '最终测试集指标暂时无法加载。'
  } finally {
    metricsLoading.value = false
  }
}

onMounted(() => {
  loadInfo()
  loadMetrics()
})
</script>
