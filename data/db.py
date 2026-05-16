"""
data/db.py — 店小二数据库管家

规范来源：project_start.md 第五节（数据库设计）、第六节第8条（数据库管家）
          10_SUPPLEMENT_RULES.md 第十二条（数据库线程安全）

约束：
- 所有 public 函数必须在 with _db_lock: 内执行 SQL
- 禁止在锁内执行网络请求等长时间 IO
- menu 删除操作只做软删除（is_active=0），不物理删除（sheji_beiwanglu.md 第五章）
- expenses.category 只允许 'cost' / 'expense'（TEST_CONTRACTS.md C3）
- settings.password_hash 存储 SHA-256，不存明文（TEST_CONTRACTS.md C4）
"""

import sqlite3
import threading
import hashlib
import os
from datetime import datetime

# ──────────────────────────────────────────────
# 模块级线程锁（所有数据库操作必须持有此锁）
# ──────────────────────────────────────────────
_db_lock = threading.Lock()

# 数据库文件路径（打包到 Android 后由 app 层传入，此处提供默认值供测试）
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "dianxiaoer.db")
_db_path = _DEFAULT_DB_PATH


def set_db_path(path: str) -> None:
    """由 main.py 在启动时设置真实路径（Android 用 app.user_data_dir）"""
    global _db_path
    _db_path = path


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（每次调用新建连接，线程安全由 _db_lock 保证）"""
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row          # 允许按列名访问
    conn.execute("PRAGMA journal_mode=WAL")  # 提升并发读性能
    conn.execute("PRAGMA foreign_keys=ON")   # 启用外键约束
    return conn


# ══════════════════════════════════════════════
# 初始化：建表
# ══════════════════════════════════════════════

def init_db() -> None:
    """
    初始化数据库，创建全部 6 张表。
    幂等操作（CREATE TABLE IF NOT EXISTS），可重复调用。
    """
    ddl_orders = """
    CREATE TABLE IF NOT EXISTS orders (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        table_num   INTEGER,                          -- 桌号，非桌台场景为 NULL
        customer_id INTEGER REFERENCES customers(id), -- 可为 NULL
        item_name   TEXT    NOT NULL,
        quantity    INTEGER NOT NULL,
        unit_price  REAL    NOT NULL,
        total_price REAL    NOT NULL,
        is_paid     INTEGER NOT NULL DEFAULT 0,       -- 0=未结, 1=已结
        order_time  TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime')),
        paid_time   TIMESTAMP                         -- 结账时间，可为 NULL
    );
    """

    ddl_menu = """
    CREATE TABLE IF NOT EXISTS menu (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name   TEXT    NOT NULL UNIQUE,          -- 品名唯一（TEST_CONTRACTS C2）
        unit_price  REAL    NOT NULL,
        unit        TEXT    NOT NULL DEFAULT '份',    -- 串/份/个/米/斤
        is_active   INTEGER NOT NULL DEFAULT 1        -- 1=在售, 0=停用（软删除）
    );
    """

    ddl_expenses = """
    CREATE TABLE IF NOT EXISTS expenses (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        item         TEXT    NOT NULL,
        amount       REAL    NOT NULL,
        category     TEXT    NOT NULL
                         CHECK(category IN ('cost','expense')),  -- C3 约束
        expense_time TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime')),
        note         TEXT
    );
    """

    ddl_customers = """
    CREATE TABLE IF NOT EXISTS customers (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL,
        phone      TEXT,
        note       TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime'))
    );
    """

    ddl_settings = """
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    );
    """

    ddl_backup_log = """
    CREATE TABLE IF NOT EXISTS backup_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        backup_time TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime')),
        file_hash   TEXT    NOT NULL
    );
    """

    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(ddl_orders)
            conn.execute(ddl_menu)
            conn.execute(ddl_expenses)
            conn.execute(ddl_customers)
            conn.execute(ddl_settings)
            conn.execute(ddl_backup_log)
            conn.commit()
        finally:
            conn.close()


# ══════════════════════════════════════════════
# settings 表（键值对）
# ══════════════════════════════════════════════

def get_setting(key: str) -> str | None:
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()


def set_setting(key: str, value: str) -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value)
            )
            conn.commit()
        finally:
            conn.close()


# ══════════════════════════════════════════════
# 密码管理（SHA-256 + 固定盐）
# ══════════════════════════════════════════════

# 固定盐：不暴露给用户，硬编码在 auth 模块（此处由 db.py 统一管理哈希逻辑）
_PASSWORD_SALT = "dianxiaoer_salt_v1"


def hash_password(plain: str) -> str:
    """返回 SHA-256(盐+密码) 的十六进制字符串"""
    raw = (_PASSWORD_SALT + plain).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def set_password(plain: str) -> None:
    """存储密码哈希（不存明文）"""
    set_setting("password_hash", hash_password(plain))


def verify_password(plain: str) -> bool:
    """验证密码，返回 True/False"""
    stored = get_setting("password_hash")
    if stored is None:
        return False
    return stored == hash_password(plain)


# ══════════════════════════════════════════════
# menu 表
# ══════════════════════════════════════════════

def get_menu_item(item_name: str) -> sqlite3.Row | None:
    """按名称查询在售品类，不存在或已停用返回 None"""
    with _db_lock:
        conn = _get_conn()
        try:
            return conn.execute(
                "SELECT * FROM menu WHERE item_name=? AND is_active=1",
                (item_name,)
            ).fetchone()
        finally:
            conn.close()


def get_all_menu() -> list:
    """返回所有在售品类列表"""
    with _db_lock:
        conn = _get_conn()
        try:
            return conn.execute(
                "SELECT * FROM menu WHERE is_active=1 ORDER BY id"
            ).fetchall()
        finally:
            conn.close()


def add_menu_item(item_name: str, unit_price: float, unit: str = "份") -> int:
    """
    添加新品类，返回新行 id。
    若同名品类已存在（含已停用），则激活并更新价格，不重复插入。
    """
    with _db_lock:
        conn = _get_conn()
        try:
            existing = conn.execute(
                "SELECT id FROM menu WHERE item_name=?", (item_name,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE menu SET unit_price=?, unit=?, is_active=1 WHERE item_name=?",
                    (unit_price, unit, item_name)
                )
                conn.commit()
                return existing["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO menu(item_name,unit_price,unit) VALUES(?,?,?)",
                    (item_name, unit_price, unit)
                )
                conn.commit()
                return cur.lastrowid
        finally:
            conn.close()


def deactivate_menu_item(item_name: str) -> None:
    """软删除品类（is_active=0），保留历史订单引用"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE menu SET is_active=0 WHERE item_name=?", (item_name,)
            )
            conn.commit()
        finally:
            conn.close()


# ══════════════════════════════════════════════
# orders 表
# ══════════════════════════════════════════════

def add_order(
    item_name: str,
    quantity: int,
    unit_price: float,
    table_num: int | None = None,
    customer_id: int | None = None,
) -> int:
    """
    点单落库，立即写入（无确认弹窗，宪法 9.4）。
    返回新行 id。
    """
    total_price = round(quantity * unit_price, 2)
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO orders
                   (table_num, customer_id, item_name, quantity, unit_price, total_price)
                   VALUES (?,?,?,?,?,?)""",
                (table_num, customer_id, item_name, quantity, unit_price, total_price)
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_unpaid_orders(table_num: int | None = None,
                      customer_id: int | None = None) -> list:
    """查询未结订单。可按桌号或客户 id 筛选。"""
    with _db_lock:
        conn = _get_conn()
        try:
            if table_num is not None:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE table_num=? AND is_paid=0 ORDER BY order_time",
                    (table_num,)
                ).fetchall()
            elif customer_id is not None:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE customer_id=? AND is_paid=0 ORDER BY order_time",
                    (customer_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE is_paid=0 ORDER BY order_time"
                ).fetchall()
            return rows
        finally:
            conn.close()


def checkout(table_num: int | None = None,
             customer_id: int | None = None) -> float:
    """
    结账：将对应未结订单全部标记为已结，返回本次结账总价。
    立即落盘，无确认弹窗（宪法 9.4）。
    """
    paid_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            if table_num is not None:
                rows = conn.execute(
                    "SELECT id, total_price FROM orders WHERE table_num=? AND is_paid=0",
                    (table_num,)
                ).fetchall()
                conn.execute(
                    "UPDATE orders SET is_paid=1, paid_time=? WHERE table_num=? AND is_paid=0",
                    (paid_time, table_num)
                )
            elif customer_id is not None:
                rows = conn.execute(
                    "SELECT id, total_price FROM orders WHERE customer_id=? AND is_paid=0",
                    (customer_id,)
                ).fetchall()
                conn.execute(
                    "UPDATE orders SET is_paid=1, paid_time=? WHERE customer_id=? AND is_paid=0",
                    (paid_time, customer_id)
                )
            else:
                rows = []
            conn.commit()
            total = sum(r["total_price"] for r in rows)
            return round(total, 2)
        finally:
            conn.close()


# ══════════════════════════════════════════════
# 查询：销售额
# ══════════════════════════════════════════════

def query_sales(time_range: str = "today") -> float:
    """
    查询已结账销售额。
    time_range: 'today' / 'week' / 'month'
    """
    range_map = {
        "today": "date(order_time)=date('now','localtime')",
        "week":  "date(order_time)>=date('now','localtime','-6 days')",
        "month": "date(order_time)>=date('now','localtime','start of month')",
    }
    condition = range_map.get(time_range, range_map["today"])
    sql = f"SELECT COALESCE(SUM(total_price),0) AS total FROM orders WHERE is_paid=1 AND {condition}"
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(sql).fetchone()
            return round(row["total"], 2)
        finally:
            conn.close()


# ══════════════════════════════════════════════
# expenses 表
# ══════════════════════════════════════════════

def add_expense(item: str, amount: float, category: str, note: str = "") -> int:
    """
    记录支出。category 只允许 'cost'（进货成本）或 'expense'（经营费用）。
    数据库层有 CHECK 约束兜底，此处再做一层 Python 校验。
    """
    if category not in ("cost", "expense"):
        raise ValueError(f"category 必须为 'cost' 或 'expense'，收到: {category!r}")
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO expenses(item,amount,category,note) VALUES(?,?,?,?)",
                (item, amount, category, note)
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


# ══════════════════════════════════════════════
# customers 表
# ══════════════════════════════════════════════

def add_customer(name: str, phone: str = "", note: str = "") -> int:
    """添加客户，返回新行 id"""
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO customers(name,phone,note) VALUES(?,?,?)",
                (name, phone, note)
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_customer_by_name(name: str) -> sqlite3.Row | None:
    with _db_lock:
        conn = _get_conn()
        try:
            return conn.execute(
                "SELECT * FROM customers WHERE name=?", (name,)
            ).fetchone()
        finally:
            conn.close()


def get_customer_by_id(customer_id: int) -> sqlite3.Row | None:
    with _db_lock:
        conn = _get_conn()
        try:
            return conn.execute(
                "SELECT * FROM customers WHERE id=?", (customer_id,)
            ).fetchone()
        finally:
            conn.close()


# ══════════════════════════════════════════════
# backup_log 表
# ══════════════════════════════════════════════

def add_backup_log(file_hash: str) -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO backup_log(file_hash) VALUES(?)", (file_hash,)
            )
            conn.commit()
        finally:
            conn.close()


# ══════════════════════════════════════════════
# 试用期检查
# ══════════════════════════════════════════════

def is_trial_expired() -> bool:
    """
    检查试用期是否到期。
    trial_end_date 为空 → 正式授权，永不过期。
    trial_end_date 有值 → 与今日比较。
    """
    end_date = get_setting("trial_end_date")
    if not end_date:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    return today > end_date


# ══════════════════════════════════════════════
# 模块自测（python data/db.py 直接运行）
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile, sys

    # 使用临时文件，不污染正式数据库
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    set_db_path(tmp.name)

    print("=== 初始化数据库 ===")
    init_db()
    print("init_db() 完成")

    print("\n=== C1: orders 表字段完整性 ===")
    conn = sqlite3.connect(tmp.name)
    conn.row_factory = sqlite3.Row
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
    required = {"id","table_num","customer_id","item_name","quantity",
                "unit_price","total_price","is_paid","order_time","paid_time"}
    missing = required - cols
    if missing:
        print(f"  ❌ 缺少字段: {missing}")
        sys.exit(1)
    else:
        print(f"  ✅ 全部字段存在: {required}")

    print("\n=== C2: menu 表 item_name 唯一性 ===")
    add_menu_item("羊肉串", 3.0, "串")
    # 直接用底层连接验证 UNIQUE 约束（不经过 add_menu_item 的软删除逻辑）
    try:
        _raw = sqlite3.connect(tmp.name)
        _raw.execute("INSERT INTO menu(item_name,unit_price,unit) VALUES(?,?,?)",
                     ("羊肉串", 3.0, "串"))
        _raw.commit()
        _raw.close()
        print("  ❌ 重名插入未被拒绝")
        sys.exit(1)
    except sqlite3.IntegrityError:
        _raw.close()
        print("  ✅ 重名插入被数据库拒绝")

    print("\n=== C3: expenses category 约束 ===")
    add_expense("测试成本", 100, "cost")
    # Python 层约束
    try:
        add_expense("非法类别", 50, "other")
        print("  ❌ 非法 category 未被 Python 层拒绝")
        sys.exit(1)
    except ValueError as e:
        print(f"  ✅ Python 层拒绝: {e}")
    # SQL CHECK 约束（用独立连接，不经过 _db_lock）
    try:
        _raw2 = sqlite3.connect(tmp.name)
        _raw2.execute("INSERT INTO expenses(item,amount,category) VALUES(?,?,?)",
                      ("SQL层测试", 50, "other"))
        _raw2.commit()
        _raw2.close()
        print("  ❌ SQL CHECK 约束未生效")
        sys.exit(1)
    except sqlite3.IntegrityError:
        _raw2.close()
        print("  ✅ SQL CHECK 约束生效，数据库层也拒绝")

    print("\n=== C4: 密码 SHA-256 存储，无明文 ===")
    set_password("123456")
    stored = get_setting("password_hash")
    if stored == "123456":
        print("  ❌ 密码以明文存储！")
        sys.exit(1)
    if len(stored) != 64:
        print(f"  ❌ 哈希长度异常: {len(stored)}")
        sys.exit(1)
    print(f"  ✅ 密码已哈希存储: {stored[:16]}...")
    assert verify_password("123456") is True
    assert verify_password("wrong") is False
    print("  ✅ verify_password() 验证正确")

    print("\n=== 点单/结账基本流程 ===")
    add_order("羊肉串", 30, 3.0, table_num=3)
    add_order("肉筋", 15, 2.0, table_num=3)
    unpaid = get_unpaid_orders(table_num=3)
    assert len(unpaid) == 2, f"未结单数量应为2，实际为{len(unpaid)}"
    print(f"  ✅ 点单落库，未结单 {len(unpaid)} 条")
    total = checkout(table_num=3)
    assert total == 120.0, f"结账总价应为120，实际为{total}"
    print(f"  ✅ 结账成功，总价 {total} 元")
    unpaid_after = get_unpaid_orders(table_num=3)
    assert len(unpaid_after) == 0
    print(f"  ✅ 结账后未结单为 0")

    print("\n=== 销售额查询 ===")
    sales = query_sales("today")
    assert sales == 120.0, f"今日销售额应为120，实际为{sales}"
    print(f"  ✅ 今日销售额: {sales} 元")

    print("\n=== 试用期检查 ===")
    assert is_trial_expired() is False  # trial_end_date 为空
    set_setting("trial_end_date", "2020-01-01")
    assert is_trial_expired() is True
    set_setting("trial_end_date", "")   # 重置
    print("  ✅ 试用期检查逻辑正确")

    # 清理临时数据库（含 WAL 辅助文件）
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(tmp.name + suffix)
        except OSError:
            pass

    print("\n══════════════════════════════════════")
    print("全部契约测试通过 ✅  data/db.py 可交付")
    print("══════════════════════════════════════")
