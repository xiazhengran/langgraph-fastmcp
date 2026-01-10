# LangGraph + FastMCP 智能代理系统

一个基于 LangGraph 和 FastMCP (Model Context Protocol) 的企业级智能代理系统,支持任务规划、反思和工具调用。

## 📋 功能特性

- **🎯 智能任务规划**: 自动将复杂任务分解为可执行的子任务
- **🔧 LangChain 工具集成**: 使用 `bind_tools()` 和 `ToolNode` 标准化工具调用
- **⚡ FastMCP 支持**: 使用 FastMCP 简化 MCP 服务器开发
- **🔄 动态工具发现**: 自动从 MCP 服务器获取工具信息
- **📊 智能依赖管理**: 
  - 支持任务间的依赖关系和结果引用
  - **字段级引用**: 支持 `${task_id.field}` 格式，从复杂结果中提取特定字段
  - **自动依赖分析**: 即使 `depends_on` 为空，系统会自动从参数中提取依赖
  - **智能复用**: 自动复用已执行的 search_metrics 结果，避免重复查询
- **🗄️ 数据库集成**: 
  - 支持 MySQL 数据库查询
  - **语义指标检索**: 通过 search_metrics 从中文指标名找到数据库字段名
  - **灵活日期格式**: 支持单日、年月、日期范围等多种日期格式
- **📈 LangSmith 监控**: 集成 LangSmith 追踪所有 LLM 调用和任务执行
- **🏢 企业级架构**: 模块化设计,代码清晰,易于维护

## 🏗️ 架构设计

### 核心流程
```
用户输入 → 规划节点 (JSON计划) → 执行节点 (LangChain工具) → 最终答案节点
```

**规划阶段:**
- LLM 根据工具描述生成 JSON 格式的任务计划
- 不使用 `bind_tools()`,避免 LLM 直接调用工具
- 支持任务依赖和结果引用

**执行阶段:**
- 使用 LangChain `BaseTool` 执行工具调用
- 自动参数验证和类型检查
- 支持异步执行

### 技术栈
- **LangChain**: 工具封装和执行
- **LangGraph**: 状态图管理
- **FastMCP**: 简化 MCP 服务器开发
- **动态工具封装**: 自动将 MCP 工具转换为 LangChain `BaseTool`

## 📁 项目结构

```
langgraph-fastmcp/
├── agent.py           # 主入口:初始化 MCP 连接,构建和运行图
├── states.py          # 状态定义:TypedDict 和 Pydantic 模型
├── utils.py           # 工具函数:LLM 初始化、Schema 转换等
├── tools.py           # 工具封装:MCP 工具 → LangChain BaseTool
├── worker.py          # MCP 客户端管理
├── planner.py         # Planner 主图:使用 bind_tools 和 ToolNode
├── mcp_server.py      # MCP 服务器:FastMCP 实现
├── meta.py            # Prompt 管理:动态生成工具描述
├── requirements.txt   # 项目依赖
├── .env              # 环境配置
└── README.md         # 项目文档
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

编辑 `.env` 文件:

```env
# OpenAI 兼容接口配置
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL=gpt-4

# MCP 服务器配置
MCP_SERVER_COMMAND=python
MCP_SERVER_ARGS=mcp_server.py

# API 服务配置 (可选)
API_HOST=0.0.0.0
API_PORT=8000

# LangSmith 监控配置 (可选)
LANGSMITH_API_KEY=your-langsmith-api-key-here
LANGSMITH_PROJECT=langgraph-fastmcp
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_TRACING=true  # 设置为 false 可禁用监控
```

**LangSmith 监控说明:**
- 如需启用 LangSmith 监控,请设置 `LANGSMITH_TRACING=true` 并配置有效的 `LANGSMITH_API_KEY`
- 可在 [LangSmith 官网](https://smith.langchain.com/) 注册获取 API Key
- 监控数据将记录所有 LLM 调用、任务执行和工具调用,便于调试和优化


### 3. 运行程序

**方式一: 命令行交互模式**

```bash
python agent.py
```

**方式二: HTTP 服务模式 (FastAPI)**

```bash
python app.py
```

服务默认运行在 `http://0.0.0.0:8898`

## 🌐 HTTP API 服务

启动 FastAPI 服务后,提供以下 REST API 接口:

### 接口列表

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/` | 根路径健康检查 |
| GET | `/health` | 健康检查端点 |
| POST | `/chat` | 聊天接口,执行任务并返回结果 |
| POST | `/chat/stream` | 流式聊天接口 |

### /chat 接口

**请求格式:**
```json
{
  "user_input": "查询差评率2025年1月在江西省南昌市的数据"
}
```

**响应格式:**
```json
{
  "success": true,
  "final_answer": "查询结果...",
  "tasks": [
    {
      "task_id": "task_1",
      "description": "搜索指标",
      "tool": "search_metrics",
      "status": "completed",
      "result": "...",
      "error": null
    },
    {
      "task_id": "task_2",
      "description": "查询数据",
      "tool": "query_sales_summary_detail",
      "status": "completed",
      "result": "...",
      "error": null
    }
  ],
  "error": null
}
```

### /chat/stream 接口 (SSE 流式输出)

**请求格式:**
```json
{
  "user_input": "计算 (3 + 5) * 2 的结果"
}
```

**响应格式 (NDJSON - 每行一个 JSON):**
```
{"type": "start", "content": "🚀 开始处理: 客单价在哪张表?"}
{"type": "phase", "content": "📋 规划阶段 - 开始分析用户需求..."}
{"type": "info", "content": "获取到 5 个可用工具"}
{"type": "info", "content": "正在调用 LLM 生成任务计划..."}
{"type": "plan_ready", "content": "✅ 计划生成完成，共 1 个任务"}
{"type": "task", "content": "[task_1] 搜索客单价指标的相关信息 (工具: search_metrics)"}
{"type": "phase", "content": "⚡ 执行阶段 - 开始执行 1 个任务"}
{"type": "executing", "content": "正在执行任务 [task_1]: 搜索客单价指标的相关信息"}
{"type": "complete", "content": "✅ 任务 [task_1] 完成: {\"results\":[...]}"}
{"type": "phase", "content": "💡 最终答案阶段 - 正在生成答案..."}
{"type": "answer", "content": "根"}
{"type": "answer", "content": "据"}
{"type": "answer", "content": "任"}
...
{"type": "done", "content": "✅ 处理完成，最终答案长度: 186 字符"}
```

**事件类型:**
| 类型 | 描述 |
|------|------|
| `start` | 开始处理请求 |
| `phase` | 当前执行阶段 (规划/执行/生成答案) |
| `info` | 详细信息 |
| `plan_ready` | 计划生成完成 |
| `task` | 任务列表 |
| `executing` | 正在执行任务 |
| `complete` | 任务执行完成 |
| `error` | 错误信息 |
| `answer` | 最终答案逐字输出 |
| `done` | 处理完成 |

### 调用示例

**cURL (普通接口):**
```bash
curl -X POST http://localhost:8898/chat \
  -H "Content-Type: application/json" \
  -d '{"user_input": "计算 (3 + 5) * 2 的结果"}'
```

**cURL (流式接口):**
```bash
curl -N -X POST http://localhost:8898/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"user_input": "计算 (3 + 5) * 2 的结果"}'
```

**Windows CMD 正确调用方式:**
```cmd
curl -N -X POST http://localhost:8898/chat/stream -H "Content-Type: application/json" -d "{\"user_input\": \"客单价在哪张表?\"}"
```

**Windows PowerShell 调用方式:**
```powershell
curl -N -X POST http://localhost:8898/chat/stream -H 'Content-Type: application/json' -d '{"user_input": "客单价在哪张表?"}'
```

**Python (流式):**
```python
import httpx
import json

async def stream_chat():
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "http://localhost:8898/chat/stream",
            json={"user_input": "计算 (3 + 5) * 2 的结果"}
        ) as response:
            async for line in response.aiter_lines():
                if line.strip():
                    data = json.loads(line)
                    print(f"[{data['type']}] {data['content']}")

# asyncio.run(stream_chat())
```

> **Windows 注意事项:**
> - CMD 中需要用 `^` 换行，或者全部写在一行
> - JSON 中的双引号需要转义为 `\"`
> - 建议使用 PowerShell 或创建 JSON 文件后用 `-d @filename` 发送

### 浏览器 JavaScript 调用

**普通接口:**
```javascript
fetch('http://localhost:8898/chat', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({ user_input: "客单价在哪张表?" })
})
.then(response => response.json())
.then(data => console.log('响应数据:', data))
.catch(error => console.error('请求出错:', error));
```

**SSE 流式接口:**
```javascript
fetch('http://localhost:8898/chat/stream', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_input: "我想知道2025年1月5日到2025年7月6日九江市的的客单价?"})
})
.then(res => res.text()) // 注意：用 .text() 而不是 .json()
.then(console.log)
.catch(console.error);
```

> **注意:** 在浏览器控制台直接复制粘贴执行即可，确保 FastAPI 服务已启动 (端口 8898)。

## 💡 使用示例

### 示例 1: 数学计算

**输入:**
```
计算 (3 + 5) * 2 的结果
```

**执行流程:**
1. 规划节点分解任务:
   - task_1: 使用 add 工具计算 3 + 5
   - task_2: 使用 multiply 工具计算 task_1 的结果 * 2
2. 执行节点按顺序执行:
   - task_1 反思 → 执行 add(3, 5) → 返回 8
   - task_2 反思 → 执行 multiply(8, 2) → 返回 16
3. 最终答案: 16

### 示例 2: 字符串处理

**输入:**
```
将 "hello" 和 "world" 拼接后计算 MD5 的前8位
```

**执行流程:**
1. 规划节点分解任务:
   - task_1: 使用 concat_and_md5_truncate 工具
2. 执行节点执行:
   - task_1 反思 → 执行 concat_and_md5_truncate("hello", "world") → 返回 MD5 前8位
3. 最终答案: MD5 哈希值

### 示例 3: 数据库查询（智能指标检索）

**输入:**
```
查询差评率2025年1月在江西省南昌市的数据
```

**执行流程:**
1. 规划节点分解任务:
   - task_1: 使用 search_metrics 工具搜索"差评率"
   - task_2: 使用 query_sales_summary_detail 工具查询数据，依赖 task_1 的 metric_name
2. 执行节点按顺序执行:
   - task_1 反思 → 执行 search_metrics("差评率")
     返回: `{"results": [{"metric_name": "negative_review_rate_034", "metric_name_cn": "差评率", ...}]}`
   
   - task_2 反思 → 解析依赖 `${task_1.metric_name}`
     提取 metric_name: "negative_review_rate_034"
     执行 query_sales_summary_detail(
       metric_name="negative_review_rate_034",
       date="2025-01",  # 自动转换为 2025-01-01 至 2025-01-31
       province="江西省",
       city="南昌市"
     )
     返回: 查询结果列表
3. 最终答案: 返回差评率的明细数据和汇总

**关键特性：**
- ✅ 智能指标检索：使用 search_metrics 从中文指标名找到数据库字段名
- ✅ 字段级依赖：使用 `${task_1.metric_name}` 提取特定字段
- ✅ 灵活日期格式：支持年月格式 "2025-01"，自动扩展为月份范围
- ✅ 自动依赖管理：系统自动检测并添加 task_1 到 task_2 的 depends_on

## 🔧 可用工具

### add
- **描述**: 执行两个数字的加法运算
- **参数**: 
  - `a` (number): 第一个加数
  - `b` (number): 第二个加数
- **返回**: 和

### multiply
- **描述**: 执行两个数字的乘法运算
- **参数**:
  - `a` (number): 第一个乘数
  - `b` (number): 第二个乘数
- **返回**: 积

### concat_and_md5_truncate
- **描述**: 拼接两个字符串并返回 MD5 哈希值的前8位
- **参数**:
  - `str1` (string): 第一个字符串
  - `str2` (string): 第二个字符串
- **返回**: MD5 哈希值前8位

### search_metrics
- **描述**: 从知识库中检索相关的指标信息（基于语义搜索）
- **参数**:
  - `value` (string): 搜索的关键词，例如 "差评率"
  - `column_name` (string, 可选): 要搜索的字段名，默认为 "metric_name_cn"（指标中文名）
  - `n_results` (number, 可选): 返回结果数量，默认为 3
- **返回**: 包含检索结果的字典，每个结果包含：
  - `metric_name`: 指标英文名（数据库字段名）
  - `metric_name_cn`: 指标中文名
  - `description`: 描述
  - `calculation_method`: 计算方法
  - `usage_guide`: 使用指南
  - `source_table`: 来源表
  - `similarity_score`: 相似度得分

### query_sales_summary_detail
- **描述**: 从 MySQL 数据库中查询 dws_sales_summary 表的明细数据
- **参数**:
  - `metric_name` (string, 必填): 指标字段名，例如 'negative_review_rate_034'
    - 注意：这是数据库中的字段名，不是指标中文名
    - 应先使用 search_metrics 获取标准的字段名
  - `date` (string, 可选): 时间/日期，支持以下格式：
    - 单个日期：'2024-01-01'
    - 年月：'2024-01' 或 '2024-01:01' (查询该月，如2025年1月)
    - 日期范围：'2024-01-01:2024-01-31' (使用冒号分隔)
  - `province` (string, 可选): 省份
  - `city` (string, 可选): 城市
- **返回**: 查询结果列表，每条记录为一个字典，包含：
  - `stat_date`: 统计日期
  - `country`: 国家
  - `province`: 省份
  - `city`: 城市
  - `[metric_name]`: 指标值（字段名取决于传入的metric_name参数）

### query_models_val_detail
- **描述**: 从 MySQL 中获取指定 task_id 的 models_val_detail 表中的指定字段数据
- **参数**:
  - `task_id` (number): task_id
  - `column` (string): 指定要查询的字段
- **返回**: 指定 task_id 的指定 column 字段数据（JSON 字符串格式）

## 📝 任务依赖引用

### 基本引用格式

在任务参数中使用 `${task_id}` 引用其他任务的结果:

```json
{
  "tasks": [
    {
      "task_id": "task_1",
      "tool": "add",
      "arguments": {"a": 3, "b": 5},
      "depends_on": []
    },
    {
      "task_id": "task_2",
      "tool": "multiply",
      "arguments": {"a": "${task_1}", "b": 2},
      "depends_on": ["task_1"]
    }
  ]
}
```

### 字段级引用（智能特性）

系统支持字段级引用 `${task_id.field}`，可以从复杂结果中提取特定字段：

```json
{
  "tasks": [
    {
      "task_id": "task_1",
      "tool": "search_metrics",
      "arguments": {"value": "差评率"},
      "depends_on": []
    },
    {
      "task_id": "task_2",
      "tool": "query_sales_summary_detail",
      "arguments": {
        "metric_name": "${task_1.metric_name}",  // 从 search_metrics 结果中提取 metric_name 字段
        "date": "2025-01"
      },
      "depends_on": ["task_1"]
    }
  ]
}
```

**支持的特性：**
- ✅ 自动依赖分析：即使 `depends_on` 为空，系统会自动从参数中提取依赖
- ✅ 字段级提取：支持从 JSON 结果中提取特定字段
- ✅ 智能复用：自动复用已执行的 search_metrics 结果，避免重复查询
- ✅ 智能调用：如果使用 query_sales_summary_detail 但未提供依赖，会自动调用 search_metrics

## 📊 LangSmith 监控

本项目集成了 LangSmith 监控功能,可以追踪和调试所有 LLM 调用、任务执行和工具调用。

### 启用监控

1. **获取 API Key**: 访问 [LangSmith 官网](https://smith.langchain.com/) 注册并获取 API Key

2. **配置环境变量**: 在 `.env` 文件中设置:
   ```env
   LANGSMITH_API_KEY=your-actual-api-key
   LANGSMITH_PROJECT=langgraph-fastmcp
   LANGSMITH_TRACING=true
   ```

3. **运行程序**: 启动时会显示监控状态
   ```
   ✅ LangSmith 监控已启用
      项目: langgraph-fastmcp
      端点: https://api.smith.langchain.com
   ```

### 禁用监控

如果不需要监控,可以设置:
```env
LANGSMITH_TRACING=false
```

或直接删除/注释相关配置。

### 监控内容

LangSmith 会自动记录:
- 🤖 **LLM 调用**: 所有规划、反思、最终答案生成的 LLM 交互
- 📋 **任务执行**: 每个子任务的执行过程和结果
- 🔧 **工具调用**: MCP 工具的调用参数和返回值
- ⏱️ **性能指标**: 执行时间、Token 使用量等
- ❌ **错误追踪**: 异常和错误信息

### 查看监控数据

访问 [LangSmith Dashboard](https://smith.langchain.com/) 查看:
- 完整的执行链路追踪
- LLM 输入输出详情
- 性能分析和优化建议
- 错误日志和调试信息

## 🎨 自定义开发

### 添加新工具

1. 在 `mcp_server.py` 中定义工具:

```python
Tool(
    name="your_tool",
    description="工具描述",
    inputSchema={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "参数描述"}
        },
        "required": ["param1"]
    }
)
```

2. 实现工具逻辑:

```python
@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "your_tool":
        # 实现逻辑
        return [TextContent(type="text", text=result)]
```

### 修改 Prompt

编辑 `meta.py` 中的 `PROMPTS` 字典:

```python
PROMPTS = {
    "planner_system": "你的自定义规划提示词...",
    "reflection_system": "你的自定义反思提示词...",
    # ...
}
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request!

## 📄 许可证

MIT License
