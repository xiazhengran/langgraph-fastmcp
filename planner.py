"""
Planner 主图模块
使用 LangChain 工具绑定和 LangGraph ToolNode
"""

import json
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from states import PlannerState, Plan, Task
from utils import get_llm, log_step
from meta import build_planner_prompt
from worker import mcp_client
from tools import get_langchain_tools


# ============= 节点函数 =============

async def planning_node(state: PlannerState) -> PlannerState:
    """
    规划节点: 生成 JSON 格式的任务计划
    """
    user_input = state["user_input"]
    
    print("\n" + "="*60)
    print("📋 规划节点 - 开始思考...")
    print("="*60)
    print(f"用户输入: {user_input}\n")
    print("🤔 LLM 思考过程:")
    print("-"*60)
    
    try:
        # 获取 MCP 工具用于生成描述
        mcp_tools = await mcp_client.list_tools()
        log_step("获取工具列表", f"共 {len(mcp_tools)} 个工具")
        
        # 打印工具信息用于调试
        for tool in mcp_tools:
            log_step(f"工具: {tool.name}", {
                "description": tool.description if hasattr(tool, 'description') else "无描述"
            })
        
        # 生成包含工具信息的 prompt
        planner_prompt = build_planner_prompt(mcp_tools)
        
        log_step("Planner Prompt", planner_prompt[:500] + "...")  # 只打印前500字符
        
        # 不使用 bind_tools,让 LLM 返回 JSON 格式的计划
        llm = get_llm(temperature=0.7)
        
        # 调用 LLM 生成计划
        messages = [
            {"role": "system", "content": planner_prompt},
            {"role": "user", "content": user_input}
        ]
        
        print("\n🚀 开始调用 LLM...")
        
        # 使用流式输出
        full_content = ""
        async for chunk in llm.astream(messages):
            if hasattr(chunk, 'content') and chunk.content:
                print(chunk.content, end='', flush=True)
                full_content += chunk.content
        
        print("\n")  # 换行
        
        # 直接使用收集到的完整内容
        content = full_content
        log_step("LLM 响应", f"完整内容长度: {len(content)} 字符")
        
        # 解析响应
        if content:
            log_step("LLM 返回内容", content[:1000])  # 打印前1000字符
            
            # 尝试解析 JSON 格式的计划
            try:
                import re
                
                # 提取 JSON
                if "```json" in content:
                    start = content.find("```json") + 7
                    end = content.find("```", start)
                    json_str = content[start:end].strip()
                elif "```" in content:
                    start = content.find("```") + 3
                    end = content.find("```", start)
                    json_str = content[start:end].strip()
                else:
                    # 尝试直接解析整个内容
                    json_str = content.strip()
                
                log_step("提取的 JSON", json_str)
                
                plan_data = json.loads(json_str)
                plan = Plan(**plan_data)
                
                log_step("生成的计划", plan.model_dump())
                
                state["plan"] = plan
                state["task_results"] = {}
                
            except json.JSONDecodeError as e:
                log_step("JSON 解析错误", f"位置: {e.pos}, 消息: {e.msg}")
                log_step("原始内容", content)
                state["error"] = f"JSON 解析失败: {str(e)}\n原始内容: {content[:200]}"
            except Exception as e:
                log_step("解析计划失败", f"错误类型: {type(e).__name__}, 消息: {str(e)}")
                import traceback
                log_step("完整错误堆栈", traceback.format_exc())
                state["error"] = f"解析计划失败: {str(e)}"
        else:
            log_step("LLM 响应异常", "内容为空")
            state["error"] = "LLM 未返回有效内容"
        
    except Exception as e:
        log_step("规划节点错误", f"错误类型: {type(e).__name__}")
        log_step("错误消息", str(e))
        import traceback
        log_step("完整错误堆栈", traceback.format_exc())
        state["error"] = f"规划节点错误: {str(e)}"
    
    return state


# ============= 辅助函数 =============

def extract_metric_name(search_result: str) -> str | None:
    """从 search_metrics 的 JSON 结果中提取 metric_name"""
    try:
        import json
        data = json.loads(search_result)
        if "results" in data and len(data["results"]) > 0:
            first_result = data["results"][0]
            if "metric_name" in first_result:
                return first_result["metric_name"]
        return None
    except Exception as e:
        log_step("解析 metric_name 失败", str(e))
        return None


def extract_field_from_result(result: str, field: str) -> Any:
    """从任务结果中提取指定字段"""
    try:
        import json
        data = json.loads(result)
        if "results" in data and len(data["results"]) > 0:
            first_result = data["results"][0]
            if field in first_result:
                return first_result[field]
        return result
    except Exception:
        return result


def resolve_task_dependencies(task_results: dict[str, Any], plan: Plan, task: Task) -> dict[str, Any]:
    """
    解析任务参数中的依赖引用，将 ${task_id} 或 ${task_id.field} 格式替换为实际值
    
    Args:
        task_results: 已执行任务的结果字典
        plan: 任务计划
        task: 当前任务
    
    Returns:
        resolved_args: 解析后的参数字典
    """
    resolved_args = {}
    
    for key, value in task.arguments.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            ref_expr = value[2:-1]
            
            # 支持两种格式：${task_id} 和 ${task_id.field}
            if '.' in ref_expr:
                # 格式：${task_id.field}
                ref_task_id, ref_field = ref_expr.split('.', 1)
                if ref_task_id not in task_results:
                    raise ValueError(f"Task dependency not found: {ref_task_id}")
                
                ref_result = task_results[ref_task_id]
                ref_task_obj = next((t for t in plan.tasks if t.task_id == ref_task_id), None)
                
                # 如果依赖的是 search_metrics 且指定了 field，从结果中提取对应字段
                if ref_task_obj and ref_task_obj.tool == "search_metrics":
                    resolved_value = extract_field_from_result(str(ref_result), ref_field)
                    log_step(f"从 {ref_task_id}.{ref_field} 提取值", resolved_value)
                    resolved_args[key] = resolved_value
                else:
                    resolved_args[key] = ref_result
            else:
                # 格式：${task_id}
                ref_task_id = ref_expr
                if ref_task_id not in task_results:
                    raise ValueError(f"Task dependency not found: {ref_task_id}")
                
                ref_result = task_results[ref_task_id]
                ref_task = next((t for t in plan.tasks if t.task_id == ref_task_id), None)
                
                # 如果依赖的是 search_metrics 结果，自动提取 metric_name
                if ref_task and ref_task.tool == "search_metrics":
                    metric_name = extract_metric_name(str(ref_result))
                    if metric_name:
                        resolved_args[key] = metric_name
                        log_step(f"从 {ref_task_id} 提取 metric_name", metric_name)
                    else:
                        resolved_args[key] = ref_result
                else:
                    resolved_args[key] = ref_result
        else:
            resolved_args[key] = value
    
    return resolved_args


def auto_add_dependencies(plan: Plan) -> None:
    """
    预处理：分析任务参数中的依赖引用，自动添加到 depends_on
    
    Args:
        plan: 任务计划
    """
    for task in plan.tasks:
        for value in task.arguments.values():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                ref_expr = value[2:-1]
                ref_task_id = ref_expr.split('.')[0]
                if ref_task_id != task.task_id and ref_task_id not in task.depends_on:
                    task.depends_on.append(ref_task_id)
                    log_step(f"自动添加依赖", f"{task.task_id} -> {ref_task_id}")


async def ensure_search_metrics(tools: list, metric_input: str) -> str:
    """
    确保 search_metrics 已执行，返回 metric_name
    
    Args:
        tools: 可用的工具列表
        metric_input: 指标输入值
    
    Returns:
        metric_name: 提取的 metric_name
    """
    search_tool = next((t for t in tools if t.name == "search_metrics"), None)
    if not search_tool:
        log_step("search_metrics 工具未找到", "使用原始输入")
        return metric_input
    
    log_step("执行 search_metrics", f"查询指标: {metric_input}")
    search_result = await search_tool.ainvoke({
        "value": metric_input,
        "column_name": "metric_name_cn",
        "n_results": 1
    })
    log_step("search_metrics 结果", search_result)
    
    metric_name = extract_metric_name(str(search_result))
    if metric_name:
        log_step("提取 metric_name", f"{metric_input} -> {metric_name}")
        return metric_name
    else:
        log_step("未找到匹配的 metric_name", f"使用原始输入: {metric_input}")
        return metric_input


# ============= 节点函数 =============

async def execution_node(state: PlannerState) -> PlannerState:
    """
    执行节点: 使用 ToolNode 执行工具调用
    智能处理 search_metrics 和 query_sales_summary_detail 的依赖关系
    """
    plan = state.get("plan")
    if not plan:
        state["error"] = "没有可执行的计划"
        return state
    
    log_step("执行节点", f"共 {len(plan.tasks)} 个任务")
    
    try:
        # 获取 LangChain 工具
        tools = await get_langchain_tools(mcp_client)
        
        task_results = state.get("task_results", {})
        executed_tasks = set()
        
        # 预处理：自动分析并添加任务依赖
        auto_add_dependencies(plan)
        
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
                state["error"] = f"检测到循环依赖或无法满足的依赖: {[t.task_id for t in remaining]}"
                break
            
            # 执行就绪的任务
            for task in ready_tasks:
                log_step(f"执行任务 {task.task_id}", {
                    "description": task.description,
                    "tool": task.tool,
                    "arguments": task.arguments
                })
                
                try:
                    # 解析参数中的依赖引用
                    resolved_args = resolve_task_dependencies(task_results, plan, task)
                    
                    # 特殊处理：query_sales_summary_detail 需要查询 metric_name
                    if task.tool == "query_sales_summary_detail":
                        metric_name_input = resolved_args.get("metric_name", "")
                        if isinstance(metric_name_input, str) and not metric_name_input.startswith("${"):
                            log_step("自动调用 search_metrics", f"需要查询指标: {metric_name_input}")
                            resolved_args["metric_name"] = await ensure_search_metrics(tools, metric_name_input)
                    
                    # 找到对应的工具
                    tool = next((t for t in tools if t.name == task.tool), None)
                    if not tool:
                        raise ValueError(f"Tool not found: {task.tool}")
                    
                    # 执行工具
                    result = await tool.ainvoke(resolved_args)
                    
                    task.status = "completed"
                    task.result = result
                    task_results[task.task_id] = result
                    
                    log_step(f"任务 {task.task_id} 完成", {
                        "status": task.status,
                        "result": result
                    })
                    
                except Exception as e:
                    log_step(f"任务 {task.task_id} 错误", str(e))
                    import traceback
                    log_step("错误堆栈", traceback.format_exc())
                    task.status = "failed"
                    task.error = str(e)
                    task_results[task.task_id] = {"error": str(e)}
                
                executed_tasks.add(task.task_id)
        
        state["task_results"] = task_results
        
    except Exception as e:
        log_step("执行节点错误", str(e))
        import traceback
        log_step("完整错误堆栈", traceback.format_exc())
        state["error"] = f"执行节点错误: {str(e)}"
    
    return state


async def final_answer_node(state: PlannerState) -> PlannerState:
    """
    最终答案节点: 汇总所有任务结果生成最终答案
    """
    plan = state.get("plan")
    task_results = state.get("task_results", {})
    
    print("\n" + "="*60)
    print("💡 最终答案节点 - 生成答案...")
    print("="*60)
    print("\n📊 任务执行摘要:")
    for task in plan.tasks:
        print(f"  - 任务 {task.task_id}: {task.status}")
    
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
        messages = [
            {"role": "system", "content": "请根据所有子任务的执行结果,生成最终答案。要求简洁明了,包含关键信息。"},
            {"role": "user", "content": f"用户原始问题: {user_input}\n\n根据任务执行摘要,请生成用户想要了解的最终答案。\n\n任务执行摘要:\n{summary_text}"}
        ]
        
        print("\n" + "="*60)
        print("🤖 LLM 生成最终答案:")
        print("-"*60)
        
        # 使用流式输出
        full_content = ""
        async for chunk in llm.astream(messages):
            if hasattr(chunk, 'content') and chunk.content:
                print(chunk.content, end='', flush=True)
                full_content += chunk.content
        
        print("\n" + "="*60 + "\n")
        
        state["final_answer"] = full_content
        
    except Exception as e:
        log_step("最终答案节点错误", str(e))
        state["final_answer"] = f"生成最终答案时出错: {str(e)}\n\n任务摘要:\n{summary_text}"
    
    return state


def should_execute(state: PlannerState) -> str:
    """
    条件边: 判断是否应该执行任务
    """
    if state.get("error"):
        return "end"
    if not state.get("plan"):
        return "end"
    return "execute"


# ============= 构建主图 =============

def create_planner_graph() -> StateGraph:
    """
    创建 Planner 主图
    
    流程:
    1. planning_node: 规划任务 (使用 bind_tools)
    2. execution_node: 执行任务 (使用 ToolNode)
    3. final_answer_node: 生成最终答案
    """
    workflow = StateGraph(PlannerState)
    
    # 添加节点
    workflow.add_node("planning", planning_node)
    workflow.add_node("execution", execution_node)
    workflow.add_node("final_answer", final_answer_node)
    
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
