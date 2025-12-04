"""
状态定义模块
定义主图和子图的状态结构
"""

from typing import TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel, Field


# ============= Pydantic 模型 =============

class Task(BaseModel):
    """单个任务定义"""
    task_id: str = Field(description="任务唯一标识")
    description: str = Field(description="任务描述")
    tool: str = Field(description="使用的工具名称")
    arguments: Dict[str, Any] = Field(description="工具参数")
    depends_on: List[str] = Field(default_factory=list, description="依赖的任务ID列表")
    status: str = Field(default="pending", description="任务状态: pending, running, completed, failed")
    result: Optional[Any] = Field(default=None, description="任务执行结果")
    error: Optional[str] = Field(default=None, description="错误信息")


class Plan(BaseModel):
    """任务计划"""
    tasks: List[Task] = Field(description="任务列表")


class ReflectionResult(BaseModel):
    """反思结果"""
    understanding_correct: bool = Field(description="是否正确理解用户意图")
    tool_appropriate: bool = Field(description="工具选择是否合适")
    parameters_correct: bool = Field(description="参数是否正确")
    suggestions: str = Field(default="", description="改进建议")
    proceed: bool = Field(description="是否继续执行")


# ============= TypedDict 状态 =============

class PlannerState(TypedDict):
    """主图(Planner)状态"""
    user_input: str  # 用户输入
    plan: Optional[Plan]  # 生成的任务计划
    task_results: Dict[str, Any]  # 任务执行结果 {task_id: result}
    final_answer: str  # 最终答案
    error: Optional[str]  # 错误信息


class WorkerState(TypedDict):
    """子图(Worker)状态"""
    task: Task  # 当前任务
    reflection: Optional[ReflectionResult]  # 反思结果
    tool_result: Optional[Any]  # 工具执行结果
    error: Optional[str]  # 错误信息
