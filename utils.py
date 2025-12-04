"""
工具函数模块
提供 LLM 初始化、Schema 转换等通用功能
"""

import os
import json
from typing import Dict, Any, List
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage

# 加载环境变量
load_dotenv()


# ============= LangSmith 监控 =============

def setup_langsmith() -> bool:
    """
    设置 LangSmith 监控
    
    Returns:
        是否成功启用 LangSmith
    """
    langsmith_enabled = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
    
    if not langsmith_enabled:
        return False
    
    langsmith_api_key = os.getenv("LANGSMITH_API_KEY", "")
    langsmith_project = os.getenv("LANGSMITH_PROJECT", "langgraph-fastmcp")
    langsmith_endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    
    if not langsmith_api_key or langsmith_api_key == "your-langsmith-api-key-here":
        print("⚠️  LangSmith 追踪已启用但未配置 API Key,监控将不可用")
        return False
    
    # 设置 LangSmith 环境变量
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = langsmith_project
    os.environ["LANGCHAIN_ENDPOINT"] = langsmith_endpoint
    
    print(f"✅ LangSmith 监控已启用")
    print(f"   项目: {langsmith_project}")
    print(f"   端点: {langsmith_endpoint}")
    
    return True


# 自动初始化 LangSmith
_langsmith_enabled = setup_langsmith()


# ============= LLM 初始化 =============

def get_llm(temperature: float = 0.7) -> ChatOpenAI:
    """
    初始化 LLM 客户端
    
    Args:
        temperature: 温度参数
        
    Returns:
        ChatOpenAI 实例
    """
    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "gpt-4")
    
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")
    
    return ChatOpenAI(
        base_url=api_base,
        api_key=api_key,
        model=model,
        temperature=temperature
    )


# ============= 消息处理 =============

def create_messages(system_prompt: str, user_message: str) -> List[BaseMessage]:
    """
    创建消息列表
    
    Args:
        system_prompt: 系统提示词
        user_message: 用户消息
        
    Returns:
        消息列表
    """
    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message)
    ]


def parse_json_response(response: str) -> Dict[str, Any]:
    """
    解析 JSON 响应
    
    Args:
        response: LLM 响应文本
        
    Returns:
        解析后的字典
    """
    try:
        # 尝试直接解析
        return json.loads(response)
    except json.JSONDecodeError:
        # 尝试提取 JSON 代码块
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            json_str = response[start:end].strip()
            return json.loads(json_str)
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            json_str = response[start:end].strip()
            return json.loads(json_str)
        else:
            raise ValueError(f"Failed to parse JSON from response: {response}")


# ============= MCP Schema 转换 =============

def mcp_tool_to_langchain_schema(mcp_tool: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 MCP 工具 Schema 转换为 LangChain 格式
    
    Args:
        mcp_tool: MCP 工具定义
        
    Returns:
        LangChain 工具 Schema
    """
    return {
        "name": mcp_tool.get("name", ""),
        "description": mcp_tool.get("description", ""),
        "parameters": mcp_tool.get("inputSchema", {})
    }


# ============= 任务依赖解析 =============

def resolve_task_dependencies(task_args: Dict[str, Any], task_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    解析任务参数中的依赖引用 (${task_id})
    
    Args:
        task_args: 任务参数
        task_results: 已完成任务的结果
        
    Returns:
        解析后的参数
    """
    resolved_args = {}
    
    for key, value in task_args.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            # 提取引用的 task_id
            ref_task_id = value[2:-1]
            if ref_task_id in task_results:
                resolved_args[key] = task_results[ref_task_id]
            else:
                raise ValueError(f"Task dependency not found: {ref_task_id}")
        else:
            resolved_args[key] = value
    
    return resolved_args


# ============= 日志工具 =============

def log_step(step_name: str, data: Any):
    """
    打印步骤日志
    
    Args:
        step_name: 步骤名称
        data: 数据
    """
    print(f"\n{'='*60}")
    print(f"[{step_name}]")
    print(f"{'='*60}")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(data)
    print(f"{'='*60}\n")
