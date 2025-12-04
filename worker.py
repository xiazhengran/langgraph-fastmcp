"""
Worker 子图模块
包含反思节点和工具执行节点
"""

import json
from typing import Any
from langgraph.graph import StateGraph, END
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from states import WorkerState, ReflectionResult, Task
from utils import get_llm, create_messages, parse_json_response, log_step
from meta import get_prompt


# ============= MCP 客户端管理 =============

class MCPClientManager:
    """MCP 客户端管理器 (兼容 FastMCP)"""
    
    def __init__(self):
        self.session: ClientSession | None = None
        self.exit_stack = None
        self._tools_cache = None  # 缓存工具列表
    
    async def connect(self, server_params: StdioServerParameters):
        """连接到 MCP 服务器"""
        from contextlib import AsyncExitStack
        
        self.exit_stack = AsyncExitStack()
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write)
        )
        await self.session.initialize()
    
    async def list_tools(self) -> list:
        """
        获取 MCP 服务器提供的所有工具
        
        Returns:
            工具列表
        """
        if not self.session:
            raise RuntimeError("MCP session not initialized")
        
        # 使用缓存避免重复请求
        if self._tools_cache is not None:
            return self._tools_cache
        
        result = await self.session.list_tools()
        self._tools_cache = result.tools
        return result.tools
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """调用工具"""
        if not self.session:
            raise RuntimeError("MCP session not initialized")
        
        result = await self.session.call_tool(tool_name, arguments)
        
        # 提取文本内容
        if result.content and len(result.content) > 0:
            content = result.content[0]
            # 处理不同类型的内容
            if hasattr(content, 'text'):
                return content.text
            elif hasattr(content, 'data'):
                return content.data
            else:
                return str(content)
        return None
    
    async def close(self):
        """关闭连接"""
        if self.exit_stack:
            await self.exit_stack.aclose()


# 全局 MCP 客户端实例
mcp_client = MCPClientManager()


# ============= 节点函数 =============

async def reflection_node(state: WorkerState) -> WorkerState:
    """
    反思节点: 在执行工具前思考是否正确理解用户意图
    """
    task = state["task"]
    
    log_step("反思节点", {
        "task_id": task.task_id,
        "description": task.description,
        "tool": task.tool,
        "arguments": task.arguments
    })
    
    # 构建反思提示
    reflection_prompt = f"""
任务信息:
- 描述: {task.description}
- 工具: {task.tool}
- 参数: {json.dumps(task.arguments, ensure_ascii=False)}

请仔细思考并回答:
1. 是否正确理解了任务意图?
2. 选择的工具是否合适?
3. 参数是否正确?
4. 是否有更好的执行方案?
"""
    
    try:
        llm = get_llm(temperature=0.3)
        messages = create_messages(get_prompt("reflection_system"), reflection_prompt)
        response = await llm.ainvoke(messages)
        
        # 解析反思结果
        reflection_data = parse_json_response(response.content)
        reflection = ReflectionResult(**reflection_data)
        
        log_step("反思结果", reflection.model_dump())
        
        state["reflection"] = reflection
        
        # 如果反思认为不应该继续,设置错误
        if not reflection.proceed:
            state["error"] = f"反思建议停止执行: {reflection.suggestions}"
        
    except Exception as e:
        log_step("反思节点错误", str(e))
        state["error"] = f"反思节点错误: {str(e)}"
    
    return state


async def tool_execution_node(state: WorkerState) -> WorkerState:
    """
    工具执行节点: 调用 MCP 工具执行任务
    """
    task = state["task"]
    reflection = state.get("reflection")
    
    # 如果反思不通过,跳过执行
    if reflection and not reflection.proceed:
        log_step("跳过工具执行", "反思建议停止")
        return state
    
    log_step("工具执行节点", {
        "task_id": task.task_id,
        "tool": task.tool,
        "arguments": task.arguments
    })
    
    try:
        # 调用 MCP 工具
        result = await mcp_client.call_tool(task.tool, task.arguments)
        
        log_step("工具执行结果", result)
        
        state["tool_result"] = result
        task.status = "completed"
        task.result = result
        
    except Exception as e:
        log_step("工具执行错误", str(e))
        state["error"] = f"工具执行错误: {str(e)}"
        task.status = "failed"
        task.error = str(e)
    
    return state


def should_execute_tool(state: WorkerState) -> str:
    """
    条件边: 判断是否应该执行工具
    """
    if state.get("error"):
        return "end"
    
    reflection = state.get("reflection")
    if reflection and not reflection.proceed:
        return "end"
    
    return "execute"


# ============= 构建子图 =============

def create_worker_graph() -> StateGraph:
    """
    创建 Worker 子图
    
    流程:
    1. reflection_node: 反思任务
    2. tool_execution_node: 执行工具 (条件执行)
    """
    workflow = StateGraph(WorkerState)
    
    # 添加节点
    workflow.add_node("reflection", reflection_node)
    workflow.add_node("tool_execution", tool_execution_node)
    
    # 设置入口
    workflow.set_entry_point("reflection")
    
    # 添加边
    workflow.add_conditional_edges(
        "reflection",
        should_execute_tool,
        {
            "execute": "tool_execution",
            "end": END
        }
    )
    
    workflow.add_edge("tool_execution", END)
    
    return workflow.compile()
