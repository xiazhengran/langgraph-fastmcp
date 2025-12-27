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


async def execution_node(state: PlannerState) -> PlannerState:
    """
    执行节点: 使用 ToolNode 执行工具调用
    """
    plan = state.get("plan")
    if not plan:
        state["error"] = "没有可执行的计划"
        return state
    
    log_step("执行节点", f"共 {len(plan.tasks)} 个任务")
    
    try:
        # 获取 LangChain 工具
        tools = await get_langchain_tools(mcp_client)
        
        # 创建 ToolNode
        tool_node = ToolNode(tools)
        
        task_results = state.get("task_results", {})
        executed_tasks = set()
        
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
                    resolved_args = {}
                    for key, value in task.arguments.items():
                        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                            ref_task_id = value[2:-1]
                            if ref_task_id in task_results:
                                resolved_args[key] = task_results[ref_task_id]
                            else:
                                raise ValueError(f"Task dependency not found: {ref_task_id}")
                        else:
                            resolved_args[key] = value
                    
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
                    task.status = "failed"
                    task.error = str(e)
                    task_results[task.task_id] = {"error": str(e)}
                
                executed_tasks.add(task.task_id)
        
        state["task_results"] = task_results
        
    except Exception as e:
        log_step("执行节点错误", str(e))
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
        messages = [
            {"role": "system", "content": "请根据所有子任务的执行结果,生成最终答案。要求简洁明了,包含关键信息。"},
            {"role": "user", "content": f"任务执行摘要:\n{summary_text}\n\n请生成最终答案。"}
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
