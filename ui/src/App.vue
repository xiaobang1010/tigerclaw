<script setup>
import { ref } from 'vue'

// 状态管理
const showConfig = ref(false)
const showModelConfig = ref(false)
const activeNav = ref('chat')

// 导航菜单
const navItems = [
  { id: 'chat', name: '对话', icon: '💬' },
  { id: 'inspiration', name: '灵感', icon: '💡' },
  { id: 'task', name: '任务', icon: '✓' },
  { id: 'help', name: '帮助', icon: '?' },
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
          <span class="nav-icon">{{ item.icon }}</span>
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
        <div class="welcome-section">
          <div class="agent-item">
            <div class="agent-icon">
              <img src="https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=red%20tiger%20claw%20icon&image_size=square" alt="TigerClaw" />
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
      </div>
      
      <!-- 底部输入框 -->
      <div class="input-area">
        <div class="input-box">
          <input type="text" placeholder="可以描述任务或提问任何问题" />
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
        <div class="send-btn">
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
          <p>配置界面内容</p>
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
          <p>大模型配置内容</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  background-color: #f5f5f5;
  font-family: Arial, sans-serif;
}

/* 左侧导航栏 */
.sidebar {
  width: 240px;
  background-color: #fff;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  padding: 20px 0;
}

.user-avatar {
  padding: 0 20px 20px;
  display: flex;
  justify-content: center;
}

.user-avatar img {
  width: 48px;
  height: 48px;
  border-radius: 50%;
}

.nav-items {
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 12px 20px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.nav-item:hover {
  background-color: #f0f0f0;
}

.nav-item.active {
  background-color: #e3f2fd;
  color: #1976d2;
}

.nav-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 12px;
  font-size: 18px;
}

.nav-name {
  font-size: 14px;
}

.sidebar-bottom {
  padding: 20px;
  display: flex;
  justify-content: center;
}

.settings-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background-color: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 0.2s;
}

.settings-btn:hover {
  background-color: #e0e0e0;
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
  padding: 20px;
  background-color: #fff;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.search-box {
  flex: 1;
  max-width: 400px;
}

.search-box input {
  width: 100%;
  padding: 10px 15px;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  font-size: 14px;
}

.top-buttons {
  display: flex;
  align-items: center;
  gap: 20px;
}

.new-agent-btn {
  padding: 8px 16px;
  background-color: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.new-agent-btn:hover {
  background-color: #f0f0f0;
}

.usage-info {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #666;
}

.clock-icon {
  font-size: 16px;
}

/* 内容区域 */
.content-area {
  flex: 1;
  padding: 40px;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
}

.welcome-section {
  text-align: center;
  max-width: 600px;
  width: 100%;
}

.agent-item {
  display: flex;
  align-items: center;
  background-color: #fff;
  padding: 15px;
  border-radius: 10px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  margin-bottom: 40px;
  width: 300px;
  margin-left: auto;
  margin-right: auto;
}

.agent-icon {
  margin-right: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.agent-icon img {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  object-fit: cover;
}

.agent-info h3 {
  margin: 0 0 5px 0;
  font-size: 16px;
}

.agent-info p {
  margin: 0;
  font-size: 14px;
  color: #666;
}

.welcome-message h1 {
  font-size: 32px;
  margin: 0 0 10px 0;
  font-weight: 600;
}

.welcome-message h1 span {
  color: #e53935;
}

.welcome-message p {
  font-size: 16px;
  color: #666;
  margin: 0;
}

/* 底部输入框 */
.input-area {
  padding: 20px;
  background-color: #fff;
  border-top: 1px solid #e0e0e0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.input-box {
  flex: 1;
}

.input-box input {
  width: 100%;
  padding: 12px 15px;
  border: 1px solid #e0e0e0;
  border-radius: 25px;
  font-size: 14px;
  resize: none;
}

.input-options {
  display: flex;
  gap: 10px;
  align-items: center;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 12px;
  background-color: #f0f0f0;
  border-radius: 15px;
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.2s;
  white-space: nowrap;
}

.option-item:hover {
  background-color: #e0e0e0;
}

.send-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background-color: #1976d2;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 0.2s;
}

.send-btn:hover {
  background-color: #1565c0;
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
}

.config-dialog {
  background-color: #fff;
  border-radius: 10px;
  width: 400px;
  max-width: 90%;
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

.config-header {
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.config-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
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
  width: 24px;
  height: 24px;
}

.config-content {
  padding: 20px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .sidebar {
    width: 60px;
  }
  
  .nav-name {
    display: none;
  }
  
  .nav-icon {
    margin-right: 0;
  }
  
  .top-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  
  .search-box {
    max-width: 100%;
  }
  
  .content-area {
    padding: 20px;
  }
  
  .input-options {
    flex-wrap: wrap;
  }
  
  .option-item {
    font-size: 12px;
    padding: 6px 10px;
  }
}
</style>
