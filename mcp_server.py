"""
MCP 服务器模块 (FastMCP 实现)
提供工具能力: add, multiply, concat_and_md5_truncate
"""

import hashlib
from fastmcp import FastMCP

from MysqlUtils import mysql_util

# 创建 FastMCP 服务器实例
mcp = FastMCP("langgraph-mcp-tools")


# ============= 工具定义 =============

@mcp.tool()
def add(a: float, b: float) -> float:
    """
    执行两个数字的加法运算
    
    Args:
        a: 第一个加数
        b: 第二个加数
        
    Returns:
        两数之和
    """
    return a + b


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """
    执行两个数字的乘法运算
    
    Args:
        a: 第一个乘数
        b: 第二个乘数
        
    Returns:
        两数之积
    """
    return a * b


@mcp.tool()
def concat_and_md5_truncate(str1: str, str2: str, length: int = 32) -> str:
    """
    拼接两个字符串并返回 MD5 哈希值的前length位
    
    Args:
        str1: 第一个字符串
        str2: 第二个字符串
        length: 返回的结果长度
        
    Returns:
        拼接后字符串的 MD5 哈希值前length位
    """
    concatenated = str1 + str2
    md5_hash = hashlib.md5(concatenated.encode()).hexdigest()
    return md5_hash[:length]

@mcp.tool()
def query_models_val_detail(task_id: int, column: str) -> str:
    """
    从Mysql中获取指定task_id的models_val_detail表中的指定columns字段数据
    
    Args:
        task_id: task_id
        column: 指定要查询的字段   
        
    Returns:
        指定task_id的指定column字段数据
    """

    return mysql_util.query_models_val_detail(task_id, column)


# ============= 服务器启动 =============

if __name__ == "__main__":
    # 运行 MCP 服务器
    mcp.run()
