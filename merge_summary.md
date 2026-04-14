此次合并在 /workspace/ui 目录中新增了一个完整的 Vue 3 前端项目，实现了与大模型的交互功能。项目包含完整的聊天界面、API 服务配置和响应式设计，为用户提供了一个现代化的 AI 助手界面。
| 文件 | 变更 |
|------|---------|
| ui/index.html | - 新增基础 HTML 结构，包含应用入口和元数据配置 |
| ui/package.json | - 新增项目配置，包含 Vue 3、Vite 和 Axios 等依赖 |
| ui/src/App.vue | - 新增完整的聊天界面组件，包含导航栏、消息展示、输入区域和配置对话框<br>- 实现消息发送和接收功能，支持流式响应处理<br>- 添加响应式设计，适配不同屏幕尺寸 |
| ui/src/services/api.js | - 新增 API 服务，实现与大模型的通信<br>- 支持流式响应处理和错误处理 |
| ui/src/main.js | - 新增应用入口，初始化 Vue 应用 |
| ui/src/style.css | - 新增全局样式，包含响应式设计和主题配置 |
| ui/vite.config.js | - 新增 Vite 配置文件 |
| ui/public/favicon.svg | - 新增网站图标 |
| ui/public/icons.svg | - 新增图标资源 |
| ui/src/assets/hero.png | - 新增英雄图资源 |
| ui/src/assets/vite.svg | - 新增 Vite 图标资源 |
| ui/src/assets/vue.svg | - 新增 Vue 图标资源 |
| ui/src/components/HelloWorld.vue | - 新增示例组件 |