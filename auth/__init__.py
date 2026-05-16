"""
auth 包 — 店小二登录认证模块

对包外只暴露 login 模块的四个核心函数：
- login(password)            → str    登录验证
- change_password(old, new)  → str    修改密码
- reset_to_default()         → None   恢复默认密码 + 清空业务数据
- get_failed_count()         → int    当前累计失败次数
"""

from .login import login, change_password, reset_to_default, get_failed_count

__all__ = ["login", "change_password", "reset_to_default", "get_failed_count"]
