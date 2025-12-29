import os
import logging
import json
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Union
import mysql.connector
from mysql.connector import pooling, Error
from mysql.connector.pooling import MySQLConnectionPool
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MysqlUtil:
    _instance: Optional['MysqlUtil'] = None
    _pool: Optional[MySQLConnectionPool] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MysqlUtil, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._pool is not None:
            return  # 已初始化

        # 从环境变量读取数据库配置
        config = {
            "host": os.getenv("MYSQL_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_PORT", 3306)),
            "user": os.getenv("MYSQL_USER", "root"),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DATABASE", ""),
            "charset": "utf8mb4",
            "autocommit": False,
            "pool_name": "mypool",
            "pool_size": int(os.getenv("MYSQL_POOL_SIZE", 5)),
            "pool_reset_session": True,
            "connection_timeout": 10,
        }

        try:
            self._pool = pooling.MySQLConnectionPool(**config)
            logger.info("MySQL 连接池初始化成功")
        except Error as e:
            logger.error(f"MySQL 连接池初始化失败: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = None
        try:
            conn = self._pool.get_connection()
            yield conn
        except Error as e:
            if conn:
                conn.rollback()
            logger.error(f"数据库操作出错: {e}")
            raise
        finally:
            if conn and conn.is_connected():
                conn.close()

    def execute(
        self,
        sql: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch: bool = False
    ) -> Optional[Union[List[Dict[str, Any]], int]]:
        """
        执行 SQL 语句

        :param sql: SQL 语句（建议使用参数化查询）
        :param params: 参数（tuple 或 dict）
        :param fetch: 是否返回查询结果
        :return: 查询结果（fetch=True）或影响行数（fetch=False）
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True, buffered=True)
            try:
                cursor.execute(sql, params or ())
                if fetch:
                    result = cursor.fetchall()
                    logger.debug(f"查询返回 {len(result)} 行")
                    return result
                else:
                    rowcount = cursor.rowcount
                    conn.commit()
                    logger.debug(f"执行成功，影响 {rowcount} 行")
                    return rowcount
            except Exception as e:
                conn.rollback()
                logger.error(f"SQL 执行失败: {sql} | 错误: {e}")
                raise
            finally:
                cursor.close()

    def fetch_one(self, sql: str, params: Optional[Union[tuple, dict]] = None) -> Optional[Dict[str, Any]]:
        """获取单条记录"""
        result = self.execute(sql, params, fetch=True)
        return result[0] if result else None

    def fetch_all(self, sql: str, params: Optional[Union[tuple, dict]] = None) -> List[Dict[str, Any]]:
        """获取所有记录"""
        return self.execute(sql, params, fetch=True) or []

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """
        插入单条记录

        :param table: 表名
        :param data: 字段名 -> 值 的字典
        :return: 插入的行 ID（lastrowid）
        """
        columns = list(data.keys())
        placeholders = ["%s"] * len(columns)
        sql = f"INSERT INTO `{table}` ({', '.join(f'`{col}`' for col in columns)}) VALUES ({', '.join(placeholders)})"
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, list(data.values()))
                last_id = cursor.lastrowid
                conn.commit()
                logger.debug(f"插入记录到 {table}，ID: {last_id}")
                return last_id
            except Exception as e:
                conn.rollback()
                logger.error(f"插入失败: {e}")
                raise
            finally:
                cursor.close()

    def update(self, table: str, data: Dict[str, Any], where: str, where_params: tuple = ()) -> int:
        """
        更新记录

        :param table: 表名
        :param data: 要更新的字段
        :param where: WHERE 条件（带占位符）
        :param where_params: WHERE 参数
        :return: 影响行数
        """
        set_clause = ", ".join(f"`{k}` = %s" for k in data.keys())
        sql = f"UPDATE `{table}` SET {set_clause} WHERE {where}"
        params = list(data.values()) + list(where_params)
        return self.execute(sql, params)

    def delete(self, table: str, where: str, where_params: tuple = ()) -> int:
        """删除记录"""
        sql = f"DELETE FROM `{table}` WHERE {where}"
        return self.execute(sql, where_params)

    def query_models_val_detail(self, task_id: int, column: str) -> str:
        """
        查询models_val_detail表中指定task_id的数据
        columns: 指定要查询的字段   
        返回 JSON 字符串格式
        """
        sql = "SELECT `" + column + "` FROM `models_val_detail` WHERE `task_id` = %s"
        result = self.fetch_one(sql, (task_id,))
        if result and result[column] is not None:
            return str(result[column])  
        else:
            return "" 
    def query_dws_sales_summary_detail(
        self,
        metric_name: str,
        date: Optional[str] = None,
        province: Optional[str] = None,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        查询dws_sales_summary表明细数据
        
        :param metric_name: 指标字段名（必填），例如 'negative_review_rate_034'
        :param date: 时间/日期（选填），支持以下格式：
            - 单个日期：'2024-01-01'
            - 年月：'2024-01' 或 '2024-01:01' (查询该月)
            - 日期范围：'2024-01-01:2024-01-31' (使用冒号分隔)
        :param province: 省份（选填）
        :param city: 城市（选填）
        :return: 查询结果列表，每条记录为一个字典
        """
        # 构建 SELECT 字段：包含维度字段和指标字段
        select_fields = [
            "stat_date",
            "country",
            "province",
            "city",
            f"`{metric_name}`"
        ]
        select_clause = ", ".join(select_fields)
        
        # 构建 WHERE 条件
        conditions = []
        params = []
        
        # 处理日期参数（注意：字段名是 stat_date）
        if date is not None:
            if ':' in date:
                # 处理日期范围
                date_parts = date.split(':')
                if len(date_parts) == 2:
                    # 检查是否是年月格式，如 '2024-01:01'
                    if date_parts[0].count('-') == 1 and date_parts[1].count('-') == 1:
                        # 格式：'2024-01:01' 表示某年某月
                        year = date_parts[0].split('-')[0]
                        month = date_parts[1].split('-')[0]
                        start_date = f"{year}-{month}-01"
                        # 获取该月最后一天
                        from datetime import datetime
                        import calendar
                        last_day = calendar.monthrange(int(year), int(month))[1]
                        end_date = f"{year}-{month}-{last_day:02d}"
                        conditions.append("`stat_date` BETWEEN %s AND %s")
                        params.extend([start_date, end_date])
                    else:
                        # 标准日期范围格式：'2024-01-01:2024-01-31'
                        start_date, end_date = date_parts
                        conditions.append("`stat_date` BETWEEN %s AND %s")
                        params.extend([start_date, end_date])
                else:
                    raise ValueError(f"无效的日期范围格式: {date}")
            elif date.count('-') == 1:
                # 格式：'2024-01' 表示某年某月
                year, month = date.split('-')
                start_date = f"{year}-{month}-01"
                # 获取该月最后一天
                from datetime import datetime
                import calendar
                last_day = calendar.monthrange(int(year), int(month))[1]
                end_date = f"{year}-{month}-{last_day:02d}"
                conditions.append("`stat_date` BETWEEN %s AND %s")
                params.extend([start_date, end_date])
            else:
                # 单个日期格式：'2024-01-01'
                conditions.append("`stat_date` = %s")
                params.append(date)
        
        if province is not None:
            conditions.append("`province` = %s")
            params.append(province)
        
        if city is not None:
            conditions.append("`city` = %s")
            params.append(city)
        
        # 构建 WHERE 子句
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # 构建 SQL 查询
        sql = f"SELECT {select_clause} FROM `agent_project`.`dws_sales_summary` WHERE {where_clause}"
        
        logger.info(f"查询dws_sales_summary表: metric_field={metric_name}, date={date}, province={province}, city={city}")
        
        return self.fetch_all(sql, tuple(params))
    


# 全局实例（单例）
mysql_util = MysqlUtil()
