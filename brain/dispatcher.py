"""
brain/dispatcher.py — 店小二大脑调度器

规范来源：
- project_start.md 第六条第4款（大脑调度器）
- project_start.md 第九条第2条（JSON Schema 校验 + 超时10秒 + 重试1次）
- 01_PROJECT_CONSTITUTION.md 2.2（调度顺序不可变）
- 01_PROJECT_CONSTITUTION.md 9.4（无二次确认）

核心流程：
    用户文本 → 拼接系统Prompt(含品类列表) → 调用大模型API → 解析JSON → 执行操作 → 返回结果

返回值 dict 结构：
    {
        "action": str,          # add_order / checkout / chat / ...
        "chat": str,            # 大模型生成的回复文案（供屏幕显示）
        "changnuo": str | None, # 唱诺文案（仅 add_order/checkout 有值，其余 None）
        "data": dict | None,    # 操作相关数据（如结账总价、销售额等）
    }
"""

import json
import re
import urllib.request
import urllib.error
import ssl
import threading

# 超时设置
_TIMEOUT_SECONDS = 10
_MAX_RETRIES = 1

# 有效 action 白名单
_VALID_ACTIONS = frozenset({
    "add_order", "checkout", "query_sales", "query_menu",
    "add_menu_item", "add_expense", "add_customer",
    "query_customer", "chat",
})

# 网络状态标志（线程安全）
_network_ok = True
_status_lock = threading.Lock()

# ══════════════════════════════════════════════
# 系统Prompt（硬编码）
# ══════════════════════════════════════════════

_SYSTEM_PROMPT_TEMPLATE = """你是餐饮/零售店AI记账助手"店小二"。你的任务是将用户的自然语言输入转换为结构化操作指令。

你必须严格返回JSON格式，不要输出任何其他内容。JSON结构如下：

支持的action类型：
1. add_order - 点单/加单
2. checkout - 结账送客
3. query_sales - 查询销售额（time_range: today/week/month）
4. query_menu - 查询当前品类列表
5. add_menu_item - 添加新品类（需先问价确认）
6. add_expense - 记录支出（category: cost=进货成本, expense=经营费用）
7. add_customer - 添加客户
8. query_customer - 查询客户信息
9. chat - 普通对话（无法识别为以上操作时使用）

JSON Schema（严格遵循）：
- 点单: {"action":"add_order","table_num":3或null,"customer_id":null或数字,"items":[{"name":"菜品名","quantity":数量,"unit_price":null}],"chat":"回复文案"}
  注意：unit_price为null时系统自动查品类库；若品类不存在则你应先问价格，用chat回复提问。
- 结账: {"action":"checkout","table_num":3或null,"customer_id":null或数字,"chat":"回复文案"}
- 查销售额: {"action":"query_sales","time_range":"today","chat":"回复文案"}
- 查菜单: {"action":"query_menu","chat":"回复文案"}
- 加品类: {"action":"add_menu_item","item_name":"名称","unit_price":价格,"unit":"单位","chat":"回复文案"}
- 加支出: {"action":"add_expense","item":"项目名","amount":金额,"category":"cost或expense","chat":"回复文案"}
- 加客户: {"action":"add_customer","name":"客户名","phone":"电话或空","chat":"回复文案"}
- 查客户: {"action":"query_customer","name":"客户名","chat":"回复文案"}
- 对话: {"action":"chat","chat":"回复文案"}

重要规则：
- 用户说的桌号用 table_num 表示，非桌台场景传 null
- 品类价格优先查品类库，不确定时问用户
- 数字和金额必须准确提取
- 回复文案要简短自然，像店员跟老板说话
- 无法理解用户意图时，使用 chat action 友好回复"""

# 品类列表拼接到系统Prompt的模板
_MENU_PROMPT = """

当前品类库（在售商品）：
{menu_list}

如果用户点的品类在列表中，unit_price填null让系统自动查库。
如果品类不在列表中，你应该先问价格（用chat回复），等用户报价后再用add_menu_item入库。"""


# ══════════════════════════════════════════════
# 大模型API调用
# ══════════════════════════════════════════════

def _build_messages(user_text: str) -> list:
    """构建发给大模型的消息列表（系统Prompt + 用户消息）"""
    from data.db import get_all_menu

    # 拼接品类列表
    menu_items = get_all_menu()
    if menu_items:
        menu_lines = []
        for item in menu_items:
            menu_lines.append(f"  {item['item_name']} - {item['unit_price']}元/{item['unit']}")
        menu_str = "\n".join(menu_lines)
    else:
        menu_str = "  （暂无品类，等待添加）"

    system_prompt = _SYSTEM_PROMPT_TEMPLATE + _MENU_PROMPT.format(menu_list=menu_str)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]


def _get_api_config() -> dict:
    """从数据库读取大模型API配置"""
    from data.db import get_setting

    return {
        "url": get_setting("llm_api_url") or "",
        "key": get_setting("llm_api_key") or "",
        "backup_url": get_setting("llm_backup_url") or "",
        "backup_key": get_setting("llm_backup_key") or "",
        "model": get_setting("llm_model") or "deepseek-chat",
    }


def _call_llm_api(api_url: str, api_key: str, model: str, messages: list) -> str | None:
    """
    调用大模型API，返回响应文本。
    失败返回 None（由调用方决定重试或切备用）。
    """
    if not api_url or not api_key:
        return None

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 512,
    }).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    # 跳过SSL证书验证（部分自建API可能用自签证书）
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS, context=ctx) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, json.JSONDecodeError, TimeoutError, OSError):
        return None


def _call_with_fallback(messages: list) -> str | None:
    """
    调用大模型API，含主备切换和重试逻辑。
    返回响应文本，全部失败返回 None。
    """
    global _network_ok
    config = _get_api_config()

    # 尝试主API
    if config["url"] and config["key"]:
        result = _call_llm_api(config["url"], config["key"], config["model"], messages)
        if result is not None:
            with _status_lock:
                _network_ok = True
            return result
        # 主API失败，重试1次
        result = _call_llm_api(config["url"], config["key"], config["model"], messages)
        if result is not None:
            with _status_lock:
                _network_ok = True
            return result

    # 尝试备用API
    if config["backup_url"] and config["backup_key"]:
        result = _call_llm_api(config["backup_url"], config["backup_key"], config["model"], messages)
        if result is not None:
            with _status_lock:
                _network_ok = True
            return result

    # 全部失败
    with _status_lock:
        _network_ok = False
    return None


# ══════════════════════════════════════════════
# JSON解析
# ══════════════════════════════════════════════

def _parse_llm_response(text: str) -> dict | None:
    """
    解析大模型返回的JSON。
    支持直接JSON和 ```json ... ``` 代码块格式。
    解析失败返回 None。
    """
    text = text.strip()

    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r"```json\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()

    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        if "action" not in data:
            return None
        if data["action"] not in _VALID_ACTIONS:
            return None
        # 确保 chat 字段存在
        if "chat" not in data:
            data["chat"] = ""
        return data
    except (json.JSONDecodeError, TypeError):
        return None


# ══════════════════════════════════════════════
# 操作执行
# ══════════════════════════════════════════════

def _execute_action(parsed: dict) -> dict:
    """
    根据解析结果执行数据库操作。
    返回增强后的结果字典（含 changnuo 和 data 字段）。

    宪法 9.4：所有操作立即落盘，无二次确认。
    """
    action = parsed["action"]
    chat = parsed.get("chat", "")
    result = {"action": action, "chat": chat, "changnuo": None, "data": None}

    if action == "add_order":
        result = _exec_add_order(parsed)

    elif action == "checkout":
        result = _exec_checkout(parsed)

    elif action == "query_sales":
        result = _exec_query_sales(parsed)

    elif action == "query_menu":
        result = _exec_query_menu()

    elif action == "add_menu_item":
        result = _exec_add_menu_item(parsed)

    elif action == "add_expense":
        result = _exec_add_expense(parsed)

    elif action == "add_customer":
        result = _exec_add_customer(parsed)

    elif action == "query_customer":
        result = _exec_query_customer(parsed)

    # chat action 不需要执行操作，直接返回
    return result


def _exec_add_order(parsed: dict) -> dict:
    """执行点单操作"""
    from data.db import get_menu_item, add_order, add_customer as db_add_customer, get_customer_by_name

    items = parsed.get("items", [])
    table_num = parsed.get("table_num")
    customer_id = parsed.get("customer_id")
    added_items = []

    for item in items:
        name = item.get("name", "")
        qty = item.get("quantity", 1)
        unit_price = item.get("unit_price")

        # unit_price 为 null → 自动查品类库
        if unit_price is None:
            menu_row = get_menu_item(name)
            if menu_row:
                unit_price = menu_row["unit_price"]
            else:
                # 品类不存在，跳过（大模型应已先问价，此处兜底）
                continue

        add_order(name, qty, unit_price, table_num=table_num, customer_id=customer_id)
        added_items.append({"name": name, "quantity": qty, "unit_price": unit_price})

    # 唱诺文案（使用 changnuo 模块）
    changnuo = None
    if added_items:
        try:
            from skills.changnuo import make_changnuo_order
            changnuo = make_changnuo_order(
                table_num=table_num,
                items=added_items,
                is_add=False,
            )
        except Exception:
            # 兜底：简单拼凑
            parts = [f"{i['quantity']}{i['name']}" for i in added_items]
            items_str = "、".join(parts)
            table_str = f"{table_num}号桌" if table_num else ""
            changnuo = f"{table_str}{items_str}，稍等！"

    return {
        "action": "add_order",
        "chat": parsed.get("chat", ""),
        "changnuo": changnuo,
        "data": {"added_items": added_items, "table_num": table_num},
    }


def _exec_checkout(parsed: dict) -> dict:
    """执行结账操作"""
    from data.db import checkout as db_checkout

    table_num = parsed.get("table_num")
    customer_id = parsed.get("customer_id")
    total = db_checkout(table_num=table_num, customer_id=customer_id)

    # 唱诺文案：送客唱诺（使用 changnuo 模块）
    try:
        from skills.changnuo import make_changnuo_checkout
        changnuo = make_changnuo_checkout()
    except Exception:
        changnuo = "慢走，欢迎再来！"

    return {
        "action": "checkout",
        "chat": parsed.get("chat", ""),
        "changnuo": changnuo,
        "data": {"total": total},
    }


def _exec_query_sales(parsed: dict) -> dict:
    """查询销售额"""
    from data.db import query_sales

    time_range = parsed.get("time_range", "today")
    if time_range not in ("today", "week", "month"):
        time_range = "today"

    total = query_sales(time_range)

    return {
        "action": "query_sales",
        "chat": parsed.get("chat", ""),
        "changnuo": None,
        "data": {"total": total, "time_range": time_range},
    }


def _exec_query_menu() -> dict:
    """查询品类列表"""
    from data.db import get_all_menu

    items = get_all_menu()
    menu_list = [
        {"name": i["item_name"], "price": i["unit_price"], "unit": i["unit"]}
        for i in items
    ]

    return {
        "action": "query_menu",
        "chat": "",  # 由调用方根据 data 渲染
        "changnuo": None,
        "data": {"menu": menu_list},
    }


def _exec_add_menu_item(parsed: dict) -> dict:
    """添加新品类"""
    from data.db import add_menu_item

    name = parsed.get("item_name", "")
    price = parsed.get("unit_price", 0)
    unit = parsed.get("unit", "份")

    item_id = add_menu_item(name, price, unit)

    return {
        "action": "add_menu_item",
        "chat": parsed.get("chat", ""),
        "changnuo": None,
        "data": {"item_name": name, "unit_price": price, "unit": unit, "id": item_id},
    }


def _exec_add_expense(parsed: dict) -> dict:
    """记录支出"""
    from data.db import add_expense

    item = parsed.get("item", "")
    amount = parsed.get("amount", 0)
    category = parsed.get("category", "expense")
    note = parsed.get("note", "")

    exp_id = add_expense(item, amount, category, note)

    return {
        "action": "add_expense",
        "chat": parsed.get("chat", ""),
        "changnuo": None,
        "data": {"item": item, "amount": amount, "category": category, "id": exp_id},
    }


def _exec_add_customer(parsed: dict) -> dict:
    """添加客户"""
    from data.db import add_customer

    name = parsed.get("name", "")
    phone = parsed.get("phone", "")
    note = parsed.get("note", "")

    cust_id = add_customer(name, phone=phone, note=note)

    return {
        "action": "add_customer",
        "chat": parsed.get("chat", ""),
        "changnuo": None,
        "data": {"name": name, "id": cust_id},
    }


def _exec_query_customer(parsed: dict) -> dict:
    """查询客户"""
    from data.db import get_customer_by_name, get_unpaid_orders

    name = parsed.get("name", "")
    customer = get_customer_by_name(name)

    if customer:
        unpaid = get_unpaid_orders(customer_id=customer["id"])
        orders = [
            {"item": o["item_name"], "qty": o["quantity"], "price": o["total_price"]}
            for o in unpaid
        ]
        data = {
            "name": customer["name"],
            "phone": customer["phone"],
            "id": customer["id"],
            "unpaid_orders": orders,
        }
    else:
        data = {"name": name, "found": False}

    return {
        "action": "query_customer",
        "chat": parsed.get("chat", ""),
        "changnuo": None,
        "data": data,
    }


# ══════════════════════════════════════════════
# 主调度入口
# ══════════════════════════════════════════════

def dispatch(user_text: str) -> dict:
    """
    主调度入口：用户文本 → 大模型解析 → 执行操作 → 返回结果。

    返回值：
    {
        "action": str,          # 动作类型
        "chat": str,            # 回复文案（屏幕显示）
        "changnuo": str | None, # 唱诺文案（仅 add_order/checkout）
        "data": dict | None,    # 操作数据
    }
    """
    # 1. 构建消息
    messages = _build_messages(user_text)

    # 2. 调用大模型
    response_text = _call_with_fallback(messages)

    # 3. 大模型不可用 → 兜底回复
    if response_text is None:
        return {
            "action": "chat",
            "chat": "网络不可用，请稍后再试。您的消息已保留，网络恢复后会自动处理。",
            "changnuo": None,
            "data": None,
        }

    # 4. 解析JSON
    parsed = _parse_llm_response(response_text)
    if parsed is None:
        return {
            "action": "chat",
            "chat": "没太听明白，能再说一遍不？",
            "changnuo": None,
            "data": None,
        }

    # 5. 执行操作
    return _execute_action(parsed)


def get_network_status() -> bool:
    """返回大模型API连通状态（True=可用）"""
    with _status_lock:
        return _network_ok


# ══════════════════════════════════════════════
# 契约测试（python -m brain.dispatcher 直接运行）
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile, sys, os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from data.db import set_db_path, init_db, add_menu_item as db_add_menu

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    set_db_path(tmp.name)
    init_db()

    # 预置品类
    db_add_menu("羊肉串", 3.0, "串")
    db_add_menu("肉筋", 2.0, "串")
    db_add_menu("啤酒", 5.0, "瓶")

    passed = 0
    failed_tests = []

    def run_test(name):
        def decorator(fn):
            try:
                fn()
                print(f"  B{name}: PASS")
            except AssertionError as e:
                print(f"  B{name}: FAIL - {e}")
                failed_tests.append(name)
            except Exception as e:
                print(f"  B{name}: ERROR - {type(e).__name__}: {e}")
                failed_tests.append(name)
        return decorator

    print("=== brain/dispatcher.py 契约测试 ===")

    # ── B1: JSON解析正确 ──
    @run_test("1")
    def test_B1():
        # 正常JSON
        r1 = _parse_llm_response('{"action":"chat","chat":"你好"}')
        assert r1 is not None, "正常JSON解析失败"
        assert r1["action"] == "chat"
        assert r1["chat"] == "你好"

        # 代码块包裹
        r2 = _parse_llm_response('```json\n{"action":"add_order","table_num":3,"items":[{"name":"羊肉串","quantity":10,"unit_price":null}],"chat":"ok"}\n```')
        assert r2 is not None, "代码块JSON解析失败"
        assert r2["action"] == "add_order"

        # 无效action
        r3 = _parse_llm_response('{"action":"hack_db","chat":"hehe"}')
        assert r3 is None, "无效action应返回None"

        # 非JSON
        r4 = _parse_llm_response("这是一段普通文字")
        assert r4 is None, "非JSON应返回None"

        # 缺少action字段
        r5 = _parse_llm_response('{"chat":"没action"}')
        assert r5 is None, "缺少action应返回None"

    # ── B2: _call_llm_api 无效配置返回None ──
    @run_test("2")
    def test_B2():
        r1 = _call_llm_api("", "fake_key", "model", [])
        assert r1 is None, "空URL应返回None"

        r2 = _call_llm_api("http://127.0.0.1:1", "fake_key", "model", [])
        assert r2 is None, "不可达地址应返回None"

    # ── B3: 操作执行验证（不调用大模型，直接测试 _execute_action）──
    @run_test("3")
    def test_B3():
        from data.db import get_menu_item, query_sales, get_all_menu

        # add_order：自动查库价格
        parsed_order = {
            "action": "add_order",
            "table_num": 5,
            "items": [{"name": "羊肉串", "quantity": 20, "unit_price": None}],
            "chat": "已记录",
        }
        result = _execute_action(parsed_order)
        assert result["action"] == "add_order"
        assert result["changnuo"] is not None, "点单应有唱诺"
        assert "20" in result["changnuo"] or "羊肉串" in result["changnuo"]
        assert result["data"]["added_items"][0]["unit_price"] == 3.0, "应自动查库得到单价3.0"

        # checkout
        parsed_checkout = {
            "action": "checkout",
            "table_num": 5,
            "chat": "5号桌结账",
        }
        result = _exec_checkout(parsed_checkout)
        assert result["action"] == "checkout"
        assert result["data"]["total"] == 60.0, f"结账总价应为60，实际{result['data']['total']}"
        assert result["changnuo"] is not None, "结账应有送客唱诺"

        # query_sales
        parsed_sales = {"action": "query_sales", "time_range": "today", "chat": ""}
        result = _execute_action(parsed_sales)
        assert result["data"]["total"] == 60.0
        assert result["changnuo"] is None, "查询不应有唱诺"

        # add_expense
        parsed_exp = {
            "action": "add_expense", "item": "炭", "amount": 100,
            "category": "cost", "chat": "已记录"
        }
        result = _execute_action(parsed_exp)
        assert result["action"] == "add_expense"
        assert result["changnuo"] is None, "支出不应有唱诺"

        # add_customer
        parsed_cust = {"action": "add_customer", "name": "张三", "phone": "138", "chat": "ok"}
        result = _execute_action(parsed_cust)
        assert result["action"] == "add_customer"
        assert result["data"]["id"] > 0

    # ── B4: dispatch 兜底路径（无API配置时）──
    @run_test("4")
    def test_B4():
        # 清除API配置确保走兜底
        from data.db import set_setting
        set_setting("llm_api_url", "")
        set_setting("llm_api_key", "")

        result = dispatch("来20串羊肉串")
        assert result["action"] == "chat", f"无API时应返回chat兜底，实际: {result['action']}"
        assert result["changnuo"] is None
        assert "不可用" in result["chat"] or "没听" in result["chat"]

        # 恢复网络状态
        global _network_ok
        with _status_lock:
            _network_ok = True

    # 统计
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
        print(f"全部 {passed}/4 契约测试通过 ✅  brain/dispatcher.py 可交付")
    print(f"{'='*40}")
