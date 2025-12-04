"""
主入口模块
初始化 MCP 连接,构建和运行图
"""

import asyncio
import os
from mcp import StdioServerParameters

from states import PlannerState
from planner import create_planner_graph
from worker import mcp_client
from utils import log_step


async def main():
    """主函数"""
    
    print("\n" + "="*60)
    print("🚀 LangGraph + MCP 智能代理系统")
    print("="*60 + "\n")
    
    # 1. 连接 MCP 服务器
    log_step("初始化", "连接 MCP 服务器...")
    
    server_params = StdioServerParameters(
        command=os.getenv("MCP_SERVER_COMMAND", "python"),
        args=[os.getenv("MCP_SERVER_ARGS", "mcp_server.py")],
        env=None
    )
    
    try:
        await mcp_client.connect(server_params)
        log_step("初始化", "✅ MCP 服务器连接成功")
    except Exception as e:
        log_step("初始化", f"❌ MCP 服务器连接失败: {str(e)}")
        return
    
    # 2. 创建主图
    log_step("初始化", "构建 Planner 主图...")
    planner_graph = create_planner_graph()
    log_step("初始化", "✅ 主图构建完成")
    
    # 3. 获取用户输入
    print("\n" + "-"*60)
    user_input = input("请输入您的需求: ").strip()
    print("-"*60 + "\n")
    
    if not user_input:
        print("❌ 输入为空,退出程序")
        await mcp_client.close()
        return
    
    # 4. 执行主图
    initial_state: PlannerState = {
        "user_input": user_input,
        "plan": None,
        "task_results": {},
        "final_answer": "",
        "error": None
    }
    
    try:
        log_step("执行", "开始执行任务...")
        final_state = await planner_graph.ainvoke(initial_state)
        
        # 5. 输出结果
        print("\n" + "="*60)
        print("📊 执行结果")
        print("="*60 + "\n")
        
        if final_state.get("error"):
            print(f"❌ 错误: {final_state['error']}\n")
        else:
            print(f"✅ 最终答案:\n{final_state.get('final_answer', '无')}\n")
        
        # 显示任务详情
        if final_state.get("plan"):
            print("\n" + "-"*60)
            print("📋 任务执行详情")
            print("-"*60 + "\n")
            
            for task in final_state["plan"].tasks:
                print(f"任务 ID: {task.task_id}")
                print(f"描述: {task.description}")
                print(f"工具: {task.tool}")
                print(f"状态: {task.status}")
                if task.result:
                    print(f"结果: {task.result}")
                if task.error:
                    print(f"错误: {task.error}")
                print()
        
    except Exception as e:
        log_step("执行", f"❌ 执行失败: {str(e)}")
    
    finally:
        # 6. 清理资源
        log_step("清理", "关闭 MCP 连接...")
        await mcp_client.close()
        log_step("清理", "✅ 资源清理完成")
    
    print("\n" + "="*60)
    print("👋 程序结束")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
