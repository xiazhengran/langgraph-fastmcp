# LangGraph + FastMCP 智能代理系统

一个基于 LangGraph 和 FastMCP (Model Context Protocol) 的企业级智能代理系统,支持任务规划、反思和工具调用。

## 📋 功能特性

- **🎯 智能任务规划**: 自动将复杂任务分解为可执行的子任务
- **🔧 LangChain 工具集成**: 使用 `bind_tools()` 和 `ToolNode` 标准化工具调用
- **⚡ FastMCP 支持**: 使用 FastMCP 简化 MCP 服务器开发
- **🔄 动态工具发现**: 自动从 MCP 服务器获取工具信息
- **📊 依赖管理**: 支持任务间的依赖关系和结果引用
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

```bash
python agent.py
```

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

## 📝 任务依赖引用

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
