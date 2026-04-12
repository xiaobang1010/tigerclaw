<script setup>
import { ref, onMounted } from 'vue'
import ChatWindow from './components/ChatWindow.vue'
import TracePage from './components/TracePage.vue'
import { sendChatRequest, handleStreamResponse } from './services/api'
import { useSessions } from './composables/useSessions'

const {
  sessions,
  activeSessionId,
  currentSession,
  currentMessages,
  createSession,
  switchSession,
  deleteSession,
  addMessage,
  updateSessionTitle
} = useSessions()

const activeNav = ref('chat')
const showSettings = ref(false)
const isLoading = ref(false)
const errorMessage = ref('')

const envConfig = ref({
  model: import.meta.env.VITE_OPENAI_MODEL || '未配置',
  baseUrl: import.meta.env.VITE_OPENAI_BASE_URL || '未配置',
  apiKey: import.meta.env.VITE_OPENAI_API_KEY ? '已配置' : '未配置'
})

const formatTime = (ts) => {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  if (isToday) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

const handleNewChat = () => {
  createSession()
  activeNav.value = 'chat'
}

const handleSwitchSession = (id) => {
  switchSession(id)
  activeNav.value = 'chat'
}

const handleDeleteSession = (id, event) => {
  event.stopPropagation()
  deleteSession(id)
}

const renamingSessionId = ref(null)
const renameValue = ref('')

const handleContextMenu = (session, event) => {
  event.preventDefault()
  renamingSessionId.value = session.id
  renameValue.value = session.title
}

const finishRename = (sessionId) => {
  if (renameValue.value.trim()) {
    updateSessionTitle(sessionId, renameValue.value.trim())
  }
  renamingSessionId.value = null
}

const handleSendMessage = async (text) => {
  let sessionId = activeSessionId.value
  if (!sessionId) {
    sessionId = createSession()
  }

  addMessage(sessionId, {
    role: 'user',
    content: text,
    timestamp: new Date().toISOString()
  })

  addMessage(sessionId, {
    role: 'assistant',
    content: '',
    reasoning: '',
    timestamp: new Date().toISOString()
  })

  isLoading.value = true
  errorMessage.value = ''

  try {
    const session = sessions.value.find((s) => s.id === sessionId)
    const history = session.messages
      .filter((m) => m.role === 'user' || (m.role === 'assistant' && m.content))
      .map((m) => ({ role: m.role, content: m.content }))

    const response = await sendChatRequest(history, sessionId)

    handleStreamResponse(
      response,
      (chunk, type) => {
        const msg = session.messages[session.messages.length - 1]
        if (msg && msg.role === 'assistant') {
          if (type === 'reasoning') {
            msg.reasoning = (msg.reasoning || '') + chunk
          } else if (type === 'answer') {
            msg.content = (msg.content || '') + chunk
          }
        }
      },
      (error) => {
        const msg = session.messages[session.messages.length - 1]
        if (msg && msg.role === 'assistant') {
          msg.content = '发生错误，请稍后重试'
        }
        console.error('Stream error:', error)
      }
    )
  } catch (error) {
    const session = sessions.value.find((s) => s.id === sessionId)
    if (session) {
      const msg = session.messages[session.messages.length - 1]
      if (msg && msg.role === 'assistant') {
        msg.content = '发送消息失败，请检查配置'
      }
    }
    errorMessage.value = '发送消息失败，请检查配置'
    console.error('Send error:', error)
  } finally {
    isLoading.value = false
  }
}

const dismissError = () => {
  errorMessage.value = ''
}

onMounted(() => {
  if (!import.meta.env.VITE_OPENAI_API_KEY) {
    errorMessage.value = '请在.env.local文件中配置API密钥'
  }
})
</script>

<template>
  <div class="app-container">
    <div class="sidebar">
      <div class="sidebar-header">
        <div class="logo">🐾 TigerClaw</div>
        <button class="new-chat-btn" @click="handleNewChat">+ 新建对话</button>
      </div>

      <div class="session-list">
        <div
          v-for="session in sessions"
          :key="session.id"
          class="session-item"
          :class="{ active: session.id === activeSessionId }"
          @click="handleSwitchSession(session.id)"
          @contextmenu="handleContextMenu(session, $event)"
        >
          <div class="session-info">
            <div v-if="renamingSessionId === session.id" class="session-rename">
              <input
                v-model="renameValue"
                class="rename-input"
                @keyup.enter="finishRename(session.id)"
                @blur="finishRename(session.id)"
                @click.stop
                autofocus
              />
            </div>
            <template v-else>
              <div class="session-title">{{ session.title }}</div>
              <div class="session-time">{{ formatTime(session.updatedAt) }}</div>
            </template>
          </div>
          <button class="session-delete" @click="handleDeleteSession(session.id, $event)">✕</button>
        </div>
        <div v-if="sessions.length === 0" class="session-empty">暂无对话</div>
      </div>

      <div class="sidebar-footer">
        <div class="nav-tabs">
          <div
            class="nav-tab"
            :class="{ active: activeNav === 'chat' }"
            @click="activeNav = 'chat'"
          >
            💬 对话
          </div>
          <div
            class="nav-tab"
            :class="{ active: activeNav === 'trace' }"
            @click="activeNav = 'trace'"
          >
            📊 轨迹
          </div>
        </div>
        <div class="settings-trigger" @click="showSettings = true">
          ⚙️ 设置
        </div>
      </div>
    </div>

    <div class="main-content">
      <div v-if="errorMessage" class="error-banner">
        <span>{{ errorMessage }}</span>
        <button class="error-dismiss" @click="dismissError">✕</button>
      </div>

      <template v-if="activeNav === 'chat'">
        <ChatWindow
          v-if="currentSession"
          :messages="currentMessages"
          :session-id="activeSessionId || ''"
          :is-loading="isLoading"
          @send-message="handleSendMessage"
        />
        <div v-else class="welcome-page">
          <div class="welcome-icon">🐾</div>
          <h2 class="welcome-title">欢迎使用 TigerClaw</h2>
          <p class="welcome-hint">点击左侧「新建对话」开始</p>
        </div>
      </template>

      <TracePage v-else-if="activeNav === 'trace'" :current-session-id="activeSessionId || ''" />
    </div>

    <div v-if="showSettings" class="settings-overlay" @click="showSettings = false">
      <div class="settings-dialog" @click.stop>
        <div class="settings-header">
          <h2>配置</h2>
          <button class="close-btn" @click="showSettings = false">×</button>
        </div>
        <div class="settings-content">
          <h3>当前配置</h3>
          <div class="config-item">
            <span class="config-label">模型：</span>
            <span class="config-value">{{ envConfig.model }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">API地址：</span>
            <span class="config-value">{{ envConfig.baseUrl }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">API密钥：</span>
            <span class="config-value">{{ envConfig.apiKey }}</span>
          </div>
          <div class="config-hint">
            <p>请在 .env.local 文件中配置以下信息：</p>
            <pre>VITE_OPENAI_BASE_URL=https://api-inference.modelscope.cn/v1
VITE_OPENAI_API_KEY=&lt;MODELSCOPE_TOKEN&gt;
VITE_OPENAI_MODEL=ZhipuAI/GLM-5</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 14px;
  color: #1f2937;
}

.sidebar {
  width: 260px;
  background-color: #f9fafb;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 20px 16px 12px;
}

.logo {
  font-size: 20px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 12px;
}

.new-chat-btn {
  width: 100%;
  padding: 10px 0;
  background-color: #4f46e5;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
}

.new-chat-btn:hover {
  background-color: #4338ca;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.15s;
  border-left: 3px solid transparent;
  margin-bottom: 2px;
}

.session-item:hover {
  background-color: #f3f4f6;
}

.session-item.active {
  background-color: #eef2ff;
  border-left-color: #4f46e5;
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-title {
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-time {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}

.session-delete {
  display: none;
  background: none;
  border: none;
  color: #ef4444;
  font-size: 14px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
  transition: background-color 0.15s;
}

.session-delete:hover {
  background-color: #fee2e2;
}

.session-item:hover .session-delete {
  display: block;
}

.session-empty {
  padding: 24px 16px;
  text-align: center;
  color: #9ca3af;
  font-size: 13px;
}

.session-rename {
  width: 100%;
}

.rename-input {
  width: 100%;
  padding: 2px 6px;
  border: 1px solid #4f46e5;
  border-radius: 4px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  background: #ffffff;
}

.sidebar-footer {
  padding: 12px 8px;
  border-top: 1px solid #e5e7eb;
}

.nav-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 4px;
}

.nav-tab {
  flex: 1;
  padding: 8px 0;
  text-align: center;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #6b7280;
  transition: all 0.15s;
}

.nav-tab:hover {
  background-color: #e5e7eb;
}

.nav-tab.active {
  background-color: #eef2ff;
  color: #4f46e5;
  font-weight: 600;
}

.settings-trigger {
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #6b7280;
  transition: all 0.15s;
}

.settings-trigger:hover {
  background-color: #e5e7eb;
  color: #374151;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  background-color: #ffffff;
}

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background-color: #fef2f2;
  border-bottom: 1px solid #fecaca;
  color: #dc2626;
  font-size: 13px;
  flex-shrink: 0;
}

.error-dismiss {
  background: none;
  border: none;
  color: #dc2626;
  cursor: pointer;
  font-size: 14px;
  padding: 0 4px;
}

.welcome-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
}

.welcome-icon {
  font-size: 56px;
  margin-bottom: 20px;
}

.welcome-title {
  font-size: 24px;
  font-weight: 600;
  color: #374151;
  margin: 0 0 8px 0;
}

.welcome-hint {
  font-size: 15px;
  color: #9ca3af;
  margin: 0;
}

.settings-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.settings-dialog {
  background-color: #ffffff;
  border-radius: 12px;
  width: 480px;
  max-width: 90%;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  animation: dialogFadeIn 0.2s ease;
}

@keyframes dialogFadeIn {
  from {
    opacity: 0;
    transform: translateY(-12px) scale(0.97);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.settings-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: none;
  font-size: 22px;
  cursor: pointer;
  color: #6b7280;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s;
}

.close-btn:hover {
  background-color: #f3f4f6;
  color: #1f2937;
}

.settings-content {
  padding: 24px;
}

.settings-content h3 {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  margin: 0 0 16px 0;
}

.config-item {
  display: flex;
  align-items: baseline;
  padding: 8px 0;
  border-bottom: 1px solid #f3f4f6;
}

.config-label {
  font-size: 13px;
  color: #6b7280;
  min-width: 80px;
}

.config-value {
  font-size: 13px;
  color: #1f2937;
  font-weight: 500;
}

.config-hint {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.config-hint p {
  font-size: 13px;
  color: #6b7280;
  margin: 0 0 8px 0;
}

.config-hint pre {
  background-color: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 12px;
  color: #374151;
  line-height: 1.6;
  overflow-x: auto;
  margin: 0;
}
</style>
