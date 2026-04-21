# 📚 Bilibili Wiki：把收藏夹变成可对话的持久化知识库

基于 **Karpathy LLM Wiki 方案**，将你的 B 站收藏夹变成可对话的持久化知识库。

> 核心思想：LLM 增量构建和维护持久化 Wiki，知识已编译并持续更新，越用越丰富。

---

## ✨ 功能一览

- ✅ B 站扫码登录，读取收藏夹
- ✅ 本地 ASR 转写（兼容 OpenAI 格式）
- ✅ **Wiki 构建** - 增量构建结构化知识库
- ✅ **概念提取** - 自动提取关键概念和实体
- ✅ **智能问答** - 基于 Wiki 回答问题
- ✅ **本地 LLM** - 使用 Qwen3.5 通过 vLLM 部署
- ✅ **本地 VLM** - 可选的视觉分析功能

---

## 🖼️ 演示与截图

![首页截图](assets/screenshots/home.png)
![对话界面截图](assets/screenshots/chat.png)

---

## ⚡ 快速开始（3 步）

### 0) 安装依赖

```bash
# 安装系统依赖
# macOS: brew install ffmpeg
# Windows: 下载安装包后将 bin 目录加入 PATH
# Linux: apt/yum/pacman 安装 ffmpeg

# 安装 Python 依赖
conda activate bilibili-rag
pip install -r requirements.txt
```

### 1) 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写配置
```

### 2) 启动服务

```bash
# 启动后端
python -m uvicorn app.main:app --reload
# 后端文档：http://localhost:8000/docs

# 启动前端
cd frontend
npm install
npm run dev
# 前端页面：http://localhost:3000
```

---

## 🧠 工作流程

```
1. 选择收藏夹 → 2. 拉取视频 → 3. 本地 ASR 转写
4. 概念提取 → 5. 生成 Wiki 页面 → 6. 对话问答
```

### Wiki 构建过程

1. **读取原始素材**：ASR 转写 + 视频元信息
2. **概念提取**：使用 Qwen3.5 提取关键概念和实体
3. **生成页面**：创建/更新概念页面、实体页面、视频摘要
4. **维护索引**：更新全局索引和操作日志

---

## 📁 Wiki 目录结构

```
data/wiki/
├── index.md              # 全局索引
├── log.md                # 操作日志
├── raw/                  # 原始素材
│   └── {bvid}/
│       ├── asr.txt       # ASR 转写
│       └── meta.json     # 视频元信息
├── concepts/             # 概念页面（核心知识点）
│   ├── 三层架构.md
│   ├── Spring Boot.md
│   └── ...
├── entities/             # 实体页面（工具/框架/技术）
│   ├── MySQL.md
│   ├── Redis.md
│   └── ...
└── videos/               # 视频摘要
    ├── BV1abc123.md
    └── ...
```

---

## 🤖 本地服务配置

### 1. 启动 vLLM 服务（LLM）

```bash
vllm serve Qwen/Qwen3.5-35B-A3B \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 4
```

### 2. 启动 ASR 服务

```bash
# 使用 Whisper 或其他兼容 OpenAI 格式的 ASR 服务
# 示例：http://localhost:1234/v1
```

### 3. 启动 VLM 服务（可选）

```bash
# 如果需要视觉分析功能
# 示例：http://localhost:3000/v1
```

### 环境变量配置

```bash
# 本地 LLM 配置
LOCAL_LLM_BASE_URL=http://localhost:8000/v1
LOCAL_LLM_API_KEY=your_llm_api_key_here
LOCAL_LLM_MODEL=qwen3.5-35b-a3b

# 本地 ASR 配置
LOCAL_ASR_BASE_URL=http://localhost:1234/v1
LOCAL_ASR_API_KEY=your_asr_api_key_here
LOCAL_ASR_MODEL=whisper

# 本地 VLM 配置（可选）
LOCAL_VLM_BASE_URL=http://localhost:3000/v1
LOCAL_VLM_API_KEY=your_vlm_api_key_here
LOCAL_VLM_MODEL=qwen2.5-vl-72b-instruct
```

---

## 💰 费用说明

- **本地 LLM**：无费用（使用本地 Qwen3.5）
- **本地 ASR**：无费用（使用本地 Whisper）
- **本地 VLM**：无费用（使用本地 Qwen2.5-VL）

---

## 🐳 Docker 部署

### 构建镜像

```bash
# 构建 Docker 镜像
docker build -t bilibili-rag:latest .
```

### 上传镜像到仓库 (可选)

```bash
# 标记镜像
docker tag bilibili-rag:latest your-registry/bilibili-rag:latest

# 推送到仓库
docker push your-registry/bilibili-rag:latest
```

### 使用 Docker Compose 启动

```bash
# 确保 .env 文件已配置
cp .env.example .env
# 编辑 .env，填写配置

# 启动服务
docker-compose up -d

# 访问应用
# 前端: http://localhost
# 后端 API: http://localhost/api/...
# API 文档: http://localhost/api/docs
```

### 停止服务

```bash
docker-compose down
```

---

## 🧩 技术栈

- **后端**：FastAPI
- **LLM**：Qwen3.5-35B-A3B (本地 vLLM)
- **ASR**：Whisper (本地，兼容 OpenAI 格式)
- **VLM**：Qwen2.5-VL (可选，本地)
- **前端**：Next.js + Tailwind (静态导出)
- **数据库**：SQLite
- **容器化**：Docker 多阶段构建 + Nginx 反向代理
- **方案**：基于 Karpathy LLM Wiki

---

## 📂 目录结构

```
bilibili-wiki/
├── app/                # 后端逻辑
├── frontend/           # 前端界面
├── data/               # 数据库与 Wiki
├── schema/             # Wiki 模式定义
├── test/               # 测试脚本
└── README.md
```

---

## ✅ 常见问题

**Q：为什么有些音频 URL 可达、有些不可达？**  
A：B 站音频直链存在鉴权/过期/区域限制，只有公网可直接拉取的 URL 才可达。

---

> 免责声明：本项目仅供个人学习与技术研究，使用者需自行遵守相关平台协议与法律法规，禁止用于未授权的商业或违规用途。

---

## 📜 License

MIT

---

## 📖 扩展阅读

- [Karpathy LLM Wiki 方案](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Wiki 构建文档](README.WIKI.md)
- [Wiki Schema 定义](schema/BILIBILI_WIKI.md)