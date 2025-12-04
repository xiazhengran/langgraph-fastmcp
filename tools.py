"""
工具封装模块
将 MCP 工具封装为 LangChain BaseTool
"""

from typing import Any, Optional, Type, List
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun


class MCPToolWrapper(BaseTool):
    """
    MCP 工具的 LangChain 包装器
    """
    
    mcp_client: Any = Field(exclude=True)  # MCP 客户端实例
    tool_name: str  # MCP 工具名称
    
    class Config:
        arbitrary_types_allowed = True
    
    def _run(
        self,
        *args,
        run_manager: Optional[CallbackManagerForToolRun] = None,
        **kwargs
    ) -> Any:
        """
        同步执行工具(不支持)
        """
        raise NotImplementedError("MCPToolWrapper only supports async execution")
    
    async def _arun(
        self,
        *args,
        run_manager: Optional[CallbackManagerForToolRun] = None,
        **kwargs
    ) -> Any:
        """
        异步执行工具
        """
        # 调用 MCP 客户端执行工具
        result = await self.mcp_client.call_tool(self.tool_name, kwargs)
        return result


def create_pydantic_model_from_schema(tool_name: str, schema: dict) -> Type[BaseModel]:
    """
    从 JSON Schema 创建 Pydantic 模型
    
    Args:
        tool_name: 工具名称
        schema: JSON Schema
        
    Returns:
        Pydantic 模型类
    """
    properties = schema.get('properties', {})
    required = set(schema.get('required', []))
    
    # 构建字段定义
    fields = {}
    for field_name, field_info in properties.items():
        field_type = field_info.get('type', 'string')
        field_desc = field_info.get('description', '')
        
        # 映射 JSON Schema 类型到 Python 类型
        type_mapping = {
            'string': str,
            'number': float,
            'integer': int,
            'boolean': bool,
            'array': list,
            'object': dict
        }
        
        python_type = type_mapping.get(field_type, str)
        
        # 如果不是必需字段,设置为 Optional
        if field_name not in required:
            python_type = Optional[python_type]
            default_value = None
        else:
            default_value = ...
        
        # 创建字段
        fields[field_name] = (python_type, Field(default=default_value, description=field_desc))
    
    # 如果没有字段,创建一个空模型
    if not fields:
        fields['__dummy__'] = (Optional[str], Field(default=None, description='Dummy field'))
    
    # 动态创建 Pydantic 模型
    model_name = f"{tool_name.capitalize()}Input"
    return create_model(model_name, **fields)


def mcp_tool_to_langchain_tool(mcp_tool: Any, mcp_client: Any) -> BaseTool:
    """
    将 MCP 工具转换为 LangChain BaseTool
    
    Args:
        mcp_tool: MCP 工具对象
        mcp_client: MCP 客户端实例
        
    Returns:
        LangChain BaseTool 实例
    """
    tool_name = mcp_tool.name
    description = mcp_tool.description or f"Tool: {tool_name}"
    
    # 从 inputSchema 创建 Pydantic 模型
    input_schema = mcp_tool.inputSchema if hasattr(mcp_tool, 'inputSchema') else {}
    args_schema = create_pydantic_model_from_schema(tool_name, input_schema)
    
    # 创建工具实例
    tool = MCPToolWrapper(
        name=tool_name,
        description=description,
        mcp_client=mcp_client,
        tool_name=tool_name,
        args_schema=args_schema
    )
    
    return tool


async def get_langchain_tools(mcp_client: Any) -> List[BaseTool]:
    """
    从 MCP 客户端获取所有工具并转换为 LangChain BaseTool
    
    Args:
        mcp_client: MCP 客户端实例
        
    Returns:
        LangChain BaseTool 列表
    """
    # 获取 MCP 工具列表
    mcp_tools = await mcp_client.list_tools()
    
    # 转换为 LangChain 工具
    langchain_tools = [
        mcp_tool_to_langchain_tool(mcp_tool, mcp_client)
        for mcp_tool in mcp_tools
    ]
    
    return langchain_tools
