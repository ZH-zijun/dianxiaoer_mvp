"""
utils/daily_report.py — 每日自动日报

规范来源：
- project_start.md 第三节（功能范围 P2：每日自动日报）
- project_start.md 第十节（数据库完整结构汇总）

核心行为：
- 每日自动生成日报（当日销售额、订单数、支出、利润）
- 日报文本供本地通知或屏幕显示
- 由 settings_screen 调用触发，或由定时任务触发

对外接口：
- generate_daily_report(date_str=None) → dict  生成指定日期的日报
- format_report_text(report) → str             格式化日报为文本
"""

from datetime import datetime


def generate_daily_report(date_str: str = None) -> dict:
    """
    生成指定日期的日报数据。

    参数：
    - date_str: 日期字符串（YYYY-MM-DD），默认为今天

    返回值 dict：
    {
        "date": "2026-05-15",
        "total_sales": 1250.0,        # 当日已结账销售额
        "order_count": 15,            # 当日订单数（已结+未结）
        "paid_order_count": 12,       # 已结订单数
        "unpaid_count": 3,            # 未结订单数
        "total_cost": 500.0,          # 当日进货成本
        "total_expense": 100.0,       # 当日经营费用
        "profit": 650.0,              # 利润 = 销售额 - 成本
        "top_items": [                # 热销商品 TOP5
            {"name": "羊肉串", "qty": 300, "revenue": 900.0},
            ...
        ],
        "unpaid_tables": [3, 7],      # 未结桌号列表
    }
    """
    from data.db import _get_conn, _db_lock

    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    report = {
        "date": date_str,
        "total_sales": 0.0,
        "order_count": 0,
        "paid_order_count": 0,
        "unpaid_count": 0,
        "total_cost": 0.0,
        "total_expense": 0.0,
        "profit": 0.0,
        "top_items": [],
        "unpaid_tables": [],
    }

    with _db_lock:
        conn = _get_conn()
        try:
            # 当日销售额（已结账）
            row = conn.execute(
                """SELECT COALESCE(SUM(total_price),0) AS total
                   FROM orders
                   WHERE date(order_time)=? AND is_paid=1""",
                (date_str,)
            ).fetchone()
            report["total_sales"] = round(row["total"], 2)

            # 当日订单统计
            row_all = conn.execute(
                """SELECT COUNT(*) AS cnt FROM orders WHERE date(order_time)=?""",
                (date_str,)
            ).fetchone()
            report["order_count"] = row_all["cnt"]

            row_paid = conn.execute(
                """SELECT COUNT(*) AS cnt FROM orders
                   WHERE date(order_time)=? AND is_paid=1""",
                (date_str,)
            ).fetchone()
            report["paid_order_count"] = row_paid["cnt"]

            report["unpaid_count"] = report["order_count"] - report["paid_order_count"]

            # 当日进货成本
            row_cost = conn.execute(
                """SELECT COALESCE(SUM(amount),0) AS total
                   FROM expenses
                   WHERE date(expense_time)=? AND category='cost'""",
                (date_str,)
            ).fetchone()
            report["total_cost"] = round(row_cost["total"], 2)

            # 当日经营费用
            row_exp = conn.execute(
                """SELECT COALESCE(SUM(amount),0) AS total
                   FROM expenses
                   WHERE date(expense_time)=? AND category='expense'""",
                (date_str,)
            ).fetchone()
            report["total_expense"] = round(row_exp["total"], 2)

            # 利润 = 已结销售额 - 进货成本
            report["profit"] = round(report["total_sales"] - report["total_cost"], 2)

            # 热销商品 TOP5（按数量排序）
            top_rows = conn.execute(
                """SELECT item_name, SUM(quantity) AS total_qty, SUM(total_price) AS total_rev
                   FROM orders
                   WHERE date(order_time)=?
                   GROUP BY item_name
                   ORDER BY total_qty DESC
                   LIMIT 5""",
                (date_str,)
            ).fetchall()
            report["top_items"] = [
                {"name": r["item_name"], "qty": r["total_qty"],
                 "revenue": round(r["total_rev"], 2)}
                for r in top_rows
            ]

            # 未结桌号列表
            unpaid_rows = conn.execute(
                """SELECT DISTINCT table_num FROM orders
                   WHERE date(order_time)=? AND is_paid=0 AND table_num IS NOT NULL
                   ORDER BY table_num""",
                (date_str,)
            ).fetchall()
            report["unpaid_tables"] = [r["table_num"] for r in unpaid_rows]

        finally:
            conn.close()

    return report


def format_report_text(report: dict) -> str:
    """
    将日报数据格式化为可读文本。

    供屏幕显示和通知推送使用。
    """
    lines = [
        f"📊 {report['date']} 日报",
        "",
        f"💰 销售额：¥{report['total_sales']:.2f}",
        f"📦 订单数：{report['order_count']}（已结 {report['paid_order_count']}，未结 {report['unpaid_count']}）",
        f"📉 进货成本：¥{report['total_cost']:.2f}",
        f"📌 经营费用：¥{report['total_expense']:.2f}",
        f"✅ 利润：¥{report['profit']:.2f}",
    ]

    # 热销商品
    if report["top_items"]:
        lines.append("")
        lines.append("🔥 热销 TOP5：")
        for i, item in enumerate(report["top_items"], 1):
            lines.append(f"  {i}. {item['name']}  {item['qty']}份  ¥{item['revenue']:.0f}")

    # 未结桌号
    if report["unpaid_tables"]:
        tables_str = "、".join(str(t) for t in report["unpaid_tables"])
        lines.append("")
        lines.append(f"⚠️ 未结桌号：{tables_str}")

    return "\n".join(lines)


# ══════════════════════════════════════════════
# 契约测试
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import sys, os, tempfile

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from data.db import set_db_path, init_db, add_order, add_expense, add_menu_item

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    set_db_path(tmp.name)
    init_db()

    # 预置品类
    add_menu_item("羊肉串", 3.0, "串")
    add_menu_item("啤酒", 5.0, "瓶")
    add_menu_item("肉筋", 2.0, "串")

    # 写入测试数据（使用今天的日期）
    today = datetime.now().strftime("%Y-%m-%d")

    add_order("羊肉串", 30, 3.0, table_num=1)   # 90
    add_order("羊肉串", 20, 3.0, table_num=1)   # 60
    add_order("啤酒", 5, 5.0, table_num=1)      # 25
    add_order("肉筋", 10, 2.0, table_num=2)     # 20

    add_expense("羊排进货", 500, "cost")
    add_expense("炭", 50, "expense")

    failed_tests = []

    def run_test(name):
        def decorator(fn):
            try:
                fn()
                print(f"  R{name}: PASS")
            except AssertionError as e:
                print(f"  R{name}: FAIL - {e}")
                failed_tests.append(name)
            except Exception as e:
                print(f"  R{name}: ERROR - {type(e).__name__}: {e}")
                failed_tests.append(name)
        return decorator

    print("=== utils/daily_report.py 契约测试 ===")

    # ── R1: 日报数据生成 ──
    @run_test("1")
    def test_R1():
        report = generate_daily_report(today)
        assert report["date"] == today
        assert report["order_count"] == 4, f"订单数应为4，实际: {report['order_count']}"
        assert report["total_sales"] >= 0  # 未结账所以可能为0
        assert report["total_cost"] == 500.0, f"成本应为500，实际: {report['total_cost']}"
        assert report["total_expense"] == 50.0, f"费用应为50，实际: {report['total_expense']}"
        assert report["profit"] == report["total_sales"] - 500.0

    # ── R2: 热销商品排序 ──
    @run_test("2")
    def test_R2():
        report = generate_daily_report(today)
        assert len(report["top_items"]) > 0, "应有热销商品"
        # 羊肉串数量最多（30+20=50）
        assert report["top_items"][0]["name"] == "羊肉串", \
            f"热销第一名应为羊肉串，实际: {report['top_items'][0]['name']}"
        assert report["top_items"][0]["qty"] == 50, \
            f"羊肉串数量应为50，实际: {report['top_items'][0]['qty']}"

    # ── R3: 未结桌号 ──
    @run_test("3")
    def test_R3():
        report = generate_daily_report(today)
        # 所有订单未结
        assert 1 in report["unpaid_tables"], "1号桌应有未结订单"
        assert 2 in report["unpaid_tables"], "2号桌应有未结订单"

    # ── R4: 格式化文本 ──
    @run_test("4")
    def test_R4():
        report = generate_daily_report(today)
        text = format_report_text(report)
        assert today in text, "日报应包含日期"
        assert "销售额" in text, "应包含销售额"
        assert "利润" in text, "应包含利润"
        assert "热销" in text, "应包含热销排行"
        assert "羊肉串" in text, "应包含商品名"

    # ── R5: 空数据日期 ──
    @run_test("5")
    def test_R5():
        report = generate_daily_report("2099-01-01")
        assert report["date"] == "2099-01-01"
        assert report["order_count"] == 0
        assert report["total_sales"] == 0.0
        assert report["total_cost"] == 0.0
        assert report["profit"] == 0.0
        assert len(report["top_items"]) == 0

    passed = 5 - len(failed_tests)

    # 清理
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(tmp.name + suffix)
        except OSError:
            pass

    print(f"\n{'='*40}")
    if failed_tests:
        print(f"测试结果: {passed}/5 通过，失败项: {failed_tests}")
        sys.exit(1)
    else:
        print(f"全部 {passed}/5 契约测试通过 ✅  utils/daily_report.py 可交付")
    print(f"{'='*40}")
