"""
auth/login.py — 店小二登录认证

规范来源：
- project_start.md 第二节（登录模块）
- sheji_beiwanglu.md 第十一节（防御面子工程）
- 01_PROJECT_CONSTITUTION.md 9.4（无二次确认）

核心行为：
- 首次启动默认密码 123456，检测到默认密码强制修改
- 密码错误累计 3 次退出（调用方收到 "locked_out" 后自行退出）
- 密码存储走 data.db（SHA-256 + 固定盐），本模块不直接操作哈希
- 忘记密码只能重置所有数据（reset_to_default）
"""

import threading

# 默认密码（首次启动使用）
_DEFAULT_PASSWORD = "123456"

# 最大失败次数
_MAX_FAILED_ATTEMPTS = 3

# 模块级失败计数器（线程安全）
_failed_count = 0
_count_lock = threading.Lock()


def login(password: str) -> str:
    """
    登录验证。

    返回值：
    - "ok"            登录成功
    - "must_change"   登录成功但检测到默认密码，必须修改
    - "locked_out"    累计 3 次失败，调用方应退出 App
    - "wrong_password" 密码错误，还有重试机会

    注意：此函数依赖 data.db 已初始化（init_db 已调用）。
    """
    global _failed_count

    with _count_lock:
        if _failed_count >= _MAX_FAILED_ATTEMPTS:
            return "locked_out"

    # 延迟导入，避免循环依赖（data.db 不依赖 auth）
    from data.db import verify_password, set_password, get_setting

    # 首次启动：settings 中无 password_hash → 写入默认密码
    stored_hash = get_setting("password_hash")
    if stored_hash is None:
        set_password(_DEFAULT_PASSWORD)

    # 验证密码
    if not verify_password(password):
        with _count_lock:
            _failed_count += 1
            if _failed_count >= _MAX_FAILED_ATTEMPTS:
                return "locked_out"
        return "wrong_password"  # 调用方可显示剩余次数

    # 密码正确 → 重置失败计数
    with _count_lock:
        _failed_count = 0

    # 检查是否仍为默认密码
    if verify_password(_DEFAULT_PASSWORD):
        return "must_change"

    return "ok"


def change_password(old_password: str, new_password: str) -> str:
    """
    修改密码。

    返回值：
    - "ok"              修改成功
    - "wrong_old"       旧密码不正确
    - "same_password"   新密码与旧密码相同
    - "empty_password"  新密码为空

    注意：首次强制修改时旧密码传入 123456 即可。
    """
    if not new_password or not new_password.strip():
        return "empty_password"

    from data.db import verify_password, set_password

    if not verify_password(old_password):
        return "wrong_old"

    if old_password == new_password:
        return "same_password"

    set_password(new_password)

    # 修改密码后重置失败计数
    global _failed_count
    with _count_lock:
        _failed_count = 0

    return "ok"


def reset_to_default() -> None:
    """
    恢复默认密码并清空所有业务数据。
    用于"忘记密码"场景——只能丢数据，不能找回密码。

    操作：
    1. 删除数据库文件，重新 init_db
    2. 设置默认密码
    3. 重置失败计数
    """
    import os
    from data.db import set_db_path, init_db, set_password, _db_path

    global _failed_count
    with _count_lock:
        _failed_count = 0

    # 删除数据库文件（含 WAL 辅助文件）
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(_db_path + suffix)
        except OSError:
            pass

    # 重建数据库
    init_db()
    set_password(_DEFAULT_PASSWORD)


def get_failed_count() -> int:
    """返回当前累计失败次数（0~3），供 UI 层显示剩余机会。"""
    with _count_lock:
        return _failed_count


# ══════════════════════════════════════════════
# 契约测试（python -m auth.login 直接运行）
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile, sys, os

    # 确保能导入 data.db
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from data.db import set_db_path, init_db

    # 使用临时数据库
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    set_db_path(tmp.name)
    init_db()

    def reset_failed():
        """重置模块级失败计数"""
        global _failed_count
        _failed_count = 0

    passed = 0
    failed_tests = []

    def run_test(name):
        """测试包装器：重置状态 → 执行 → 捕获异常"""
        reset_failed()
        def decorator(fn):
            try:
                fn()
                print(f"  A{name}: PASS")
            except AssertionError as e:
                print(f"  A{name}: FAIL - {e}")
                failed_tests.append(name)
            except Exception as e:
                print(f"  A{name}: ERROR - {e}")
                failed_tests.append(name)
        return decorator

    print("=== auth/login.py 契约测试 ===")

    # ── A1: 首次启动默认密码，强制修改 ──
    @run_test("1")
    def test_A1():
        result = login("123456")
        assert result == "must_change", f"首次登录应返回 must_change，实际: {result}"
        ch = change_password("123456", "mypass999")
        assert ch == "ok", f"修改密码应返回 ok，实际: {ch}"
        result2 = login("mypass999")
        assert result2 == "ok", f"修改后登录应返回 ok，实际: {result2}"

    # ── A2: 错误3次锁定 ──
    @run_test("2")
    def test_A2():
        r1 = login("wrong1")
        assert r1 == "wrong_password"
        r2 = login("wrong2")
        assert r2 == "wrong_password"
        r3 = login("wrong3")
        assert r3 == "locked_out", f"第3次错误应锁定，实际: {r3}"
        r4 = login("mypass999")
        assert r4 == "locked_out", f"锁定后应返回 locked_out，实际: {r4}"

    # ── A3: 修改密码校验 ──
    @run_test("3")
    def test_A3():
        r1 = change_password("wrong", "newpass")
        assert r1 == "wrong_old", f"旧密码错误应返回 wrong_old，实际: {r1}"
        r2 = change_password("mypass999", "mypass999")
        assert r2 == "same_password", f"新旧相同应返回 same_password，实际: {r2}"
        r3 = change_password("mypass999", "")
        assert r3 == "empty_password", f"空密码应返回 empty_password，实际: {r3}"
        r4 = change_password("mypass999", "new_secure_pw")
        assert r4 == "ok"
        result = login("new_secure_pw")
        assert result == "ok"

    # ── A4: 重置恢复默认 ──
    @run_test("4")
    def test_A4():
        reset_to_default()
        result = login("123456")
        assert result == "must_change", f"重置后应触发 must_change，实际: {result}"
        assert get_failed_count() == 0, f"重置后失败计数应为 0，实际: {get_failed_count()}"

    # 统计通过数
    passed = 4 - len(failed_tests)

    # 清理
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(tmp.name + suffix)
        except OSError:
            pass

    print(f"\n{'='*40}")
    if failed_tests:
        print(f"测试结果: {passed}/4 通过，失败项: {failed_tests}")
        sys.exit(1)
    else:
        print(f"全部 {passed}/4 契约测试通过 ✅  auth/login.py 可交付")
    print(f"{'='*40}")
