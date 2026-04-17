# Bilibili RAG Wiki 构建系统

基于 Karpathy LLM Wiki 方案的个人知识库构建系统。

## 核心思想

传统 RAG 方案每次提问时从原始文档检索，LLM 重新发现知识，没有积累。

**Wiki 方案**：LLM 增量构建和维护持久化 Wiki，知识已编译并持续更新，越用越丰富。

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env

# 启用 Wiki 构建
WIKI_ENABLED=true

# 配置本地 LLM 服务（vLLM）
LOCAL_LLM_BASE_URL=http://localhost:8000/v1
LOCAL_LLM_MODEL=qwen3.5-35b-a3b

# 配置 Wiki 存储目录
WIKI_DIR=./data/wiki
```

### 2. 启动 vLLM 服务

```bash
vllm serve Qwen/Qwen3.5-35B-A3B \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 4
```

### 3. 启动后端服务

```bash
python -m uvicorn app.main:app --reload
```

### 4. 构建 Wiki 知识库

通过 API 构建（使用 Wiki 模式）：

```bash
curl -X POST "http://localhost:8000/knowledge/build" \
  -H "Content-Type: application/json" \
  -d '{
    "folder_ids": [123],
    "use_wiki": true
  }'
```

### 5. 查看 Wiki 统计

```bash
curl "http://localhost:8000/knowledge/wiki/stats"
```

## Wiki 目录结构

```
data/wiki/
├── index.md              # 全局索引
├── log.md                # 操作日志
├── raw/                  # 原始素材
│   └── {bvid}/
│       ├── asr.txt       # ASR 转写
│       ├── vision.json   # 视觉分析
│       └── meta.json     # 视频元信息
├── concepts/             # 概念页面
│   ├── 三层架构.md
│   ├── Spring Boot.md
│   └── ...
├── entities/             # 实体页面
│   ├── MySQL.md
│   ├── Redis.md
│   └── ...
└── videos/               # 视频摘要
    ├── BV1abc123.md
    └── ...
```

## API 接口

### 构建知识库

```
POST /knowledge/build
```

请求体：
```json
{
  "folder_ids": [123, 456],
  "exclude_bvids": [],
  "use_wiki": true  // 使用 Wiki 模式
}
```

### 查看 Wiki 统计

```
GET /knowledge/wiki/stats
```

响应：
```json
{
  "total_concepts": 25,
  "total_entities": 10,
  "total_videos": 50,
  "last_update": "2026-04-16 14:00:00"
}
```

### 查看构建任务状态

```
GET /knowledge/build/status/{task_id}
```

## 工作原理

### Ingest（入库）

1. 读取视频原始素材（ASR 转写 + 视觉分析）
2. 使用 LLM 提取关键概念和实体
3. 生成/更新 Wiki 页面
4. 更新索引和日志

### Query（查询）

1. 读取 index.md 找到相关页面
2. 阅读页面内容（概念页面已整合多视频内容）
3. 综合生成答案

## 与传统 RAG 对比

| 维度 | 传统 RAG | Wiki 方案 |
|------|----------|-----------|
| 知识存储 | 原始文档 + 向量 | 结构化 Markdown |
| 知识积累 | 无积累 | 增量构建，越用越丰富 |
| 跨文档推理 | 每次重新整合 | 已整合在 Wiki 中 |
| "三层架构是什么" | 可能找不到 | 概念页面已融合内容 |

## 配置说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| WIKI_ENABLED | true | 是否启用 Wiki 构建 |
| WIKI_DIR | ./data/wiki | Wiki 存储目录 |
| LOCAL_LLM_BASE_URL | http://localhost:8000/v1 | 本地 LLM 服务地址 |
| LOCAL_LLM_MODEL | qwen3.5-35b-a3b | 本地 LLM 模型名称 |

## 注意事项

1. **LLM 服务必须可用**：Wiki 构建依赖本地 LLM 服务提取概念
2. **处理时间较长**：每个视频需要调用 LLM 提取概念
3. **存储空间**：Wiki 文件会占用磁盘空间，建议定期清理

## 扩展阅读

- [Karpathy LLM Wiki 方案](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Wiki Schema 定义](schema/BILIBILI_WIKI.md)