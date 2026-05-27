"""
main.py — 店小二 App 主入口

功能：
- 初始化数据库
- ScreenManager 管理页面切换（登录 → 主对话框 → 设置）
- 键盘处理、Android 返回键
- 试用期限检查

启动方式：
  python main.py                    # Windows 开发测试
  buildozer android debug run       # Android 真机运行
"""

import os
import sys

os.environ['SDL_HINT_ANDROID_SHOW_IME_WITH_KEYBOARD'] = '1'

# 将项目根目录加入 sys.path，确保所有模块可导入
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Kivy 配置（必须在 import kivy 之前）
os.environ.setdefault('KIVY_AUDIO', 'sdl2')

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, SlideTransition
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.config import Config

# ══════════════════════════════════════════════
# Kivy 窗口配置
# ══════════════════════════════════════════════

# 窗口背景色
Config.set('kivy', 'window_icon', '')
Config.set('graphics', 'width', '400')
Config.set('graphics', 'height', '720')
Config.set('graphics', 'resizable', True)
Config.set('graphics', 'minimum_width', '360')
Config.set('graphics', 'minimum_height', '640')
# 窗口背景色（Window.clearcolor 在 Android SDL2 上可靠，Config.set 不生效）
Window.clearcolor = (0.102, 0.102, 0.180, 1)

# 输入配置
Config.set('kivy', 'keyboard_mode', 'system')  # 使用系统键盘
Config.set('kivy', 'keyboard_layout', 'qwerty')

# Log 级别
Config.set('kivy', 'log_level', 'warning')

from kivy.base import ExceptionManager, ExceptionHandler

# ══════════════════════════════════════════════
# 注册中文字体（解决界面显示方块字）
# 尝试顺序：1. 应用内 bundled 字体  2. 系统字体
# ══════════════════════════════════════════════
_FONT_REGISTERED = False
try:
    from kivy.core.text import LabelBase
    # 首选：应用内 bundled 字体
    _bundled_font = os.path.join(_PROJECT_ROOT, 'assets', 'fonts', 'NotoSansSC-VF.ttf')
    if os.path.exists(_bundled_font):
        LabelBase.register(name='Roboto', fn_regular=_bundled_font)
        _FONT_REGISTERED = True
    else:
        # 备选：常见 Android 系统字体路径
        _font_candidates = [
            '/system/fonts/NotoSansSC-Regular.otf',
            '/system/fonts/DroidSansFallback.ttf',
            '/system/fonts/NotoSansCJK-Regular.ttc',
        ]
        for _font_path in _font_candidates:
            if os.path.exists(_font_path):
                LabelBase.register(name='Roboto', fn_regular=_font_path)
                _FONT_REGISTERED = True
                break
    if not _FONT_REGISTERED:
        print('[字体] 未找到中文字体，文字可能显示为方块')
except Exception as _e:
    print(f'[字体] 注册失败: {_e}')
# ===================================================


# ══════════════════════════════════════════════
# 导入 UI 常量（必须在 App 类定义之前，供 build() 使用）
# ══════════════════════════════════════════════
from ui import ANIM_DURATION


class AppExceptionHandler(ExceptionHandler):
    """全局异常处理，防止 App 崩溃"""

    def handle_exception(self, inst):
        import traceback
        traceback.print_exception(type(inst), inst, inst.__traceback__)
        return ExceptionManager.PASS


# 注册异常处理器
_exception_handler = AppExceptionHandler()
ExceptionManager.add_handler(_exception_handler)


class DianxiaoerApp(App):
    """店小二 App"""

    def build(self):
        """构建 App 主界面"""
        # 设置窗口标题
        self.title = '店小二 - AI 记账助手'

        # 初始化数据库
        self._init_database()

        # 页面管理器
        self.sm = ScreenManager(transition=SlideTransition(duration=ANIM_DURATION))

        # 延迟导入 UI 模块（避免循环依赖，且需要数据库先初始化）
        Clock.schedule_once(lambda dt: self._init_screens(dt), 0.1)

        return self.sm

    def _init_database(self):
        """初始化数据库"""
        from data import db

        # 设置数据库路径
        db_path = os.path.join(self.user_data_dir, 'dianxiaoer.db')
        db.set_db_path(db_path)

        # 初始化建表
        db.init_db()

        # 检查试用期限
        self._check_trial()

    def _check_trial(self):
        """检查试用期限"""
        from data import db
        from datetime import datetime, date

        trial_end_str = db.get_setting('trial_end_date')
        if not trial_end_str:
            # 正式版，无限制
            self._is_trial = False
            return

        self._is_trial = True
        try:
            trial_end = datetime.strptime(trial_end_str, '%Y-%m-%d').date()
            if date.today() > trial_end:
                self._trial_expired = True
            else:
                self._trial_expired = False
                remaining = (trial_end - date.today()).days
                print(f'[试用] 剩余 {remaining} 天')
        except ValueError:
            self._trial_expired = False

    def _init_screens(self, dt):
        """初始化所有页面"""
        from ui.login_screen import LoginScreen
        from ui.chat_screen import ChatScreen
        from ui.settings_screen import SettingsScreen

        # 登录页
        self._login_screen = LoginScreen(app=self, name='login')
        self.sm.add_widget(self._login_screen)

        # 主对话框
        self._chat_screen = ChatScreen(app=self, name='chat')
        self.sm.add_widget(self._chat_screen)

        # 设置页
        self._settings_screen = SettingsScreen(app=self, name='settings')
        self.sm.add_widget(self._settings_screen)

        # 默认显示登录页
        self.sm.current = 'login'

    def goto_chat(self):
        """登录成功后跳转到主对话框"""
        self.sm.current = 'chat'

        # 添加欢迎消息
        Clock.schedule_once(lambda dt: self._add_welcome(), 0.3)

    def _add_welcome(self):
        """添加欢迎消息"""
        try:
            from skills.shop_identity import SHOP_NAME
            welcome = f'{SHOP_NAME}欢迎您！有什么可以帮您的？'
        except Exception:
            welcome = '欢迎使用店小二！有什么可以帮您的？'

        # 应用东北话滤镜
        try:
            from skills.dongbei_buff import transform_if_enabled
            welcome = transform_if_enabled(welcome)
        except Exception:
            pass

        self._chat_screen.add_message(welcome, is_user=False)

    def open_settings(self):
        """打开设置页"""
        self.sm.current = 'settings'

    def restart(self):
        """重启 App（数据重置或备份恢复后）"""
        import sys
        import os
        # 重新启动当前进程
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def on_start(self):
        """App 启动后"""
        # 'below_target' 而非 'resize'（Kivy 文档: resize 在 Android SDL2 上无效）
        Window.softinput_mode = 'below_target'
        Window.bind(on_keyboard=self._on_android_back)

    def _on_android_back(self, window, key, scancode, codepoint, modifier):
        """Android 返回键处理"""
        if key == 27:  # ESC / 返回键
            if self.sm.current == 'chat':
                # 主对话框中按返回键不退出，给用户确认机会
                return True
            elif self.sm.current == 'login':
                # 登录页按返回退出 App
                self.stop()
                return True
        return False


# ══════════════════════════════════════════════
# 启动
# ══════════════════════════════════════════════

if __name__ == '__main__':
    DianxiaoerApp().run()
