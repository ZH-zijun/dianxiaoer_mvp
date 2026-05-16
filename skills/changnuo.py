"""
skills/changnuo.py — 唱诺模板引擎

规范来源：
- project_start.md 第六节第5款（唱诺模块）
- 01_PROJECT_CONSTITUTION.md 9.2（唱诺触发边界不可变）
- 01_PROJECT_CONSTITUTION.md 9.5（东北话影响所有输出文案）
- project_start.md 第九条第11条（先替换变量，后转方言）
- project_start.md 第九条第12条（操作立即落盘后同步触发唱诺）

核心行为：
- 唱诺仅触发于：点单确认、加单确认、结账送客
- 以下绝对不唱：结账金额、成本费用、查询、删改
- 处理顺序：获取原始模板 → 替换变量 → 若方言开启则转东北话 → 最终文本
- 返回值供调用方决定显示和TTS播放

对外接口：
- make_changnuo_order(table_num, items) → str | None    点单唱诺
- make_changnuo_checkout() → str | None                  送客唱诺
- format_changnuo(text) → str                            通用格式化（替换变量+东北话）
"""

import random
import re

# ══════════════════════════════════════════════
# 点单唱诺模板
# ══════════════════════════════════════════════

_ORDER_TEMPLATES = [
    "{table}～{items}～坐稳稍等！",
    "{table}{items}～这就安排！",
    "{table}～{items}～稍等一会儿哈！",
    "{table}{items}，马上来！",
    "{table}～{items}～好的收到！",
]

# ══════════════════════════════════════════════
# 加单唱诺模板（区分于首次点单）
# ══════════════════════════════════════════════

_ADD_ORDER_TEMPLATES = [
    "{table}加单～{items}～马上安排！",
    "{table}加单了～{items}～这就来！",
    "{table}加单～又加了{items}～稍等哈！",
    "{table}{items}～加单马上到！",
]

# ══════════════════════════════════════════════
# 送客唱诺模板（含店名+老板名）
# ══════════════════════════════════════════════

_CHECKOUT_TEMPLATES = [
    "{shop}欢迎您再来！{boss}期待您再次光临！",
    "您吃好喝好，下回再来！{shop}感谢光临！",
    "慢走哈！{shop}{boss}恭候您下次光临！",
    "{shop}谢谢光临！{boss}祝您一路顺风！",
    "欢迎下次再来{shop}！{boss}等您！",
    "您慢走～{shop}永远欢迎您！",
]

# ══════════════════════════════════════════════
# 模板变量替换
# ══════════════════════════════════════════════

def _get_identity() -> dict:
    """从 shop_identity 读取名头常量"""
    from skills.shop_identity import SHOP_NAME, BOSS_NAME, BOSS_WIFE, WIFE_NOTE
    return {
        "shop": SHOP_NAME,
        "boss": BOSS_NAME,
        "wife": BOSS_WIFE,
        "wife_note": WIFE_NOTE,
    }


def _replace_vars(template: str, **kwargs) -> str:
    """
    替换模板中的 {xxx} 变量。
    未匹配的变量保持原样（不删除花括号）。
    """
    identity = _get_identity()
    all_vars = {**identity, **kwargs}
    for key, value in all_vars.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template


# ══════════════════════════════════════════════
# 唱诺生成
# ══════════════════════════════════════════════

def make_changnuo_order(
    table_num: int | None,
    items: list,
    is_add: bool = False,
) -> str | None:
    """
    生成点单/加单唱诺文案。

    参数：
    - table_num: 桌号，非桌台场景传 None
    - items: [{"name": "羊肉串", "quantity": 30}, ...]
    - is_add: True=加单（使用加单模板），False=首次点单

    返回值：
    - 格式化后的唱诺文案（已过东北话滤镜）
    - 若 items 为空返回 None
    """
    if not items:
        return None

    # 拼接菜品文案
    parts = []
    for item in items:
        name = item.get("name", "")
        qty = item.get("quantity", 1)
        parts.append(f"{qty}{name}")
    items_str = "、".join(parts)

    # 桌号文案
    table_str = f"{table_num}号桌" if table_num is not None else ""

    # 随机选模板
    templates = _ADD_ORDER_TEMPLATES if is_add else _ORDER_TEMPLATES
    template = random.choice(templates)

    # 第一步：替换变量
    text = _replace_vars(template, table=table_str, items=items_str)

    # 第二步：东北话转换（必须先替换变量再转方言！）
    from skills.dongbei_buff import transform_if_enabled
    text = transform_if_enabled(text)

    return text


def make_changnuo_checkout() -> str:
    """
    生成送客唱诺文案。
    注意：宪法 9.2 规定结账不喊金额，此处只喊送客语。
    """
    template = random.choice(_CHECKOUT_TEMPLATES)

    # 第一步：替换变量
    text = _replace_vars(template)

    # 第二步：东北话转换
    from skills.dongbei_buff import transform_if_enabled
    text = transform_if_enabled(text)

    return text


def format_changnuo(text: str) -> str:
    """
    通用唱诺格式化：替换变量 + 东北话转换。
    供外部需要手动构造唱诺文案的场景使用。
    """
    text = _replace_vars(text)
    from skills.dongbei_buff import transform_if_enabled
    text = transform_if_enabled(text)
    return text


# ══════════════════════════════════════════════
# 契约测试（python -m skills.changnuo 直接运行）
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import sys, os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    # 设置数据库（dongbei_buff 需要读 settings）
    from data.db import set_db_path, init_db, set_setting
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    set_db_path(tmp.name)
    init_db()
    # 确保东北话模式开启（默认）
    set_setting("dialect_mode", "dongbei")

    passed = 0
    failed_tests = []

    def run_test(name):
        def decorator(fn):
            try:
                fn()
                print(f"  D{name}: PASS")
            except AssertionError as e:
                print(f"  D{name}: FAIL - {e}")
                failed_tests.append(name)
            except Exception as e:
                print(f"  D{name}: ERROR - {type(e).__name__}: {e}")
                failed_tests.append(name)
        return decorator

    print("=== skills/ 契约测试 ===")

    # ── D1: 名头常量可读取 ──
    @run_test("1")
    def test_D1():
        from skills.shop_identity import SHOP_NAME, BOSS_NAME, BOSS_WIFE, WIFE_NOTE
        assert SHOP_NAME == "老五烧烤"
        assert BOSS_NAME == "老五"
        assert BOSS_WIFE == "老板娘小丽"
        assert WIFE_NOTE == "老板娘最美"

    # ── D2: 东北话滤镜 ──
    @run_test("2")
    def test_D2():
        from skills.dongbei_buff import transform, is_dialect_enabled, transform_if_enabled

        # 基本转换
        r1 = transform("客人很多")
        assert "贵客" in r1, f"'客人'应被替换为'贵客'，实际: {r1}"
        assert "老多了" in r1 or "老" in r1, f"'很多'应被替换，实际: {r1}"

        # 模板变量不被破坏
        r2 = transform("{shop}欢迎客人")
        assert "{shop}" in r2, f"模板变量不应被破坏，实际: {r2}"
        assert "贵客" in r2, f"'客人'应被替换，实际: {r2}"

        # 模式检查
        assert is_dialect_enabled() is True
        set_setting("dialect_mode", "standard")
        assert is_dialect_enabled() is False
        r3 = transform_if_enabled("客人很多")
        assert r3 == "客人很多", f"标准话模式不应转换，实际: {r3}"
        set_setting("dialect_mode", "dongbei")

    # ── D3: 点单唱诺 ──
    @run_test("3")
    def test_D3():
        # 点单
        r1 = make_changnuo_order(3, [{"name": "羊肉串", "quantity": 30}])
        assert r1 is not None, "点单唱诺不应为None"
        assert "30" in r1, f"应包含数量，实际: {r1}"
        assert "羊肉串" in r1, f"应包含菜名，实际: {r1}"

        # 非桌台场景（table_num=None）
        r2 = make_changnuo_order(None, [{"name": "啤酒", "quantity": 5}])
        assert r2 is not None
        assert "5" in r2
        assert "啤酒" in r2
        assert "号桌" not in r2, f"非桌台场景不应含桌号，实际: {r2}"

        # 空列表返回None
        r3 = make_changnuo_order(1, [])
        assert r3 is None

        # 加单模板
        r4 = make_changnuo_order(3, [{"name": "蚕茧", "quantity": 5}], is_add=True)
        assert r4 is not None
        assert "加单" in r4, f"加单应包含'加单'，实际: {r4}"

    # ── D4: 送客唱诺 ──
    @run_test("4")
    def test_D4():
        r = make_changnuo_checkout()
        assert "老五烧烤" in r, f"送客应含店名，实际: {r}"
        assert "老五" in r, f"送客应含老板名，实际: {r}"
        # 不应含金额相关
        assert "元" not in r, f"送客不应含金额，实际: {r}"

        # 多次调用应随机（大部分情况下不完全相同）
        results = set()
        for _ in range(20):
            results.add(make_changnuo_checkout())
        assert len(results) > 1, f"20次送客唱诺应至少有2种不同文案，实际只有 {len(results)} 种"

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
        print(f"全部 {passed}/4 契约测试通过 ✅  skills/ 模块可交付")
    print(f"{'='*40}")
