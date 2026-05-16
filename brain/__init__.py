"""
brain 包 — 店小二大脑调度器

对包外只暴露核心调度函数：
- dispatch(user_text) → dict    用户文本 → 解析 → 执行 → 返回结果
- get_network_status() → bool   获取大模型连通状态
"""

from .dispatcher import dispatch, get_network_status

__all__ = ["dispatch", "get_network_status"]
