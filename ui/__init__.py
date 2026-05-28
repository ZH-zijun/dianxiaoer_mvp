"""
ui 包 — 店小二 UI 界面模块

子模块：
- login_screen.py   登录页（密码验证 + 首次改密）
- chat_screen.py    主对话框（对话气泡 + 唱诺高亮 + 录音按钮）
- settings_screen.py 设置页（API配置 / 偏好 / 备份）

设计约束（来源：ui_spec.md）：
- 浅色主题，白色卡片 + 灰色页面背景
- 对话内容字号 >= 16sp
- 唱诺文案红色醒目
- 按钮文字字号 >= 14sp
- 录音按钮 >= 44dp x 44dp
"""

# ══════════════════════════════════════════════
# 配色方案（浅色主题）
# ══════════════════════════════════════════════

# 主色
PRIMARY_RED = (0.898, 0.224, 0.208, 1)       # #E53935 异常横幅、唱诺高亮、语音按钮
PRIMARY_ORANGE = (1.0, 0.427, 0.0, 1)         # #FF6D00 设置页主按钮、开关激活
PRIMARY_BLUE = (0.129, 0.588, 0.953, 1)       # #2196F3 登录页插图主色
PRIMARY_RED_DARK = (0.8, 0.15, 0.15, 1)       # 录音中加深

# 辅助色
COLOR_ERROR = (0.898, 0.224, 0.208, 1)        # #E53935
COLOR_SUCCESS = (0.298, 0.686, 0.314, 1)      # #4CAF50

# 中性色
BG_PAGE = (0.961, 0.961, 0.961, 1)            # #F5F5F5 页面背景
BG_CARD = (1.0, 1.0, 1.0, 1)                  # #FFFFFF 卡片/气泡背景
TEXT_PRIMARY = (0.2, 0.2, 0.2, 1)             # #333333
TEXT_SECONDARY = (0.4, 0.4, 0.4, 1)           # #666666
TEXT_PLACEHOLDER = (0.6, 0.6, 0.6, 1)         # #999999
BORDER_LIGHT = (0.878, 0.878, 0.878, 1)       # #E0E0E0
BORDER_DARK = (0.8, 0.8, 0.8, 1)              # #CCCCCC
COLOR_DISABLED = (0.741, 0.741, 0.741, 1)     # #BDBDBD

# 阴影（Kivy 不支持原生阴影，使用深色半透明模拟）
SHADOW_LIGHT = (0, 0, 0, 0.06)
SHADOW_MEDIUM = (0, 0, 0, 0.08)

# 唱诺专用
CHANGNUO_BG = PRIMARY_RED
CHANGNUO_COLOR = (1.0, 1.0, 1.0, 1)           # 白色文字

# 状态栏
STATUS_BAR_RED = PRIMARY_RED
STATUS_BAR_TEXT = (1.0, 1.0, 1.0, 1)

# 按钮
BTN_PRIMARY = PRIMARY_ORANGE
BTN_PRIMARY_TEXT = (1.0, 1.0, 1.0, 1)
BTN_DANGER = PRIMARY_RED
BTN_DANGER_TEXT = (1.0, 1.0, 1.0, 1)
BTN_RECORD = PRIMARY_RED
BTN_RECORD_ACTIVE = PRIMARY_RED_DARK
BTN_TEXT = (1.0, 1.0, 1.0, 1)
BTN_OUTLINE_TEXT = TEXT_PRIMARY
BTN_OUTLINE_BORDER = BORDER_DARK

# 文字
TEXT_HINT = TEXT_PLACEHOLDER
TEXT_ERROR = COLOR_ERROR
TEXT_SUCCESS = (0.298, 0.686, 0.314, 1)

# 分隔线
DIVIDER = BORDER_LIGHT

# ══════════════════════════════════════════════
# 字号规范（sp）
# ══════════════════════════════════════════════

FONT_TITLE = 18      # 导航栏标题、卡片标题
FONT_BODY = 16        # 消息正文、设置页项
FONT_SMALL = 14       # 占位、次要说明、按钮
FONT_CHANGNUO = 18    # 唱诺文案
FONT_BTN = 14         # 按钮文字
FONT_INPUT = 16       # 输入框文字
FONT_HINT = 14        # 提示/辅助文字
FONT_ERROR = 14       # 错误提示
FONT_STATUS = 14      # 状态栏文字

# 兼容旧变量名
FONT_CHAT = FONT_BODY
FONT_CHAT_SMALL = 12
FONT_BTN_LARGE = FONT_BODY
FONT_LABEL = FONT_SMALL

# ══════════════════════════════════════════════
# 间距规范（dp，基础单位 8px）
# ══════════════════════════════════════════════

SPACING_UNIT = 8
PADDING_X = 16
PADDING_Y = 12
PADDING_SMALL = 8
PADDING_LARGE = 24
PADDING_XL = 32
MARGIN_BUBBLE = 8
MARGIN_BOTTOM = 16

# ══════════════════════════════════════════════
# 圆角半径
# ══════════════════════════════════════════════

RADIUS_SM = 4
RADIUS_MD = 8
RADIUS_LG = 12
RADIUS_XL = 20

# ══════════════════════════════════════════════
# 组件尺寸（dp）
# ══════════════════════════════════════════════

BTN_HEIGHT = 44       # 标准按钮高度
BTN_RECORD_SIZE = 44  # 录音按钮尺寸
INPUT_HEIGHT = 44     # 输入框高度
STATUS_BAR_HEIGHT = 44
BUBBLE_RADIUS = 12
BUBBLE_MAX_WIDTH = 0.85
NAV_BAR_HEIGHT = 44

# ══════════════════════════════════════════════
# 动画
# ══════════════════════════════════════════════

ANIM_DURATION = 0.3
