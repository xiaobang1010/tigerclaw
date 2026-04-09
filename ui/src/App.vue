<script setup>
import { ref, onMounted } from 'vue'
import { sendChatRequest, handleStreamResponse } from './services/api'

// 状态管理
const showConfig = ref(false)
const showModelConfig = ref(false)
const activeNav = ref('chat')
const inputMessage = ref('')
const messages = ref([])
const isLoading = ref(false)
const errorMessage = ref('')

// 导航菜单
const navItems = [
  { id: 'chat', name: '对话', icon: 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=minimalist%20chat%20icon%2C%20blue%20color%2C%20professional%2C%20flat%20design&image_size=square' },
  { id: 'inspiration', name: '灵感', icon: 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=minimalist%20inspiration%20icon%2C%20yellow%20color%2C%20professional%2C%20flat%20design&image_size=square' },
  { id: 'task', name: '任务', icon: 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=minimalist%20task%20icon%2C%20green%20color%2C%20professional%2C%20flat%20design&image_size=square' },
  { id: 'help', name: '帮助', icon: 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=minimalist%20help%20icon%2C%20purple%20color%2C%20professional%2C%20flat%20design&image_size=square' },
  { id: 'settings', name: '设置', icon: '⚙️' }
]

// 底部选项
const bottomOptions = [
  { id: 'model', name: '默认大模型' },
  { id: 'skill', name: '技能' },
  { id: 'inspiration', name: '找灵感' }
]

// 切换导航
const switchNav = (id) => {
  activeNav.value = id
  if (id === 'settings') {
    showConfig.value = true
  }
}

// 打开大模型配置
const openModelConfig = () => {
  showModelConfig.value = true
}

// 关闭配置
const closeConfig = () => {
  showConfig.value = false
  showModelConfig.value = false
}

// 发送消息
const sendMessage = async () => {
  if (!inputMessage.value.trim()) return
  
  const userMessage = inputMessage.value.trim()
  messages.value.push({
    role: 'user',
    content: userMessage
  })
  
  inputMessage.value = ''
  isLoading.value = true
  errorMessage.value = ''
  
  try {
    const response = await sendChatRequest([
      { role: 'user', content: userMessage }
    ])
    
    const assistantMessageId = Date.now()
    messages.value.push({
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      reasoning: ''
    })
    
    handleStreamResponse(response, (chunk, type) => {
      const assistantMessage = messages.value.find(msg => msg.id === assistantMessageId)
      if (assistantMessage) {
        if (type === 'reasoning') {
          assistantMessage.reasoning += chunk
        } else {
          assistantMessage.content += chunk
        }
      }
    }, (error) => {
      errorMessage.value = '发生错误，请稍后重试'
      console.error('Error handling stream:', error)
    })
  } catch (error) {
    errorMessage.value = '发送消息失败，请检查配置'
    console.error('Error sending message:', error)
  } finally {
    isLoading.value = false
  }
}

// 处理键盘事件
const handleKeyPress = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

// 初始化
onMounted(() => {
  // 检查配置是否存在
  if (!import.meta.env.VITE_OPENAI_API_KEY) {
    errorMessage.value = '请在.env.local文件中配置API密钥'
  }
})
</script>

<template>
  <div class="app-container">
    <!-- 左侧导航栏 -->
    <div class="sidebar">
      <div class="user-avatar">
        <img src="https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=user%20avatar%20icon&image_size=square" alt="用户头像" />
      </div>
      
      <div class="nav-items">
        <div 
          v-for="item in navItems" 
          :key="item.id"
          class="nav-item"
          :class="{ active: activeNav === item.id }"
          @click="switchNav(item.id)"
        >
          <span v-if="item.id === 'settings'" class="nav-icon">{{ item.icon }}</span>
          <img v-else :src="item.icon" :alt="item.name" class="nav-icon-image" />
          <span class="nav-name">{{ item.name }}</span>
        </div>
      </div>
      
      <!-- 底部设置按钮 -->
      <div class="sidebar-bottom">
        <div class="settings-btn" @click="showConfig = true">
          ⚙️
        </div>
      </div>
    </div>
    
    <!-- 主内容区域 -->
    <div class="main-content">
      <!-- 顶部栏 -->
      <div class="top-bar">
        <div class="search-box">
          <input type="text" placeholder="搜索" />
        </div>
        <div class="top-buttons">
          <button class="new-agent-btn">+ 新建 Agent</button>
          <div class="usage-info">
            <span>今日未使用，剩余100%</span>
            <span class="clock-icon">🕒</span>
          </div>
        </div>
      </div>
      
      <!-- 内容区域 -->
      <div class="content-area">
        <div v-if="messages.length === 0" class="welcome-section">
          <div class="agent-item">
            <div class="agent-icon">
              <img src="https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=fierce%20and%20elegant%20tiger%20claw%20logo%2C%20red%20and%20black%20color%20scheme%2C%20minimalist%20design%2C%20professional%2C%20suitable%20for%20AI%20assistant%20app&image_size=square" alt="TigerClaw" />
            </div>
            <div class="agent-info">
              <h3>TigerClaw</h3>
              <p>随时随地，帮您高效干活</p>
            </div>
          </div>
          
          <div class="welcome-message">
            <h1>Hi，我是TigerClaw</h1>
            <p>随时随地，帮您高效干活</p>
          </div>
        </div>
        
        <div v-else class="chat-messages">
          <div 
            v-for="(message, index) in messages" 
            :key="index"
            class="message"
            :class="message.role"
          >
            <div class="message-content">
              <div v-if="message.role === 'user'" class="user-message">
                {{ message.content }}
              </div>
              <div v-else class="assistant-message">
                <div v-if="message.reasoning" class="reasoning">
                  {{ message.reasoning }}
                </div>
                <div v-if="message.content" class="answer">
                  {{ message.content }}
                </div>
              </div>
            </div>
          </div>
          
          <div v-if="isLoading" class="loading-indicator">
            <div class="loading-spinner"></div>
            <span>正在思考...</span>
          </div>
          
          <div v-if="errorMessage" class="error-message">
            {{ errorMessage }}
          </div>
        </div>
      </div>
      
      <!-- 底部输入框 -->
      <div class="input-area">
        <div class="input-box">
          <input 
            type="text" 
            v-model="inputMessage"
            placeholder="可以描述任务或提问任何问题"
            @keypress="handleKeyPress"
          />
        </div>
        <div class="input-options">
          <div class="option-item" @click="openModelConfig">
            <span>默认大模型</span>
            <span>▼</span>
          </div>
          <div class="option-item">
            <span>技能</span>
            <span>▼</span>
          </div>
          <div class="option-item">
            <span>找灵感</span>
            <span>▼</span>
          </div>
          <div class="option-item">
            <span>📎</span>
          </div>
        </div>
        <div class="send-btn" @click="sendMessage" :disabled="isLoading">
          <span>▶</span>
        </div>
      </div>
    </div>
    
    <!-- 配置界面 -->
    <div v-if="showConfig" class="config-overlay" @click="closeConfig">
      <div class="config-dialog" @click.stop>
        <div class="config-header">
          <h2>配置</h2>
          <button class="close-btn" @click="closeConfig">×</button>
        </div>
        <div class="config-content">
          <h3>API配置</h3>
          <p>请在.env.local文件中配置以下信息：</p>
          <pre>VITE_OPENAI_BASE_URL=https://api-inference.modelscope.cn/v1<br>VITE_OPENAI_API_KEY=&lt;MODELSCOPE_TOKEN&gt;<br>VITE_OPENAI_MODEL=ZhipuAI/GLM-5</pre>
        </div>
      </div>
    </div>
    
    <!-- 大模型配置界面 -->
    <div v-if="showModelConfig" class="config-overlay" @click="closeConfig">
      <div class="config-dialog" @click.stop>
        <div class="config-header">
          <h2>大模型配置</h2>
          <button class="close-btn" @click="closeConfig">×</button>
        </div>
        <div class="config-content">
          <h3>当前配置</h3>
          <p>模型：{{ import.meta.env.VITE_OPENAI_MODEL || '未配置' }}</p>
          <p>API地址：{{ import.meta.env.VITE_OPENAI_BASE_URL || '未配置' }}</p>
          <p>API密钥：{{ import.meta.env.VITE_OPENAI_API_KEY ? '已配置' : '未配置' }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 全局样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.app-container {
  display: flex;
  height: 100vh;
  background-color: #f5f5f5;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

/* 左侧导航栏 */
.sidebar {
  width: 240px;
  background-color: #fff;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  padding: 24px 0;
  box-shadow: 0 0 10px rgba(0,0,0,0.05);
}

.user-avatar {
  padding: 0 24px 24px;
  display: flex;
  justify-content: center;
}

.user-avatar img {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  object-fit: cover;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.nav-items {
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 12px 24px;
  cursor: pointer;
  transition: all 0.2s ease;
  border-left: 3px solid transparent;
}

.nav-item:hover {
  background-color: #f8f9fa;
  padding-left: 28px;
}

.nav-item.active {
  background-color: #e3f2fd;
  color: #1976d2;
  border-left-color: #1976d2;
  padding-left: 28px;
}

.nav-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 16px;
  font-size: 18px;
}

.nav-icon-image {
  width: 24px;
  height: 24px;
  object-fit: contain;
  margin-right: 16px;
}

.nav-name {
  font-size: 14px;
  font-weight: 500;
}

.sidebar-bottom {
  padding: 24px;
  display: flex;
  justify-content: center;
}

.settings-btn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background-color: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid #e0e0e0;
}

.settings-btn:hover {
  background-color: #e0e0e0;
  transform: scale(1.05);
}

/* 主内容区域 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 顶部栏 */
.top-bar {
  padding: 20px 24px;
  background-color: #fff;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.search-box {
  flex: 1;
  max-width: 450px;
  position: relative;
}

.search-box input {
  width: 100%;
  padding: 12px 16px 12px 40px;
  border: 1px solid #e0e0e0;
  border-radius: 25px;
  font-size: 14px;
  transition: all 0.2s ease;
  background-color: #f8f9fa;
}

.search-box input:focus {
  outline: none;
  border-color: #1976d2;
  background-color: #fff;
  box-shadow: 0 0 0 2px rgba(25, 118, 210, 0.2);
}

.search-box::before {
  content: "🔍";
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 14px;
  color: #999;
}

.top-buttons {
  display: flex;
  align-items: center;
  gap: 24px;
}

.new-agent-btn {
  padding: 10px 20px;
  background-color: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 25px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.new-agent-btn:hover {
  background-color: #f8f9fa;
  border-color: #1976d2;
  box-shadow: 0 2px 6px rgba(0,0,0,0.1);
}

.usage-info {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  color: #666;
  background-color: #f8f9fa;
  padding: 8px 16px;
  border-radius: 20px;
  border: 1px solid #e0e0e0;
}

.clock-icon {
  font-size: 16px;
}

/* 内容区域 */
.content-area {
  flex: 1;
  padding: 48px;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #fafafa;
}

.welcome-section {
  text-align: center;
  max-width: 600px;
  width: 100%;
  background-color: #fff;
  padding: 48px;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.agent-item {
  display: flex;
  align-items: center;
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.05);
  margin-bottom: 48px;
  width: 320px;
  margin-left: auto;
  margin-right: auto;
  transition: all 0.2s ease;
}

.agent-item:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  transform: translateY(-2px);
}

.agent-icon {
  margin-right: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.agent-icon img {
  width: 64px;
  height: 64px;
  border-radius: 12px;
  object-fit: cover;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

.agent-info h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.agent-info p {
  margin: 0;
  font-size: 14px;
  color: #666;
  line-height: 1.4;
}

.welcome-message h1 {
  font-size: 36px;
  margin: 0 0 16px 0;
  font-weight: 700;
  color: #333;
  line-height: 1.2;
}

.welcome-message h1 span {
  color: #e53935;
}

.welcome-message p {
  font-size: 18px;
  color: #666;
  margin: 0 0 32px 0;
  line-height: 1.5;
}

/* 底部输入框 */
.input-area {
  padding: 24px;
  background-color: #fff;
  border-top: 1px solid #e0e0e0;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
}

.input-box {
  flex: 1;
  position: relative;
}

.input-box input {
  width: 100%;
  padding: 16px 20px;
  border: 1px solid #e0e0e0;
  border-radius: 28px;
  font-size: 14px;
  resize: none;
  transition: all 0.2s ease;
  background-color: #f8f9fa;
}

.input-box input:focus {
  outline: none;
  border-color: #1976d2;
  background-color: #fff;
  box-shadow: 0 0 0 2px rgba(25, 118, 210, 0.2);
}

.input-options {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: nowrap;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  background-color: #f0f0f0;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  border: 1px solid #e0e0e0;
}

.option-item:hover {
  background-color: #e0e0e0;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.send-btn {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background-color: #1976d2;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 6px rgba(25, 118, 210, 0.3);
}

.send-btn:hover {
  background-color: #1565c0;
  transform: scale(1.05);
  box-shadow: 0 4px 10px rgba(25, 118, 210, 0.4);
}

/* 配置界面 */
.config-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.config-dialog {
  background-color: #fff;
  border-radius: 16px;
  width: 480px;
  max-width: 90%;
  box-shadow: 0 8px 24px rgba(0,0,0,0.15);
  overflow: hidden;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.config-header {
  padding: 24px;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #f8f9fa;
}

.config-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #666;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  transition: all 0.2s ease;
}

.close-btn:hover {
  background-color: #e0e0e0;
  color: #333;
}

.config-content {
  padding: 32px 24px;
}

/* 聊天消息样式 */
.chat-messages {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
  height: 100%;
}

.message {
  display: flex;
  margin-bottom: 16px;
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.message-content {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 16px;
  line-height: 1.4;
}

.user-message {
  background-color: #e3f2fd;
  color: #1976d2;
  border-top-right-radius: 4px;
}

.assistant-message {
  background-color: #f8f9fa;
  color: #333;
  border-top-left-radius: 4px;
}

.reasoning {
  font-style: italic;
  color: #666;
  margin-bottom: 8px;
}

.answer {
  font-weight: 500;
}

/* 加载状态 */
.loading-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background-color: #f0f0f0;
  border-radius: 12px;
  align-self: flex-start;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #e0e0e0;
  border-top: 2px solid #1976d2;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* 错误消息 */
.error-message {
  padding: 12px;
  background-color: #ffebee;
  color: #c62828;
  border-radius: 12px;
  align-self: flex-start;
  border-left: 4px solid #c62828;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .sidebar {
    width: 64px;
    padding: 20px 0;
  }
  
  .nav-name {
    display: none;
  }
  
  .nav-icon {
    margin-right: 0;
  }
  
  .nav-item {
    padding: 12px;
    justify-content: center;
  }
  
  .nav-item:hover,
  .nav-item.active {
    padding: 12px;
  }
  
  .top-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    padding: 16px 20px;
  }
  
  .search-box {
    max-width: 100%;
  }
  
  .content-area {
    padding: 24px;
  }
  
  .welcome-section {
    padding: 32px;
  }
  
  .agent-item {
    width: 100%;
  }
  
  .input-area {
    padding: 16px 20px;
    flex-wrap: wrap;
  }
  
  .input-options {
    flex-wrap: wrap;
    gap: 8px;
  }
  
  .option-item {
    font-size: 12px;
    padding: 8px 12px;
  }
  
  .config-dialog {
    width: 95%;
  }
  
  .message-content {
    max-width: 85%;
  }
}
</style>
