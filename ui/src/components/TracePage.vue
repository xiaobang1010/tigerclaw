<script setup>
import { ref, onMounted, watch } from 'vue'
import { fetchTraces, fetchTraceDetail, fetchTraceStats } from '../services/api'

const props = defineProps({
  currentSessionId: {
    type: String,
    default: ''
  }
})

const stats = ref({
  total_traces: 0,
  total_errors: 0,
  error_rate: 0,
  total_input_tokens: 0,
  total_output_tokens: 0,
  avg_duration_ms: 0,
  tool_call_distribution: {}
})
const traces = ref([])
const selectedTrace = ref(null)
const loading = ref(false)
const error = ref('')

const loadStats = async () => {
  try {
    const params = {}
    if (props.currentSessionId) {
      params.session_id = props.currentSessionId
    }
    stats.value = await fetchTraceStats(params)
  } catch (e) {
    console.error('Failed to load stats:', e)
  }
}

const loadTraces = async () => {
  loading.value = true
  error.value = ''
  try {
    const params = { limit: 50 }
    if (props.currentSessionId) {
      params.session_id = props.currentSessionId
    }
    const data = await fetchTraces(params)
    traces.value = data.traces || []
  } catch (e) {
    error.value = '加载轨迹失败，请确认 Gateway 是否运行'
    console.error('Failed to load traces:', e)
  } finally {
    loading.value = false
  }
}

const selectTrace = async (trace) => {
  if (selectedTrace.value && selectedTrace.value.trace_id === trace.trace_id) {
    selectedTrace.value = null
    return
  }
  try {
    selectedTrace.value = await fetchTraceDetail(trace.trace_id)
  } catch (e) {
    selectedTrace.value = trace
    console.error('Failed to load trace detail:', e)
  }
}

const formatTime = (ts) => {
  if (!ts) return '-'
  try {
    return new Date(ts).toLocaleString('zh-CN')
  } catch {
    return ts
  }
}

const formatDuration = (ms) => {
  if (!ms) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

const formatTokens = (n) => {
  if (!n) return '0'
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

onMounted(() => {
  loadStats()
  loadTraces()
})

watch(() => props.currentSessionId, () => {
  loadStats()
  loadTraces()
})
</script>

<template>
  <div class="trace-page">
    <div class="stats-panel">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total_traces }}</div>
        <div class="stat-label">总调用次数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ formatTokens(stats.total_input_tokens + stats.total_output_tokens) }}</div>
        <div class="stat-label">总 Token 用量</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ formatDuration(stats.avg_duration_ms) }}</div>
        <div class="stat-label">平均耗时</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ (stats.error_rate * 100).toFixed(1) }}%</div>
        <div class="stat-label">错误率</div>
      </div>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-else-if="traces.length === 0" class="empty">
      <template v-if="!currentSessionId">请先选择一个会话以查看其轨迹记录。</template>
      <template v-else>暂无轨迹数据。在此会话中发送消息后，LLM 调用记录将显示在这里。</template>
    </div>

    <div v-else class="trace-list">
      <div
        v-for="trace in traces"
        :key="trace.trace_id"
        class="trace-item"
        :class="{ expanded: selectedTrace && selectedTrace.trace_id === trace.trace_id }"
        @click="selectTrace(trace)"
      >
        <div class="trace-header">
          <div class="trace-main">
            <span class="trace-status" :class="trace.status">{{ trace.status === 'success' ? '✓' : '✗' }}</span>
            <span class="trace-model">{{ trace.model || '-' }}</span>
            <span class="trace-provider">{{ trace.provider }}</span>
          </div>
          <div class="trace-meta">
            <span class="trace-time">{{ formatTime(trace.timestamp) }}</span>
            <span class="trace-duration">{{ formatDuration(trace.duration_ms) }}</span>
            <span class="trace-tokens">{{ formatTokens(trace.input_tokens + trace.output_tokens) }} tokens</span>
            <span v-if="trace.tool_calls && trace.tool_calls.length" class="trace-tools">🔧 {{ trace.tool_calls.length }}</span>
          </div>
        </div>

        <div v-if="selectedTrace && selectedTrace.trace_id === trace.trace_id" class="trace-detail">
          <div class="detail-section">
            <h4>请求预览</h4>
            <pre class="detail-content">{{ selectedTrace.request_preview || '(无)' }}</pre>
          </div>
          <div class="detail-section">
            <h4>响应预览</h4>
            <pre class="detail-content">{{ selectedTrace.response_preview || '(无)' }}</pre>
          </div>
          <div class="detail-section">
            <h4>Token 使用</h4>
            <div class="token-bars">
              <div class="token-bar">
                <span class="token-label">输入</span>
                <div class="bar"><div class="bar-fill input" :style="{ width: Math.min(selectedTrace.input_tokens / Math.max(selectedTrace.input_tokens + selectedTrace.output_tokens, 1) * 100, 100) + '%' }"></div></div>
                <span class="token-value">{{ selectedTrace.input_tokens }}</span>
              </div>
              <div class="token-bar">
                <span class="token-label">输出</span>
                <div class="bar"><div class="bar-fill output" :style="{ width: Math.min(selectedTrace.output_tokens / Math.max(selectedTrace.input_tokens + selectedTrace.output_tokens, 1) * 100, 100) + '%' }"></div></div>
                <span class="token-value">{{ selectedTrace.output_tokens }}</span>
              </div>
            </div>
          </div>
          <div v-if="selectedTrace.error" class="detail-section">
            <h4>错误信息</h4>
            <pre class="detail-content error-text">{{ selectedTrace.error }}</pre>
          </div>
          <div v-if="selectedTrace.tool_calls && selectedTrace.tool_calls.length" class="detail-section">
            <h4>工具调用 ({{ selectedTrace.tool_calls.length }})</h4>
            <div v-for="(tc, idx) in selectedTrace.tool_calls" :key="idx" class="tool-call-item">
              <div class="tool-call-header">
                <span class="tool-name">{{ tc.name }}</span>
                <span class="tool-duration">{{ formatDuration(tc.duration_ms) }}</span>
                <span class="tool-status" :class="tc.is_error ? 'error' : 'success'">{{ tc.is_error ? '失败' : '成功' }}</span>
              </div>
              <details v-if="tc.arguments && Object.keys(tc.arguments).length">
                <summary>参数</summary>
                <pre class="tool-args">{{ JSON.stringify(tc.arguments, null, 2) }}</pre>
              </details>
              <details v-if="tc.result">
                <summary>结果</summary>
                <pre class="tool-args">{{ tc.result }}</pre>
              </details>
            </div>
          </div>
        </div>
      </div>
    </div>

    <button class="refresh-btn" @click="loadTraces(); loadStats()">刷新</button>
  </div>
</template>

<style scoped>
.trace-page {
  padding: 24px;
  max-width: 1000px;
  margin: 0 auto;
  width: 100%;
}

.stats-panel {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid #e0e0e0;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1976d2;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 13px;
  color: #666;
}

.error-banner {
  padding: 12px 16px;
  background: #fff3e0;
  border: 1px solid #ff9800;
  border-radius: 8px;
  color: #e65100;
  margin-bottom: 16px;
}

.loading, .empty {
  text-align: center;
  padding: 48px;
  color: #999;
  font-size: 15px;
}

.trace-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trace-item {
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e0e0e0;
  cursor: pointer;
  transition: all 0.2s ease;
  overflow: hidden;
}

.trace-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border-color: #bbb;
}

.trace-item.expanded {
  border-color: #1976d2;
  box-shadow: 0 2px 12px rgba(25, 118, 210, 0.15);
}

.trace-header {
  padding: 14px 18px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.trace-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.trace-status {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}

.trace-status.success {
  background: #4caf50;
}

.trace-status.error {
  background: #f44336;
}

.trace-model {
  font-weight: 600;
  font-size: 14px;
  color: #333;
}

.trace-provider {
  font-size: 12px;
  color: #888;
  background: #f0f0f0;
  padding: 2px 8px;
  border-radius: 10px;
}

.trace-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 13px;
  color: #666;
}

.trace-tools {
  background: #e3f2fd;
  color: #1565c0;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}

.trace-detail {
  padding: 0 18px 18px;
  border-top: 1px solid #f0f0f0;
}

.detail-section {
  margin-top: 14px;
}

.detail-section h4 {
  font-size: 13px;
  color: #888;
  margin: 0 0 6px 0;
  font-weight: 500;
}

.detail-content {
  background: #f8f9fa;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  max-height: 200px;
  overflow-y: auto;
}

.error-text {
  color: #c62828;
  background: #ffebee;
}

.token-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.token-bar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.token-label {
  width: 36px;
  font-size: 13px;
  color: #666;
}

.bar {
  flex: 1;
  height: 8px;
  background: #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.bar-fill.input {
  background: #1976d2;
}

.bar-fill.output {
  background: #4caf50;
}

.token-value {
  width: 60px;
  text-align: right;
  font-size: 13px;
  color: #333;
  font-weight: 500;
}

.tool-call-item {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 8px;
  border: 1px solid #eee;
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.tool-name {
  font-weight: 600;
  font-size: 14px;
  color: #333;
}

.tool-duration {
  font-size: 12px;
  color: #888;
}

.tool-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}

.tool-status.success {
  background: #e8f5e9;
  color: #2e7d32;
}

.tool-status.error {
  background: #ffebee;
  color: #c62828;
}

.tool-args {
  background: #fff;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 6px 0 0;
  border: 1px solid #eee;
  max-height: 150px;
  overflow-y: auto;
}

details summary {
  cursor: pointer;
  font-size: 12px;
  color: #666;
  padding: 2px 0;
}

.refresh-btn {
  display: block;
  margin: 24px auto 0;
  padding: 10px 32px;
  background: #1976d2;
  color: #fff;
  border: none;
  border-radius: 20px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.refresh-btn:hover {
  background: #1565c0;
  transform: translateY(-1px);
}

@media (max-width: 768px) {
  .stats-panel {
    grid-template-columns: repeat(2, 1fr);
  }

  .trace-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .trace-meta {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>
