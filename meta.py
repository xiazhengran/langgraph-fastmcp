"""
Prompt 管理模块
统一管理所有系统提示词
"""

from typing import List, Any


# ============= 基础 Prompt 模板 =============

PROMPTS = {
    "planner_system_template": """你是一个智能任务规划助手。你的职责是:
1. 理解用户的需求
2. 将复杂任务分解为多个可执行的子任务
3. 为每个子任务指定合适的工具和参数
4. 考虑任务之间的依赖关系

{tools_description}

请以 JSON 格式返回任务计划,格式如下:
{{
    "tasks": [
        {{
            "task_id": "task_1",
            "description": "任务描述",
            "tool": "工具名称",
            "arguments": {{"参数名": "参数值"}},
            "depends_on": []
        }}
    ]
}}

注意:
- task_id 必须唯一
- depends_on 列出依赖的 task_id
- 可以使用 ${{task_id}} 引用其他任务的结果
""",

    "reflection_system": """你是一个反思助手。在执行工具调用之前,请仔细思考:
1. 是否正确理解了用户的意图?
2. 选择的工具是否合适?
3. 参数是否正确?
4. 是否有更好的执行方案?

请以 JSON 格式返回反思结果:
{
    "understanding_correct": true/false,
    "tool_appropriate": true/false,
    "parameters_correct": true/false,
    "suggestions": "改进建议(如果有)",
    "proceed": true/false
}
""",

    "worker_system": """你是一个任务执行助手。你需要:
1. 接收任务指令
2. 调用相应的工具
3. 返回执行结果

请严格按照任务要求执行,不要偏离目标。
""",

    "final_answer": """请根据所有子任务的执行结果,生成最终答案。
要求:
1. 简洁明了
2. 包含关键信息
3. 如果有错误,说明原因
"""
}


# ============= 工具描述生成 =============

def format_tool_description(tool: Any) -> str:
    """
    格式化单个工具的描述
    
    Args:
        tool: MCP 工具对象
        
    Returns:
        格式化的工具描述字符串
    """
    name = tool.name
    description = tool.description or "无描述"
    
    # 提取参数信息
    params = []
    if hasattr(tool, 'inputSchema') and tool.inputSchema:
        schema = tool.inputSchema
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        
        for param_name, param_info in properties.items():
            param_type = param_info.get('type', 'any')
            param_desc = param_info.get('description', '')
            is_required = '必需' if param_name in required else '可选'
            params.append(f"  - {param_name} ({param_type}, {is_required}): {param_desc}")
    
    params_str = '\n'.join(params) if params else "  无参数"
    
    return f"- {name}: {description}\n{params_str}"


def build_tools_description(tools: List[Any]) -> str:
    """
    构建所有工具的描述文本
    
    Args:
        tools: MCP 工具列表
        
    Returns:
        格式化的工具描述文本
    """
    if not tools:
        return "可用工具:\n暂无可用工具"
    
    tool_descriptions = [format_tool_description(tool) for tool in tools]
    return "可用工具:\n" + "\n\n".join(tool_descriptions)


def build_planner_prompt(tools: List[Any]) -> str:
    """
    动态构建 Planner 的系统 Prompt
    
    Args:
        tools: MCP 工具列表
        
    Returns:
        完整的 Planner 系统 Prompt
    """
    tools_description = build_tools_description(tools)
    return PROMPTS["planner_system_template"].format(tools_description=tools_description)


# ============= Prompt 获取函数 =============

def get_prompt(name: str, **kwargs) -> str:
    """
    获取指定名称的 Prompt
    
    Args:
        name: Prompt 名称
        **kwargs: 格式化参数
        
    Returns:
        Prompt 内容
        
    Raises:
        KeyError: 如果 Prompt 不存在
    """
    if name not in PROMPTS:
        raise KeyError(f"Prompt '{name}' not found. Available prompts: {list(PROMPTS.keys())}")
    
    prompt = PROMPTS[name]
    
    # 如果有格式化参数,进行格式化
    if kwargs:
        return prompt.format(**kwargs)
    
    return prompt
