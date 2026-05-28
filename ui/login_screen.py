"""
ui/login_screen.py — 店小二登录页

规范来源：
- ui_spec.md 2.3（登录页布局网格）
- ui_spec.md 3.8（密码输入框）、3.9（错误提示框）
- ui_spec.md 5.3（密码修改流程）

功能（完整保留）：
- 密码输入 + 登录按钮
- 首次登录强制修改密码
- 错误 3 次锁定
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Rectangle

from ui import (
    BG_PAGE, BG_CARD,
    PRIMARY_RED, PRIMARY_ORANGE, PRIMARY_BLUE,
    BTN_PRIMARY, BTN_PRIMARY_TEXT,
    COLOR_DISABLED,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_PLACEHOLDER, TEXT_ERROR, TEXT_SUCCESS,
    DIVIDER,
    FONT_TITLE, FONT_BODY, FONT_SMALL, FONT_BTN, FONT_INPUT, FONT_HINT, FONT_ERROR,
    PADDING_X, PADDING_Y, PADDING_SMALL, PADDING_LARGE,
    BTN_HEIGHT, INPUT_HEIGHT, RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_XL,
    ANIM_DURATION,
)


class LoginScreen(Screen):

    def __init__(self, app=None, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._popup = None
        self._build_ui()

    def _build_ui(self):
        self.clear_widgets()

        # 页面背景
        with self.canvas.before:
            Color(*BG_PAGE)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        # 根布局 — 垂直居中
        root = BoxLayout(
            orientation='vertical',
            padding=(PADDING_LARGE, 0, PADDING_LARGE, 0),
            spacing=PADDING_LARGE,
            size_hint=(0.85, None),
            pos_hint={'center_x': 0.5, 'center_y': 0.48},
        )

        # ── 标题区域 ──
        title_box = BoxLayout(orientation='vertical', size_hint_y=None, height=70)
        title_box.add_widget(Label(
            text='店小二',
            font_size=28,
            color=PRIMARY_ORANGE,
            bold=True,
            size_hint_y=None,
            height=36,
        ))
        title_box.add_widget(Label(
            text='AI 记账助手',
            font_size=FONT_SMALL,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=24,
            halign='center',
        ))

        # ── 密码输入卡片 ──
        card = BoxLayout(
            orientation='vertical',
            padding=(PADDING_X, PADDING_Y),
            spacing=PADDING_SMALL,
            size_hint_y=None,
            height=110,
        )
        with card.canvas.before:
            Color(*BG_CARD)
            self._card_rect = RoundedRectangle(
                pos=card.pos, size=card.size, radius=[RADIUS_LG],
            )
        card.bind(pos=self._update_card_bg, size=self._update_card_bg)

        self._password_input = TextInput(
            hint_text='默认初始密码：123456',
            password=True,
            font_size=FONT_INPUT,
            background_color=(1, 1, 1, 0),
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_PLACEHOLDER,
            cursor_color=PRIMARY_BLUE,
            padding=(0, PADDING_SMALL),
            size_hint_y=None,
            height=INPUT_HEIGHT,
            multiline=False,
        )
        # 输入框下划线
        with self._password_input.canvas.before:
            Color(*DIVIDER)
            self._input_line = Rectangle(
                pos=(self._password_input.x, self._password_input.y),
                size=(self._password_input.width, 1),
            )
        self._password_input.bind(
            pos=self._update_input_line,
            size=self._update_input_line,
            on_text_validate=self._on_login_pressed,
        )

        # ── 提示文字 ──
        self._status_label = Label(
            text='',
            font_size=FONT_HINT,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=20,
            halign='center',
        )

        # ── 登录按钮 ──
        login_btn = Button(
            text='登 录',
            font_size=FONT_BTN,
            color=BTN_PRIMARY_TEXT,
            background_color=BTN_PRIMARY,
            size_hint_y=None,
            height=BTN_HEIGHT,
            on_press=self._on_login_pressed,
        )
        login_btn.background_normal = ''
        login_btn.background_down = ''
        with login_btn.canvas.before:
            Color(*BTN_PRIMARY)
            self._login_btn_bg = RoundedRectangle(
                pos=login_btn.pos, size=login_btn.size, radius=[RADIUS_XL],
            )
        login_btn.bind(pos=self._update_btn_bg, size=self._update_btn_bg)
        self._login_btn = login_btn

        # ── 底部版本 ──
        ver_label = Label(
            text='V1.0 MVP',
            font_size=FONT_SMALL,
            color=TEXT_PLACEHOLDER,
            size_hint_y=None,
            height=20,
        )

        # 组装
        card.add_widget(self._password_input)
        card.add_widget(self._status_label)

        root.add_widget(title_box)
        root.add_widget(card)
        root.add_widget(login_btn)
        root.add_widget(ver_label)
        self.add_widget(root)

    def _update_bg(self, instance, value):
        self._bg_rect.pos = instance.pos
        self._bg_rect.size = instance.size

    def _update_card_bg(self, instance, value):
        self._card_rect.pos = instance.pos
        self._card_rect.size = instance.size

    def _update_input_line(self, instance, value):
        self._input_line.pos = (instance.x, instance.y)
        self._input_line.size = (instance.width, 1)

    def _update_btn_bg(self, instance, value):
        self._login_btn_bg.pos = instance.pos
        self._login_btn_bg.size = instance.size

    # ══════════════════════════════════════════════
    # 以下业务逻辑全部保留不变
    # ══════════════════════════════════════════════

    def _on_login_pressed(self, instance=None):
        password = self._password_input.text.strip()
        if not password:
            self._status_label.text = '请输入密码'
            self._status_label.color = TEXT_ERROR
            return
        self._status_label.text = ''
        self._login_btn.disabled = True
        Clock.schedule_once(lambda dt: self._do_login(password), 0.1)

    def _do_login(self, password):
        from auth import login as do_login
        result = do_login(password)
        if result == 'ok':
            self._status_label.text = ''
            self._status_label.color = TEXT_SUCCESS
            if self.app:
                Clock.schedule_once(lambda dt: self.app.goto_chat(), 0.2)
        elif result == 'must_change':
            self._login_btn.disabled = False
            self._show_change_password_popup()
        elif result == 'locked_out':
            self._status_label.text = '密码错误次数过多，请稍后再试'
            self._status_label.color = TEXT_ERROR
            self._login_btn.disabled = True
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
        self._popup_content = BoxLayout(
            orientation='vertical',
            padding=(PADDING_X, PADDING_Y),
            spacing=PADDING_SMALL,
            size_hint=(0.85, None),
        )
        self._popup_content.minimum_height = 280

        self._popup_content.add_widget(Label(
            text='首次登录，请修改密码',
            font_size=FONT_BODY,
            color=TEXT_PRIMARY,
            bold=True,
            size_hint_y=None,
            height=32,
        ))
        self._popup_content.add_widget(Label(
            text='新密码（至少6位）：',
            font_size=FONT_SMALL,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=22,
            halign='left',
        ))
        self._new_pwd_input = TextInput(
            hint_text='请输入新密码',
            password=True,
            font_size=FONT_INPUT,
            background_color=(1, 1, 1, 0),
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_PLACEHOLDER,
            padding=(0, PADDING_SMALL),
            size_hint_y=None,
            height=INPUT_HEIGHT,
            multiline=False,
        )
        self._popup_content.add_widget(self._new_pwd_input)

        self._popup_status = Label(
            text='', font_size=FONT_HINT, color=TEXT_ERROR,
            size_hint_y=None, height=22, halign='center',
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
            background_color=(1, 1, 1, 0.5),
        )
        cancel_btn.bind(on_press=self._close_popup)
        btn_box.add_widget(confirm_btn)
        btn_box.add_widget(cancel_btn)
        self._popup_content.add_widget(btn_box)

        self._popup = Popup(
            title='修改密码',
            content=self._popup_content,
            size_hint=(0.85, None),
            height=340,
            background_color=BG_CARD,
            separator_color=DIVIDER,
            title_color=TEXT_PRIMARY,
            title_size=FONT_BODY,
            auto_dismiss=False,
        )
        self._popup.open()

    def _on_change_password(self, instance):
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
        result = change_password('123456', new_pwd)
        if result == 'ok':
            self._popup_status.text = '密码修改成功！'
            self._popup_status.color = TEXT_SUCCESS
            Clock.schedule_once(lambda dt: self._after_change_ok(), 0.5)
        else:
            self._popup_status.text = f'修改失败：{result}'
            self._popup_status.color = TEXT_ERROR

    def _after_change_ok(self):
        self._close_popup(None)
        self._status_label.text = '密码修改成功，请重新登录'
        self._status_label.color = TEXT_SUCCESS
        self._password_input.text = ''
        self._password_input.focus = True
        self._login_btn.disabled = False

    def _close_popup(self, instance):
        if self._popup:
            self._popup.dismiss()
            self._popup = None

    def _exit_app(self):
        if self.app:
            self.app.stop()

    def on_pre_enter(self):
        self._password_input.text = ''
        self._status_label.text = ''
        self._login_btn.disabled = False
        Clock.schedule_once(lambda dt: setattr(self._password_input, 'focus', True), 0.5)
