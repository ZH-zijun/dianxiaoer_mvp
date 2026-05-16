"""
skills/dongbei_buff.py — 东北话滤镜

规范来源：
- project_start.md 第六节第6款（东北话滤镜）
- project_start.md 第九条第11条（处理顺序：先替换变量，后转方言）
- 01_PROJECT_CONSTITUTION.md 9.5（东北话影响所有输出文案）

核心行为：
- 字段映射表：标准话 → 东北话
- 只做映射，不破坏模板变量 {shop} {boss} 等
- 影响范围：唱诺文案 + 大模型对话回复 + 屏幕显示（所有输出文案）
- 默认开启，设置页可切换标准话（settings.dialect_mode）
"""

import random

# ══════════════════════════════════════════════
# 东北话映射表（标准话 → 东北话）
# ══════════════════════════════════════════════
# 规则：长词优先匹配，避免"好吃"先被"吃"匹配掉

_MAPPING = [
    # 称呼与礼貌
    ("客人", "贵客"),
    ("顾客", "贵客"),
    ("您好", "你好啊"),
    ("欢迎再来", "欢迎您再来啊"),
    ("欢迎光临", "欢迎光临啊"),
    ("谢谢", "多谢啊"),
    ("再见", "慢走啊"),
    ("不好意思", "对不住啊"),
    ("麻烦", "费劲"),
    ("没关系", "没事儿"),
    ("好的", "妥了"),
    ("好的", "中"),
    ("请问", "问一声"),
    # 程度与数量
    ("很多", "老多了"),
    ("特别", "贼"),
    ("非常", "老"),
    ("非常好吃", "贼拉好吃"),
    ("特别好吃", "贼好吃"),
    ("很好吃", "贼好吃"),
    ("特别香", "贼香"),
    ("非常好", "贼好"),
    ("特别好", "贼好"),
    ("很多钱", "老些钱"),
    ("一大堆", "老鼻子了"),
    ("一大堆", "一大些"),
    # 形容与状态
    ("好吃", "好吃"),
    ("好吃", "香"),
    ("不错", "杠杠的"),
    ("厉害", "牛"),
    ("厉害", "猛"),
    ("快", "麻溜的"),
    ("快点", "麻溜点"),
    ("等一下", "等一哈"),
    ("等一下", "等一会儿"),
    ("马上", "这就"),
    ("马上来", "这就来"),
    ("马上安排", "这就安排"),
    ("稍等", "稍等哈"),
    ("稍等", "等一小会儿"),
    ("坐稳", "坐稳当"),
    ("行", "中"),
    ("可以", "中"),
    ("行", "成"),
    # 商业场景
    ("结账", "算账"),
    ("买单", "算账"),
    ("多少钱", "多钱"),
    ("一共", "总共"),
    ("总共", "拢共"),
    ("小票", "单子"),
    ("发票", "票据"),
    ("打折", "让利"),
    ("便宜", "实惠"),
    ("贵了", "有点儿贵"),
    ("合适", "得劲儿"),
    ("划算", "上算"),
    # 动作
    ("吃好", "吃好喝好"),
    ("喝好", "吃好喝好"),
    ("慢走", "慢走啊"),
    ("走好", "慢走"),
    ("小心", "留神"),
    ("看一下", "瞅一眼"),
    ("看一下", "瞧一眼"),
    ("尝尝", "尝尝鲜"),
    # 语气词补充
    ("呢", "捏"),
    ("什么", "啥"),
    ("怎么", "咋"),
    ("这个", "这"),
    ("那个", "那"),
    ("还", "还"),
]


def transform(text: str) -> str:
    """
    将标准话文本转换为东北话风格。

    处理逻辑：
    1. 按映射表从长到短替换（长词优先）
    2. 跳过模板变量占位符（{shop}、{boss} 等）
    3. 随机性：部分映射有多个候选时随机选一个

    注意：此函数必须在模板变量替换之后调用！
    """
    # 先保护模板变量，替换为临时占位符
    _placeholder_map = {}
    protected = text

    # 提取所有 {xxx} 形式的模板变量
    import re
    var_pattern = re.compile(r'\{(\w+)\}')
    idx = 0
    for m in var_pattern.finditer(text):
        original = m.group(0)  # e.g. "{shop}"
        placeholder = f"\x00PROTECT{idx}\x00"
        _placeholder_map[placeholder] = original
        protected = protected.replace(original, placeholder, 1)
        idx += 1

    # 执行东北话映射
    # 按 key 长度降序排列，确保长词优先匹配
    sorted_mapping = sorted(_MAPPING, key=lambda x: len(x[0]), reverse=True)
    for std, dongbei in sorted_mapping:
        protected = protected.replace(std, dongbei)

    # 恢复模板变量
    for placeholder, original in _placeholder_map.items():
        protected = protected.replace(placeholder, original)

    return protected


def is_dialect_enabled() -> bool:
    """
    检查东北话模式是否开启。
    从 settings 表读取 dialect_mode，默认为 dongbei（开启）。
    """
    from data.db import get_setting
    mode = get_setting("dialect_mode")
    return mode != "standard"


def transform_if_enabled(text: str) -> str:
    """
    便捷函数：若东北话模式开启则转换，否则原样返回。
    供唱诺模块和大模型回复统一调用。
    """
    if is_dialect_enabled():
        return transform(text)
    return text
