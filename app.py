"""
FastAPI 服务模块
将 langgraph-fastmcp 的 agent 功能封装为 HTTP 服务
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from mcp import StdioServerParameters
from loguru import logger

from states import PlannerState
from worker import mcp_client
from utils import log_step

# 创建一个全局事件队列用于流式输出
event_queue: asyncio.Queue = None


def get_event_queue() -> asyncio.Queue:
    """获取或创建全局事件队列"""
    global event_queue
    if event_queue is None:
        event_queue = asyncio.Queue()
    return event_queue


async def put_event(event_type: str, content: str):
    """向事件队列添加事件"""
    global event_queue
    if event_queue is not None:
        await event_queue.put({"type": event_type, "content": content})


async def clear_events():
    """清空事件队列"""
    global event_queue
    if event_queue is not None:
        while not event_queue.empty():
            try:
                event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break


# ============= 自定义图节点函数 (内联实现以支持流式输出) =============

async def planning_with_stream(state: PlannerState) -> PlannerState:
    """规划节点: 生成 JSON 格式的任务计划 (带流式输出)"""
    from planner import build_planner_prompt, get_llm, Plan
    import re
    
    user_input = state["user_input"]
    
    logger.info(f"\n{'='*60}")
    logger.info("📋 规划节点 - 开始分析用户需求...")
    logger.info(f"{'='*60}")
    logger.info(f"用户输入: {user_input}\n")
    
    await put_event("phase", "📋 规划阶段 - 开始分析用户需求...")
    
    logger.info("开始获取 MCP 工具列表...")
    
    try:
        # 获取 MCP 工具用于生成描述
        mcp_tools = await mcp_client.list_tools()
        logger.info(f"✅ 成功获取 {len(mcp_tools)} 个可用工具")
        
        # 记录每个工具的详细信息
        for tool in mcp_tools:
            logger.debug(f"  - 工具名称: {tool.name}")
            logger.debug(f"    描述: {tool.description if hasattr(tool, 'description') else '无描述'}")
        
        await put_event("info", f"获取到 {len(mcp_tools)} 个可用工具")
        
        # 生成包含工具信息的 prompt
        planner_prompt = build_planner_prompt(mcp_tools)
        
        logger.info(f"Planner Prompt 长度: {len(planner_prompt)} 字符")
        logger.info(f"完整 Planner Prompt:\n{planner_prompt}")
        
        await put_event("info", "正在调用 LLM 生成任务计划...")
        
        logger.info("🚀 开始调用 LLM (规划节点)...")
        logger.info(f"LLM 配置: temperature=0.7, model={os.getenv('OPENAI_MODEL', 'gpt-4')}")
        
        # 不使用 bind_tools,让 LLM 返回 JSON 格式的计划
        llm = get_llm(temperature=0.7)
        
        # 调用 LLM 生成计划
        messages = [
            {"role": "system", "content": planner_prompt},
            {"role": "user", "content": user_input}
        ]
        
        logger.debug(f"LLM 输入消息数量: {len(messages)}")
        logger.debug(f"用户消息长度: {len(user_input)} 字符")
        
        # 使用流式输出
        full_content = ""
        chunk_count = 0
        async for chunk in llm.astream(messages):
            if hasattr(chunk, 'content') and chunk.content:
                full_content += chunk.content
                chunk_count += 1
        
        logger.info(f"✅ LLM 响应完成，共 {chunk_count} 个 chunk，总长度: {len(full_content)} 字符")
        logger.info(f"完整 LLM 响应:\n{full_content}")
        
        await put_event("info", f"LLM 响应完成，内容长度: {len(full_content)} 字符")
        
        # 解析响应
        if full_content:
            # 尝试解析 JSON 格式的计划
            try:
                # 提取 JSON
                if "```json" in full_content:
                    start = full_content.find("```json") + 7
                    end = full_content.find("```", start)
                    json_str = full_content[start:end].strip()
                elif "```" in full_content:
                    start = full_content.find("```") + 3
                    end = full_content.find("```", start)
                    json_str = full_content[start:end].strip()
                else:
                    json_str = full_content.strip()
                
                await put_event("info", f"提取到 JSON 格式计划")
                
                plan_data = json.loads(json_str)
                plan = Plan(**plan_data)
                
                logger.success(f"✅ 计划生成成功，共 {len(plan.tasks)} 个任务")
                logger.info(f"完整计划详情: {json.dumps(plan.model_dump(), indent=2, ensure_ascii=False)}")
                
                # 输出每个任务
                for task in plan.tasks:
                    logger.info(f"  任务 [{task.task_id}]: {task.description}")
                    logger.info(f"    工具: {task.tool}")
                    logger.info(f"    参数: {task.arguments}")
                    logger.info(f"    依赖: {task.depends_on}")
                
                await put_event("plan_ready", f"✅ 计划生成完成，共 {len(plan.tasks)} 个任务")
                
                # 输出每个任务
                for task in plan.tasks:
                    await put_event("task", f"[{task.task_id}] {task.description} (工具: {task.tool})")
                
                state["plan"] = plan
                state["task_results"] = {}
                
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 解析失败: {str(e)}")
                logger.error(f"JSON 解析位置: {e.pos}")
                logger.error(f"原始内容前200字符: {full_content[:200]}")
                await put_event("error", f"JSON 解析失败: {str(e)}")
                state["error"] = f"JSON 解析失败: {str(e)}\n原始内容: {full_content[:200]}"
            except Exception as e:
                logger.error(f"❌ 解析计划失败: {str(e)}")
                import traceback
                logger.error(f"完整错误堆栈: {traceback.format_exc()}")
                await put_event("error", f"解析计划失败: {str(e)}")
                state["error"] = f"解析计划失败: {str(e)}"
        else:
            logger.error("❌ LLM 未返回有效内容")
            await put_event("error", "LLM 未返回有效内容")
            state["error"] = "LLM 未返回有效内容"
        
    except Exception as e:
        logger.error(f"❌ 规划节点错误: {str(e)}")
        import traceback
        logger.error(f"完整错误堆栈: {traceback.format_exc()}")
        await put_event("error", f"规划节点错误: {str(e)}")
        state["error"] = f"规划节点错误: {str(e)}"
    
    return state


async def execution_with_stream(state: PlannerState) -> PlannerState:
    """执行节点: 执行工具调用 (带流式输出)"""
    from tools import get_langchain_tools
    from planner import (
        resolve_task_dependencies, auto_add_dependencies, extract_metric_name
    )
    
    plan = state.get("plan")
    if not plan:
        logger.error("❌ 没有可执行的计划")
        state["error"] = "没有可执行的计划"
        return state
    
    logger.info(f"\n{'='*60}")
    logger.info("⚡ 执行节点 - 开始执行工具调用")
    logger.info(f"{'='*60}")
    logger.info(f"总任务数: {len(plan.tasks)}")
    
    await put_event("phase", f"⚡ 执行阶段 - 开始执行 {len(plan.tasks)} 个任务")
    
    try:
        # 获取 LangChain 工具
        logger.info("开始获取 LangChain 工具...")
        tools = await get_langchain_tools(mcp_client)
        logger.info(f"✅ 成功获取 {len(tools)} 个 LangChain 工具")
        
        # 记录可用工具
        for tool in tools:
            logger.debug(f"  - {tool.name}: {tool.description}")
        
        task_results = state.get("task_results", {})
        executed_tasks = set()
        
        # 预处理：自动分析并添加任务依赖
        logger.info("开始分析任务依赖关系...")
        auto_add_dependencies(plan)
        logger.info("✅ 任务依赖分析完成")
        
        await put_event("info", f"任务依赖分析完成，准备按依赖顺序执行")
        
        # 按依赖顺序执行任务
        while len(executed_tasks) < len(plan.tasks):
            # 找到可以执行的任务
            ready_tasks = [
                task for task in plan.tasks
                if task.task_id not in executed_tasks
                and all(dep in executed_tasks for dep in task.depends_on)
            ]
            
            if not ready_tasks:
                remaining = [t for t in plan.tasks if t.task_id not in executed_tasks]
                state["error"] = f"检测到循环依赖: {[t.task_id for t in remaining]}"
                await put_event("error", state["error"])
                break
            
            # 执行就绪的任务
            for task in ready_tasks:
                logger.info(f"\n{'-'*60}")
                logger.info(f"🔧 开始执行任务 [{task.task_id}]: {task.description}")
                logger.info(f"{'-'*60}")
                logger.info(f"工具: {task.tool}")
                
                await put_event("executing", f"正在执行任务 [{task.task_id}]: {task.description}")
                
                try:
                    # 解析参数中的依赖引用
                    logger.debug("开始解析任务参数中的依赖引用...")
                    resolved_args = resolve_task_dependencies(task_results, plan, task)
                    logger.info(f"✅ 参数解析完成: {resolved_args}")
                    
                    # 显示参数
                    args_str = ", ".join([f"{k}={v}" for k, v in resolved_args.items()])
                    logger.info(f"参数详情: {args_str}")
                    await put_event("info", f"  参数: {args_str}")
                    
                    # 特殊处理：query_sales_summary_detail 需要查询 metric_name
                    if task.tool == "query_sales_summary_detail":
                        metric_name_input = resolved_args.get("metric_name", "")
                        if isinstance(metric_name_input, str) and not metric_name_input.startswith("${"):
                            logger.info(f"🔍 需要查询指标: {metric_name_input}")
                            await put_event("info", f"  自动调用 search_metrics 查询指标: {metric_name_input}")
                            search_tool = next((t for t in tools if t.name == "search_metrics"), None)
                            if search_tool:
                                logger.info(f"调用 search_metrics 工具...")
                                search_result = await search_tool.ainvoke({
                                    "value": metric_name_input,
                                    "column_name": "metric_name_cn",
                                    "n_results": 1
                                })
                                logger.info(f"search_metrics 结果: {search_result}")
                                resolved_args["metric_name"] = extract_metric_name(str(search_result)) or metric_name_input
                                logger.info(f"✅ 解析到 metric_name: {resolved_args['metric_name']}")
                                await put_event("info", f"  解析到 metric_name: {resolved_args['metric_name']}")
                    
                    # 找到对应的工具
                    logger.info(f"查找工具: {task.tool}")
                    tool = next((t for t in tools if t.name == task.tool), None)
                    if not tool:
                        logger.error(f"❌ 工具未找到: {task.tool}")
                        raise ValueError(f"工具未找到: {task.tool}")
                    
                    # 执行工具
                    logger.info(f"🚀 调用工具 [{task.tool}]...")
                    logger.info(f"工具参数: {resolved_args}")
                    await put_event("info", f"  调用 {task.tool}...")
                    
                    # 记录工具调用开始时间
                    import time
                    start_time = time.time()
                    
                    result = await tool.ainvoke(resolved_args)
                    
                    # 记录工具调用耗时
                    elapsed_time = time.time() - start_time
                    logger.info(f"✅ 工具调用完成，耗时: {elapsed_time:.2f} 秒")
                    
                    task.status = "completed"
                    task.result = result
                    task_results[task.task_id] = result
                    
                    logger.success(f"✅ 任务 [{task.task_id}] 完成")
                    logger.info(f"完整结果: {result}")
                    await put_event("complete", f"✅ 任务 [{task.task_id}] 完成")
                
                except Exception as e:
                    logger.error(f"❌ 任务 [{task.task_id}] 执行失败: {str(e)}")
                    import traceback
                    logger.error(f"完整错误堆栈: {traceback.format_exc()}")
                    await put_event("error", f"❌ 任务 [{task.task_id}] 失败: {str(e)}")
                    task.status = "failed"
                    task.error = str(e)
                    task_results[task.task_id] = {"error": str(e)}
                
                executed_tasks.add(task.task_id)
        
        state["task_results"] = task_results
        
        logger.success(f"\n{'='*60}")
        logger.success(f"✅ 所有任务执行完成，共 {len(executed_tasks)} 个任务")
        logger.success(f"{'='*60}\n")
        
    except Exception as e:
        logger.error(f"❌ 执行节点错误: {str(e)}")
        import traceback
        logger.error(f"完整错误堆栈: {traceback.format_exc()}")
        await put_event("error", f"执行节点错误: {str(e)}")
        state["error"] = f"执行节点错误: {str(e)}"
    
    return state


async def final_answer_with_stream(state: PlannerState) -> PlannerState:
    """最终答案节点: 汇总所有任务结果生成最终答案 (带流式输出)"""
    from planner import get_llm
    
    plan = state.get("plan")
    task_results = state.get("task_results", {})
    
    logger.info(f"\n{'='*60}")
    logger.info("💡 最终答案节点 - 生成答案...")
    logger.info(f"{'='*60}")
    logger.info("\n📊 任务执行摘要:")
    for task in plan.tasks:
        logger.info(f"  - 任务 {task.task_id}: {task.status}")
    
    await put_event("phase", "💡 最终答案阶段 - 正在生成答案...")
    
    # 构建结果摘要
    summary = []
    for task in plan.tasks:
        summary.append(f"任务 {task.task_id} ({task.description}):")
        summary.append(f"  状态: {task.status}")
        if task.result:
            summary.append(f"  结果: {task.result}")
        if task.error:
            summary.append(f"  错误: {task.error}")
    
    summary_text = "\n".join(summary)
    
    try:
        llm = get_llm(temperature=0.3)
        user_input = state.get("user_input", "")
        
        logger.info(f"LLM 配置: temperature=0.3, model={os.getenv('OPENAI_MODEL', 'gpt-4')}")
        logger.info(f"用户原始问题: {user_input}")
        logger.info(f"完整任务摘要:\n{summary_text}")
        
        await put_event("info", "正在调用 LLM 生成最终答案...")
        
        logger.info("\n🚀 开始调用 LLM (最终答案节点)...")
        logger.info(f"{'-'*60}")
        
        messages = [
            {"role": "system", "content": "请根据所有子任务的执行结果,生成最终答案。要求简洁明了,包含关键信息。"},
            {"role": "user", "content": f"用户原始问题: {user_input}\n\n根据任务执行摘要,请生成用户想要了解的最终答案。\n\n任务执行摘要:\n{summary_text}"}
        ]
        
        # 使用流式输出生成答案
        full_content = ""
        chunk_count = 0
        async for chunk in llm.astream(messages):
            if hasattr(chunk, 'content') and chunk.content:
                content = chunk.content
                full_content += content
                chunk_count += 1
                # 实时输出每个字符
                await put_event("answer_chunk", content)
        
        logger.info(f"{'-'*60}")
        logger.success(f"✅ LLM 响应完成，共 {chunk_count} 个 chunk，总长度: {len(full_content)} 字符")
        logger.info(f"完整最终答案:\n{full_content}")
        
        await put_event("info", f"答案生成完成，共 {len(full_content)} 字符")
        
        state["final_answer"] = full_content
        
        logger.success(f"\n{'='*60}")
        logger.success("✅ 最终答案生成完成")
        logger.success(f"完整最终答案:\n{full_content}")
        logger.success(f"{'='*60}\n")
        
    except Exception as e:
        logger.error(f"❌ 生成最终答案时出错: {str(e)}")
        import traceback
        logger.error(f"完整错误堆栈: {traceback.format_exc()}")
        await put_event("error", f"生成最终答案时出错: {str(e)}")
        state["final_answer"] = f"生成最终答案时出错: {str(e)}\n\n任务摘要:\n{summary_text}"
    
    return state


def should_execute(state: PlannerState) -> str:
    """条件边: 判断是否应该执行任务"""
    if state.get("error"):
        return "end"
    if not state.get("plan"):
        return "end"
    return "execute"


def create_planner_graph():
    """创建 Planner 主图 (内联实现)"""
    from langgraph.graph import StateGraph, END
    
    workflow = StateGraph(PlannerState)
    
    # 添加节点
    workflow.add_node("planning", planning_with_stream)
    workflow.add_node("execution", execution_with_stream)
    workflow.add_node("final_answer", final_answer_with_stream)
    
    # 设置入口
    workflow.set_entry_point("planning")
    
    # 添加边
    workflow.add_conditional_edges(
        "planning",
        should_execute,
        {
            "execute": "execution",
            "end": END
        }
    )
    
    workflow.add_edge("execution", "final_answer")
    workflow.add_edge("final_answer", END)
    
    return workflow.compile()


# 全局变量存储图实例
planner_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时初始化 MCP 连接,关闭时清理
    """
    global planner_graph, event_queue
    
    # 初始化事件队列
    event_queue = asyncio.Queue()
    
    # 启动时初始化
    log_step("FastAPI 服务", "启动中...")
    
    # 连接 MCP 服务器
    server_params = StdioServerParameters(
        command=os.getenv("MCP_SERVER_COMMAND", "python"),
        args=[os.getenv("MCP_SERVER_ARGS", "mcp_server.py")],
        env=None
    )
    
    try:
        await mcp_client.connect(server_params)
        log_step("FastAPI 服务", "✅ MCP 服务器连接成功")
    except Exception as e:
        log_step("FastAPI 服务", f"❌ MCP 服务器连接失败: {str(e)}")
        raise
    
    # 创建主图
    try:
        planner_graph = create_planner_graph()
        log_step("FastAPI 服务", "✅ Planner 主图构建完成")
    except Exception as e:
        log_step("FastAPI 服务", f"❌ 主图构建失败: {str(e)}")
        raise
    
    log_step("FastAPI 服务", "✅ 服务启动成功")
    
    yield
    
    # 关闭时清理
    log_step("FastAPI 服务", "关闭中...")
    await mcp_client.close()
    log_step("FastAPI 服务", "✅ 资源清理完成")


# 创建 FastAPI 应用
app = FastAPI(
    title="LangGraph MCP Agent API",
    description="基于 LangGraph 和 MCP 的智能代理系统的 HTTP 服务",
    version="1.0.0",
    lifespan=lifespan
)


# ============= 请求/响应模型 =============

class ChatRequest(BaseModel):
    """聊天请求模型"""
    user_input: str


class TaskInfo(BaseModel):
    """任务信息模型"""
    task_id: str
    description: str
    tool: str
    status: str
    result: Optional[str] = None
    error: Optional[str] = None


class ChatResponse(BaseModel):
    """聊天响应模型"""
    success: bool
    final_answer: str = ""
    tasks: list[TaskInfo] = []
    error: Optional[str] = None


# ============= API 端点 =============

@app.get("/")
async def root():
    """根路径健康检查"""
    return {"status": "ok", "message": "LangGraph MCP Agent API 服务运行中"}


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    聊天接口
    
    接收用户输入,执行任务并返回结果
    """
    global planner_graph
    
    logger.info(f"\n{'='*60}")
    logger.info("📥 收到新的 API 请求")
    logger.info(f"{'='*60}")
    logger.info(f"端点: /chat")
    logger.info(f"用户输入: {request.user_input}")
    logger.info(f"{'='*60}\n")
    
    if not request.user_input or not request.user_input.strip():
        logger.warning("❌ 用户输入为空")
        raise HTTPException(status_code=400, detail="user_input 不能为空")
    
    if planner_graph is None:
        logger.error("❌ 服务未完全初始化")
        raise HTTPException(status_code=503, detail="服务未完全初始化,请稍后再试")
    
    log_step("API 请求", f"用户输入: {request.user_input}")
    
    # 构建初始状态
    initial_state: PlannerState = {
        "user_input": request.user_input,
        "plan": None,
        "task_results": {},
        "final_answer": "",
        "error": None
    }
    
    try:
        logger.info("开始执行主图...")
        # 执行主图
        final_state = await planner_graph.ainvoke(initial_state)
        
        logger.info("主图执行完成，开始构建响应...")
        
        # 构建响应
        tasks = []
        if final_state.get("plan"):
            for task in final_state["plan"].tasks:
                tasks.append(TaskInfo(
                    task_id=task.task_id,
                    description=task.description,
                    tool=task.tool,
                    status=task.status,
                    result=str(task.result) if task.result else None,
                    error=task.error
                ))
        
        if final_state.get("error"):
            logger.error(f"❌ 执行失败: {final_state['error']}")
            return ChatResponse(
                success=False,
                error=final_state["error"],
                tasks=tasks
            )
        
        logger.success(f"✅ 请求处理成功，最终答案长度: {len(final_state.get('final_answer', ''))} 字符")
        logger.info(f"任务数量: {len(tasks)}")
        
        return ChatResponse(
            success=True,
            final_answer=final_state.get("final_answer", ""),
            tasks=tasks
        )
        
    except Exception as e:
        logger.error(f"❌ API 错误: {str(e)}")
        import traceback
        logger.error(f"完整错误堆栈: {traceback.format_exc()}")
        log_step("API 错误", str(e))
        log_step("API 错误堆栈", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


async def event_generator(request: ChatRequest) -> AsyncGenerator[str, None]:
    """
    流式事件生成器
    从事件队列中实时读取执行进度并输出
    """
    global planner_graph, event_queue
    
    if not request.user_input or not request.user_input.strip():
        yield json.dumps({"type": "error", "content": "user_input 不能为空"}, ensure_ascii=False) + "\n"
        return
    
    if planner_graph is None:
        yield json.dumps({"type": "error", "content": "服务未完全初始化，请稍后再试"}, ensure_ascii=False) + "\n"
        return
    
    # 清空队列
    await clear_events()
    
    # 发送开始信号
    yield json.dumps({"type": "start", "content": f"🚀 开始处理: {request.user_input}"}, ensure_ascii=False) + "\n"
    
    # 构建初始状态
    initial_state: PlannerState = {
        "user_input": request.user_input,
        "plan": None,
        "task_results": {},
        "final_answer": "",
        "error": None
    }
    
    full_answer = ""
    
    try:
        # 在后台启动执行任务
        async def run_graph():
            nonlocal full_answer
            try:
                async for chunk in planner_graph.astream(initial_state):
                    # 节点完成后，全局状态已经更新，可以从事件队列读取
                    pass
            except Exception as e:
                await event_queue.put({"type": "error", "content": f"执行错误: {str(e)}"})
        
        # 启动后台任务
        task = asyncio.create_task(run_graph())
        
        # 实时读取事件队列
        while True:
            try:
                # 等待事件，带超时以支持取消
                event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                
                event_type = event.get("type", "info")
                content = event.get("content", "")
                
                if event_type == "answer_chunk":
                    # 增量输出答案
                    full_answer += content
                    yield json.dumps({"type": "answer", "content": content}, ensure_ascii=False) + "\n"
                elif event_type == "done":
                    break
                elif event_type == "error":
                    yield json.dumps({"type": "error", "content": content}, ensure_ascii=False) + "\n"
                    task.cancel()
                    return
                else:
                    yield json.dumps({"type": event_type, "content": content}, ensure_ascii=False) + "\n"
                
            except asyncio.TimeoutError:
                # 超时，检查任务是否完成
                if task.done():
                    break
                continue
        
        # 等待任务完成
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # 发送完成信号
        yield json.dumps({"type": "done", "content": f"✅ 处理完成，最终答案长度: {len(full_answer)} 字符"}, ensure_ascii=False) + "\n"
        
    except asyncio.CancelledError:
        yield json.dumps({"type": "error", "content": "连接已取消"}, ensure_ascii=False) + "\n"
    except Exception as e:
        import traceback
        log_step("流式错误", str(e))
        yield json.dumps({"type": "error", "content": f"执行失败: {str(e)}"}, ensure_ascii=False) + "\n"


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    流式聊天接口
    
    通过 Server-Sent Events 流式输出执行进度和最终结果
    """
    logger.info(f"\n{'='*60}")
    logger.info("📥 收到新的流式 API 请求")
    logger.info(f"{'='*60}")
    logger.info(f"端点: /chat/stream")
    logger.info(f"用户输入: {request.user_input}")
    logger.info(f"{'='*60}\n")
    
    return StreamingResponse(
        event_generator(request),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8898")),
        reload=False
    )
