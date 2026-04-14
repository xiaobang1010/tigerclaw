<script setup>
import { ref, nextTick, watch } from 'vue'

const props = defineProps({
  messages: {
    type: Array,
    required: true,
    default: () => []
  },
  sessionId: {
    type: String,
    default: ''
  },
  isLoading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['send-message'])

const inputMessage = ref('')
const messagesContainer = ref(null)

const sendMessage = () => {
  if (!inputMessage.value.trim() || props.isLoading) return
  emit('send-message', inputMessage.value.trim())
  inputMessage.value = ''
}

const handleKeyDown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

watch(
  () => props.messages.length,
  () => {
    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    })
  }
)
</script>

<template>
  <div class="chat-window">
    <div v-if="messages.length === 0" class="welcome-section">
      <div class="welcome-icon">🐾</div>
      <h1 class="welcome-title">Hi，我是 TigerClaw</h1>
      <p class="welcome-subtitle">随时随地，帮您高效干活</p>
      <div class="welcome-tips">
        <div class="tip-item">💡 你可以问我任何问题</div>
        <div class="tip-item">📝 帮你撰写、翻译、总结文本</div>
        <div class="tip-item">🧠 协助你进行推理和分析</div>
      </div>
    </div>

    <div v-else ref="messagesContainer" class="chat-messages">
      <div
        v-for="(message, index) in messages"
        :key="index"
        class="message"
        :class="[`message--${message.role}`]"
      >
        <div
          v-if="message.role === 'system'"
          class="message-bubble message-bubble--system"
        >
          {{ message.content }}
        </div>

        <div
          v-else-if="message.role === 'user'"
          class="message-bubble message-bubble--user"
        >
          {{ message.content }}
        </div>

        <div
          v-else-if="message.role === 'assistant'"
          class="message-bubble message-bubble--assistant"
        >
          <div v-if="message.reasoning" class="reasoning-block">
            <div class="reasoning-label">💭 思考过程</div>
            <div class="reasoning-content">{{ message.reasoning }}</div>
          </div>
          <div v-if="message.content" class="answer-content">
            {{ message.content }}
          </div>
          <div
            v-if="!message.content && !message.reasoning && isLoading && index === messages.length - 1"
            class="typing-indicator"
          >
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </div>

      <div v-if="isLoading && messages.length > 0 && messages[messages.length - 1]?.role !== 'assistant'" class="message message--assistant">
        <div class="message-bubble message-bubble--assistant">
          <div class="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </div>
    </div>

    <div class="input-area">
      <div class="input-wrapper">
        <textarea
          v-model="inputMessage"
          class="input-field"
          placeholder="可以描述任务或提问任何问题…"
          rows="1"
          :disabled="isLoading"
          @keydown="handleKeyDown"
          @input="autoResize"
        ></textarea>
        <button
          class="send-btn"
          :class="{ 'send-btn--disabled': !inputMessage.trim() || isLoading }"
          :disabled="!inputMessage.trim() || isLoading"
          @click="sendMessage"
        >
          <span v-if="isLoading" class="loading-spinner"></span>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
        </button>
      </div>
      <div class="input-hint">Enter 发送 · Shift+Enter 换行</div>
    </div>
  </div>
</template>

<script>
export default {
  methods: {
    autoResize(event) {
      const el = event.target
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 160) + 'px'
    }
  }
}
</script>

<style scoped>
.chat-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.welcome-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.welcome-icon {
  font-size: 64px;
  margin-bottom: 24px;
}

.welcome-title {
  font-size: 32px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 12px 0;
}

.welcome-subtitle {
  font-size: 16px;
  color: #6b7280;
  margin: 0 0 40px 0;
  line-height: 1.5;
}

.welcome-tips {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 360px;
  width: 100%;
}

.tip-item {
  padding: 14px 20px;
  background-color: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  font-size: 14px;
  color: #374151;
  text-align: left;
  transition: background-color 0.2s;
}

.tip-item:hover {
  background-color: #f3f4f6;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message {
  display: flex;
}

.message--user {
  justify-content: flex-end;
}

.message--assistant {
  justify-content: flex-start;
}

.message--system {
  justify-content: center;
}

.message-bubble {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 16px;
  line-height: 1.6;
  word-wrap: break-word;
  overflow-wrap: break-word;
  white-space: pre-wrap;
  font-size: 14px;
}

.message-bubble--user {
  background-color: #4f46e5;
  color: #ffffff;
  border-top-right-radius: 4px;
}

.message-bubble--assistant {
  background-color: #f3f4f6;
  color: #1f2937;
  border-top-left-radius: 4px;
}

.message-bubble--system {
  background-color: transparent;
  color: #9ca3af;
  font-size: 12px;
  padding: 4px 12px;
  max-width: 90%;
  text-align: center;
}

.reasoning-block {
  background-color: #fefce8;
  border: 1px solid #fde68a;
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 10px;
}

.reasoning-label {
  font-size: 12px;
  font-weight: 600;
  color: #92400e;
  margin-bottom: 6px;
}

.reasoning-content {
  font-size: 13px;
  color: #78716c;
  font-style: italic;
  line-height: 1.5;
  white-space: pre-wrap;
}

.answer-content {
  font-size: 14px;
  color: #1f2937;
  line-height: 1.6;
  white-space: pre-wrap;
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #9ca3af;
  animation: typingBounce 1.4s ease-in-out infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typingBounce {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-6px);
    opacity: 1;
  }
}

.input-area {
  padding: 16px 24px 20px;
  border-top: 1px solid #e5e7eb;
  background-color: #ffffff;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  background-color: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 8px 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-wrapper:focus-within {
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
  background-color: #ffffff;
}

.input-field {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 14px;
  line-height: 1.5;
  color: #1f2937;
  resize: none;
  min-height: 24px;
  max-height: 160px;
  padding: 6px 4px;
  font-family: inherit;
}

.input-field::placeholder {
  color: #9ca3af;
}

.input-field:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.send-btn {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: none;
  background-color: #4f46e5;
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 0.2s, transform 0.15s;
}

.send-btn:hover:not(.send-btn--disabled) {
  background-color: #4338ca;
  transform: scale(1.05);
}

.send-btn--disabled {
  background-color: #c7d2fe;
  color: #e0e7ff;
  cursor: not-allowed;
}

.loading-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.input-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #9ca3af;
  text-align: center;
}

@media (max-width: 768px) {
  .message-bubble {
    max-width: 85%;
  }

  .welcome-title {
    font-size: 24px;
  }

  .input-area {
    padding: 12px 16px 16px;
  }

  .chat-messages {
    padding: 16px;
  }
}
</style>
