"""
MCP 服务器模块 (FastMCP 实现)
提供工具能力: add, multiply, concat_and_md5_truncate, search_metrics
"""

import hashlib
from typing import List, Dict, Any
from fastmcp import FastMCP
import httpx

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


@mcp.tool()
def search_metrics(
    value: str,
    column_name: str = "metric_name_cn",
    n_results: int = 3
) -> Dict[str, Any]:
    """
    从知识库中检索相关的指标信息
    
    Args:
        value: 搜索的关键词，例如 "用户活跃度"
        column_name: 要搜索的字段名，默认为 "metric_name_cn"（指标中文名）
        n_results: 返回结果数量，默认为 3
        
    Returns:
        包含检索结果的字典，每个结果包含：
        - metric_name: 指标英文名
        - metric_name_cn: 指标中文名
        - description: 描述
        - calculation_method: 计算方法
        - usage_guide: 使用指南
        - source_table: 来源表
        - similarity_score: 相似度得分
    """
    url = "http://localhost:8899/search_by_column_value"
    
    payload = {
        "column_name": column_name,
        "value": value,
        "n_results": n_results
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=180.0
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        return {
            "error": f"HTTP请求失败: {str(e)}",
            "results": []
        }
    except Exception as e:
        return {
            "error": f"检索失败: {str(e)}",
            "results": []
        }


# ============= 服务器启动 =============

if __name__ == "__main__":
    # 运行 MCP 服务器
    mcp.run()
