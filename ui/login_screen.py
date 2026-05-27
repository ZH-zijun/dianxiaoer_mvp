"""
ui/login_screen.py — 店小二登录页

规范来源：
- project_start.md 第六节第2款（登录模块）
- UI 设计约束：深色背景、高对比度、按钮 >= 48dp

功能：
- 密码输入 + 登录按钮
- 首次登录（默认密码）强制修改密码（改密弹窗）
- 错误 3 次锁定，提示并退出
- 登录成功后切换到主对话框
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.clock import Clock

from ui import (
    BG_DARK, BG_CARD, BG_INPUT, BTN_PRIMARY, BTN_PRIMARY_TEXT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_HINT, TEXT_ERROR, TEXT_SUCCESS,
    DIVIDER,
    FONT_TITLE, FONT_CHAT, FONT_BTN, FONT_BTN_LARGE, FONT_INPUT, FONT_HINT,
    PADDING_X, PADDING_Y, PADDING_LARGE, PADDING_SMALL,
    BTN_HEIGHT, INPUT_HEIGHT, BUBBLE_RADIUS,
    ANIM_DURATION,
)


class LoginScreen(Screen):
    """登录页面"""

    def __init__(self, app=None, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._popup = None
        self._build_ui()

    def _build_ui(self):
        """构建登录界面"""
        self.clear_widgets()

        # 根布局 — 垂直居中
        root = BoxLayout(
            orientation='vertical',
            padding=(PADDING_X * 2, PADDING_Y),
            spacing=PADDING_LARGE,
            size_hint=(0.85, None),
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
        )

        # ── 标题区域 ──
        title_box = BoxLayout(orientation='vertical', size_hint_y=None, height=80)
        title_box.add_widget(Label(
            text='店小二',
            font_size=FONT_TITLE + 8,
            color=TEXT_PRIMARY,
            bold=True,
            size_hint_y=None,
            height=50,
        ))
        title_box.add_widget(Label(
            text='AI 记账助手',
            font_size=FONT_HINT,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=24,
        ))

        # ── 密码输入 ──
        self._password_input = TextInput(
            hint_text='请输入密码',
            password=True,
            font_size=FONT_INPUT,
            background_color=BG_INPUT,
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_HINT,
            cursor_color=TEXT_PRIMARY,
            padding=(PADDING_X, PADDING_SMALL),
            size_hint_y=None,
            height=INPUT_HEIGHT,
            multiline=False,
        )
        # 输入框圆角边框
        from kivy.graphics import Color, Rectangle, Line
        with self._password_input.canvas.before:
            Color(*DIVIDER)
            self._input_border = Line(
                rectangle=(
                    self._password_input.x,
                    self._password_input.y,
                    self._password_input.width,
                    self._password_input.height,
                ),
                width=1.5,
            )
        self._password_input.bind(
            pos=self._update_input_border,
            size=self._update_input_border,
            on_text_validate=self._on_login_pressed,
        )

        # ── 状态提示 ──
        self._status_label = Label(
            text='',
            font_size=FONT_HINT,
            color=TEXT_ERROR,
            size_hint_y=None,
            height=24,
            halign='center',
        )

        # ── 登录按钮 ──
        login_btn = Button(
            text='登 录',
            font_size=FONT_BTN_LARGE,
            color=BTN_PRIMARY_TEXT,
            background_color=BTN_PRIMARY,
            size_hint_y=None,
            height=BTN_HEIGHT,
            on_press=self._on_login_pressed,
        )
        # 按钮圆角
        login_btn.background_normal = ''
        login_btn.background_down = ''
        with login_btn.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(*BTN_PRIMARY)
            self._login_btn_bg = RoundedRectangle(
                pos=login_btn.pos,
                size=login_btn.size,
                radius=[BUBBLE_RADIUS,],
            )
        login_btn.bind(pos=self._update_btn_bg, size=self._update_btn_bg)
        self._login_btn = login_btn

        # ── 底部版本 ──
        ver_label = Label(
            text='V1.0 MVP',
            font_size=FONT_HINT - 2,
            color=TEXT_HINT,
            size_hint_y=None,
            height=20,
        )

        # 组装
        root.add_widget(title_box)
        root.add_widget(self._password_input)
        root.add_widget(self._status_label)
        root.add_widget(login_btn)
        root.add_widget(ver_label)

        self.add_widget(root)

    def _update_input_border(self, instance, value):
        """更新输入框边框位置"""
        self._input_border.rectangle = (
            instance.x, instance.y,
            instance.width, instance.height,
        )

    def _update_btn_bg(self, instance, value):
        """更新按钮圆角背景"""
        self._login_btn_bg.pos = instance.pos
        self._login_btn_bg.size = instance.size

    def _on_login_pressed(self, instance=None):
        """登录按钮点击处理"""
        password = self._password_input.text.strip()
        if not password:
            self._status_label.text = '请输入密码'
            self._status_label.color = TEXT_ERROR
            return

        self._status_label.text = ''
        self._login_btn.disabled = True

        # 异步执行登录，避免阻塞 UI
        Clock.schedule_once(lambda dt: self._do_login(password), 0.1)

    def _do_login(self, password):
        """执行登录逻辑（在 Clock 回调中）"""
        from auth import login as do_login

        result = do_login(password)

        if result == 'ok':
            self._status_label.text = ''
            self._status_label.color = TEXT_SUCCESS
            # 登录成功，切换到主对话框
            if self.app:
                Clock.schedule_once(lambda dt: self.app.goto_chat(), 0.2)

        elif result == 'must_change':
            self._login_btn.disabled = False
            self._show_change_password_popup()

        elif result == 'locked_out':
            self._status_label.text = '密码错误次数过多，请稍后再试'
            self._status_label.color = TEXT_ERROR
            self._login_btn.disabled = True
            # 3 秒后退出
            Clock.schedule_once(lambda dt: self._exit_app(), 3)

        elif result == 'wrong_password':
            from auth import get_failed_count
            remaining = 3 - get_failed_count()
            self._status_label.text = f'密码错误，还剩 {remaining} 次机会'
            self._status_label.color = TEXT_ERROR
            self._login_btn.disabled = False
            self._password_input.text = ''
            self._password_input.focus = True

        else:
            self._status_label.text = f'登录失败：{result}'
            self._status_label.color = TEXT_ERROR
            self._login_btn.disabled = False

    def _show_change_password_popup(self):
        """显示修改密码弹窗"""
        self._popup_content = BoxLayout(
            orientation='vertical',
            padding=(PADDING_X, PADDING_Y),
            spacing=PADDING_SMALL,
            size_hint=(0.85, None),
        )
        self._popup_content.minimum_height = 240

        self._popup_content.add_widget(Label(
            text='首次登录，请修改密码',
            font_size=FONT_CHAT,
            color=TEXT_PRIMARY,
            bold=True,
            size_hint_y=None,
            height=32,
        ))

        self._popup_content.add_widget(Label(
            text='新密码（至少6位）：',
            font_size=FONT_HINT,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=22,
            halign='left',
        ))

        self._new_pwd_input = TextInput(
            hint_text='请输入新密码',
            password=True,
            font_size=FONT_INPUT,
            background_color=BG_INPUT,
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_HINT,
            padding=(PADDING_X, PADDING_SMALL),
            size_hint_y=None,
            height=INPUT_HEIGHT,
            multiline=False,
        )

        self._popup_content.add_widget(self._new_pwd_input)

        self._popup_status = Label(
            text='',
            font_size=FONT_HINT,
            color=TEXT_ERROR,
            size_hint_y=None,
            height=22,
            halign='center',
        )
        self._popup_content.add_widget(self._popup_status)

        btn_box = BoxLayout(
            orientation='horizontal',
            spacing=PADDING_SMALL,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        confirm_btn = Button(
            text='确认修改',
            font_size=FONT_BTN,
            color=BTN_PRIMARY_TEXT,
            background_color=BTN_PRIMARY,
        )
        confirm_btn.bind(on_press=self._on_change_password)

        cancel_btn = Button(
            text='取消',
            font_size=FONT_BTN,
            color=TEXT_PRIMARY,
            background_color=BG_INPUT,
        )
        cancel_btn.bind(on_press=self._close_popup)

        btn_box.add_widget(confirm_btn)
        btn_box.add_widget(cancel_btn)
        self._popup_content.add_widget(btn_box)

        self._popup = Popup(
            title='修改密码',
            content=self._popup_content,
            size_hint=(0.85, None),
            height=320,
            background_color=BG_CARD,
            separator_color=DIVIDER,
            title_color=TEXT_PRIMARY,
            title_size=FONT_CHAT,
            auto_dismiss=False,
        )
        self._popup.open()

    def _on_change_password(self, instance):
        """处理修改密码"""
        new_pwd = self._new_pwd_input.text.strip()

        if not new_pwd:
            self._popup_status.text = '密码不能为空'
            self._popup_status.color = TEXT_ERROR
            return

        if len(new_pwd) < 6:
            self._popup_status.text = '密码至少需要6位'
            self._popup_status.color = TEXT_ERROR
            return

        from auth import change_password
        result = change_password('123456', new_pwd)  # 默认密码作为旧密码

        if result == 'ok':
            self._popup_status.text = '密码修改成功！'
            self._popup_status.color = TEXT_SUCCESS
            Clock.schedule_once(lambda dt: self._after_change_ok(), 0.5)
        else:
            self._popup_status.text = f'修改失败：{result}'
            self._popup_status.color = TEXT_ERROR

    def _after_change_ok(self):
        """密码修改成功后关闭弹窗并提示重新登录"""
        self._close_popup(None)
        self._status_label.text = '密码修改成功，请重新登录'
        self._status_label.color = TEXT_SUCCESS
        self._password_input.text = ''
        self._password_input.focus = True
        self._login_btn.disabled = False

    def _close_popup(self, instance):
        """关闭弹窗"""
        if self._popup:
            self._popup.dismiss()
            self._popup = None

    def _exit_app(self):
        """退出应用"""
        if self.app:
            self.app.stop()

    def on_pre_enter(self):
        """每次进入登录页时重置状态"""
        self._password_input.text = ''
        self._status_label.text = ''
        self._login_btn.disabled = False
        # 延迟设置 focus，等窗口完全初始化后再弹出键盘
        Clock.schedule_once(lambda dt: setattr(self._password_input, 'focus', True), 0.5)
