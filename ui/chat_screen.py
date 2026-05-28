"""
ui/chat_screen.py — 店小二主对话框

规范来源：
- ui_spec.md 2.1（首页/主对话页）
- ui_spec.md 3.x（消息气泡、异常横幅、语音输入框、加载指示）

功能（全部保留不动）：
- 对话气泡列表：用户（白底+深色字）、AI（白底+深色字）
- 唱诺文案：红色气泡 18sp，明显样式区分普通对话
- 底部固定输入区：语音按钮 + 输入框 + 发送按钮
- 顶部红色状态栏：网络/大模型异常时显示
- 对话区域可滚动
- 键盘弹出时自动适应
- 网络恢复后逐条处理堆积消息，不补唱诺
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Rectangle
import time

from ui import (
    BG_PAGE, BG_CARD,
    PRIMARY_RED, PRIMARY_ORANGE,
    CHANGNUO_BG, CHANGNUO_COLOR,
    STATUS_BAR_RED, STATUS_BAR_TEXT,
    BTN_PRIMARY, BTN_PRIMARY_TEXT, BTN_RECORD, BTN_RECORD_ACTIVE, BTN_TEXT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_PLACEHOLDER, TEXT_HINT,
    DIVIDER, COLOR_DISABLED,
    FONT_TITLE, FONT_CHANGNUO, FONT_CHAT, FONT_SMALL, FONT_BTN, FONT_INPUT, FONT_STATUS,
    PADDING_X, PADDING_Y, PADDING_SMALL, PADDING_LARGE,
    MARGIN_BUBBLE,
    BTN_HEIGHT, BTN_RECORD_SIZE, INPUT_HEIGHT, STATUS_BAR_HEIGHT,
    BUBBLE_RADIUS, BUBBLE_MAX_WIDTH, RADIUS_LG, RADIUS_XL,
    ANIM_DURATION, NAV_BAR_HEIGHT, SPACING_UNIT,
)


class ChatBubble(BoxLayout):
    """单条对话气泡组件"""

    def __init__(self, text='', is_user=False, is_changnuo=False,
                 timestamp='', **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.height = self.minimum_height
        self.padding = (0, PADDING_SMALL)

        # ── 发送者标签 + 时间 ──
        header = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=20,
            spacing=PADDING_SMALL,
        )
        if is_user:
            sender_text = '我'
            sender_color = TEXT_SECONDARY
        else:
            sender_text = '店小二'
            sender_color = TEXT_SECONDARY

        sender_label = Label(
            text=sender_text,
            font_size=FONT_SMALL,
            color=sender_color,
            size_hint_x=None,
            width=len(sender_text) * 14 + 8,
        )
        time_label = Label(
            text=timestamp,
            font_size=FONT_SMALL,
            color=TEXT_HINT,
            halign='right',
        )

        if is_user:
            header.add_widget(Label(size_hint_x=1))
            header.add_widget(time_label)
            header.add_widget(sender_label)
        else:
            header.add_widget(sender_label)
            header.add_widget(Label(size_hint_x=1))
            header.add_widget(time_label)

        # ── 气泡主体 ──
        bubble = BoxLayout(
            orientation='vertical',
            padding=(PADDING_X, PADDING_SMALL),
            size_hint_y=None,
            size_hint_x=BUBBLE_MAX_WIDTH,
        )

        if is_changnuo:
            bubble_bg = CHANGNUO_BG
            bubble_text_color = CHANGNUO_COLOR
            bubble.pos_hint = {'right': 1}
            font_size = FONT_CHANGNUO
            display_text = f'≪ {text} ≫'
            is_bold = True
        else:
            bubble_bg = BG_CARD
            bubble_text_color = TEXT_PRIMARY
            font_size = FONT_CHAT
            display_text = text
            is_bold = False

        # 气泡圆角背景 + 阴影模拟
        with bubble.canvas.before:
            Color(*bubble_bg)
            self._bubble_rect = RoundedRectangle(
                pos=bubble.pos, size=bubble.size,
                radius=[BUBBLE_RADIUS] * 4,
            )
        bubble.bind(pos=self._update_bubble, size=self._update_bubble)

        bubble_label = Label(
            text=display_text,
            font_size=font_size,
            color=bubble_text_color,
            bold=is_bold,
            halign='left',
            valign='middle',
            text_size=(None, None),
            markup=False,
        )
        bubble_label.bind(
            texture_size=lambda inst, val: setattr(bubble, 'minimum_height', val[1] + PADDING_SMALL * 2),
        )
        bubble.add_widget(bubble_label)

        self.add_widget(header)
        self.add_widget(bubble)

        Clock.schedule_once(lambda dt: self._refresh_height(), 0.05)

    def _update_bubble(self, instance, value):
        self._bubble_rect.pos = instance.pos
        self._bubble_rect.size = instance.size

    def _refresh_height(self):
        self.height = max(self.minimum_height, 60)


class StatusBanner(Label):
    """网络状态横条"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.text = ''
        self.font_size = FONT_STATUS
        self.color = STATUS_BAR_TEXT
        self.halign = 'center'
        self.valign = 'middle'
        self.size_hint_y = None
        self.height = 0
        self.bold = True
        self._visible = False

        with self.canvas.before:
            Color(*STATUS_BAR_RED)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_rect, size=self._update_rect)

    def show(self, msg='网络不可用，消息待处理'):
        self.text = msg
        self.height = STATUS_BAR_HEIGHT
        self._visible = True

    def hide(self):
        self.text = ''
        self.height = 0
        self._visible = False

    def _update_rect(self, instance, value):
        self._rect.pos = instance.pos
        self._rect.size = instance.size


class InputBar(BoxLayout):
    """底部输入栏：语音按钮 + 输入框 + 发送按钮"""

    def __init__(self, on_send=None, on_record_press=None, on_record_release=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.padding = (PADDING_X, PADDING_SMALL, PADDING_X, PADDING_SMALL)
        self.spacing = PADDING_SMALL
        self.size_hint_y = None
        self.height = BTN_HEIGHT + PADDING_SMALL * 2

        self._on_send = on_send
        self._on_record_press = on_record_press
        self._on_record_release = on_record_release

        # ── 语音按钮（左侧，圆形）──
        self._record_btn = Button(
            text='\U0001F3A4',
            font_size=20,
            color=BTN_TEXT,
            background_color=BTN_RECORD,
            size_hint_x=None,
            width=BTN_RECORD_SIZE,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        self._record_btn.bind(
            on_press=self._on_record_btn_press,
            on_release=self._on_record_btn_release,
        )
        self._record_btn.background_normal = ''
        self._record_btn.background_down = ''
        with self._record_btn.canvas.before:
            Color(*BTN_RECORD)
            self._record_bg = RoundedRectangle(
                pos=self._record_btn.pos, size=self._record_btn.size,
                radius=[BTN_HEIGHT / 2],
            )
        self._record_btn.bind(pos=self._update_record_bg, size=self._update_record_bg)

        # ── 文字输入框 ──
        self._text_input = TextInput(
            hint_text='说点什么...',
            font_size=FONT_INPUT,
            background_color=BG_CARD,
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_PLACEHOLDER,
            cursor_color=PRIMARY_ORANGE,
            padding=(PADDING_SMALL, 0),
            multiline=False,
            size_hint_y=None,
            height=BTN_HEIGHT,
            write_tab=False,
        )
        self._text_input.bind(on_text_validate=self._on_send_pressed)
        # 输入框圆角边框
        with self._text_input.canvas.before:
            Color(*DIVIDER)
            self._input_rect = RoundedRectangle(
                pos=self._text_input.pos, size=self._text_input.size,
                radius=[RADIUS_XL],
            )
        self._text_input.bind(pos=self._update_input_rect, size=self._update_input_rect)

        # ── 发送按钮 ──
        self._send_btn = Button(
            text='发送',
            font_size=FONT_BTN,
            color=BTN_PRIMARY_TEXT,
            background_color=BTN_PRIMARY,
            size_hint_x=None,
            width=60,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        self._send_btn.bind(on_press=self._on_send_pressed)
        self._send_btn.background_normal = ''
        self._send_btn.background_down = ''
        with self._send_btn.canvas.before:
            Color(*BTN_PRIMARY)
            self._send_bg = RoundedRectangle(
                pos=self._send_btn.pos, size=self._send_btn.size,
                radius=[RADIUS_XL],
            )
        self._send_btn.bind(pos=self._update_send_bg, size=self._update_send_bg)

        self.add_widget(self._record_btn)
        self.add_widget(self._text_input)
        self.add_widget(self._send_btn)

    # ── 业务逻辑（完整保留）──
    def _on_send_pressed(self, instance=None):
        text = self._text_input.text.strip()
        if text and self._on_send:
            self._on_send(text)
            self._text_input.text = ''

    def _on_record_btn_press(self, instance):
        self._record_bg.color[:] = BTN_RECORD_ACTIVE
        if self._on_record_press:
            self._on_record_press()

    def _on_record_btn_release(self, instance):
        self._record_bg.color[:] = BTN_RECORD
        if self._on_record_release:
            self._on_record_release()

    def _update_record_bg(self, instance, value):
        self._record_bg.pos = instance.pos
        self._record_bg.size = instance.size

    def _update_send_bg(self, instance, value):
        self._send_bg.pos = instance.pos
        self._send_bg.size = instance.size

    def _update_input_rect(self, instance, value):
        self._input_rect.pos = instance.pos
        self._input_rect.size = instance.size

    @property
    def text_input(self):
        return self._text_input


class ChatScreen(Screen):
    """主对话框页面"""

    def __init__(self, app=None, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._message_queue = []
        self._is_processing = False
        self._build_ui()

    def _build_ui(self):
        self.clear_widgets()

        # 根布局（浅灰页面背景）
        self._root = BoxLayout(orientation='vertical')
        with self.canvas.before:
            Color(*BG_PAGE)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        # ── 顶部状态栏（网络异常横幅，默认隐藏）──
        self._status_banner = StatusBanner()

        # ── 导航栏 ──
        nav_bar = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=NAV_BAR_HEIGHT,
            padding=(PADDING_X, 0, PADDING_X, 0),
        )
        with nav_bar.canvas.before:
            Color(*BG_CARD)
            self._nav_rect = Rectangle(pos=nav_bar.pos, size=nav_bar.size)
        nav_bar.bind(pos=self._update_nav_bg, size=self._update_nav_bg)

        nav_bar.add_widget(Label(
            text='店小二',
            font_size=FONT_TITLE,
            color=TEXT_PRIMARY,
            bold=True,
            size_hint_x=1,
            halign='left',
            valign='middle',
        ))
        settings_btn = Button(
            text='设置',
            font_size=FONT_SMALL,
            color=PRIMARY_ORANGE,
            background_color=(0, 0, 0, 0),
            size_hint_x=None,
            width=56,
            size_hint_y=None,
            height=NAV_BAR_HEIGHT,
        )
        settings_btn.background_normal = ''
        settings_btn.background_down = ''
        settings_btn.bind(on_press=self._on_settings_pressed)
        nav_bar.add_widget(settings_btn)

        # ── 导航栏底部分隔线 ──
        nav_sep = BoxLayout(size_hint_y=None, height=1)
        with nav_sep.canvas.before:
            Color(*DIVIDER)
            Rectangle(pos=nav_sep.pos, size=nav_sep.size)
        nav_sep.bind(
            pos=lambda i, v: setattr(nav_sep.canvas.children[-1], 'pos', i.pos),
            size=lambda i, v: setattr(nav_sep.canvas.children[-1], 'size', i.size),
        )

        # ── 对话区域（可滚动）──
        self._scroll = ScrollView(
            size_hint_y=1,
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=4,
            bar_color=TEXT_HINT,
            scroll_type=['content', 'bars'],
        )

        self._chat_list = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            padding=(PADDING_X, PADDING_Y, PADDING_X, PADDING_Y),
            spacing=MARGIN_BUBBLE,
        )
        self._chat_list.bind(minimum_height=self._chat_list.setter('height'))
        self._scroll.add_widget(self._chat_list)

        # ── 底部输入栏上方的分隔线 ──
        input_sep = BoxLayout(size_hint_y=None, height=1)
        with input_sep.canvas.before:
            Color(*DIVIDER)
            Rectangle(pos=input_sep.pos, size=input_sep.size)
        input_sep.bind(
            pos=lambda i, v: setattr(input_sep.canvas.children[-1], 'pos', i.pos),
            size=lambda i, v: setattr(input_sep.canvas.children[-1], 'size', i.size),
        )

        # ── 底部输入栏 ──
        self._input_bar = InputBar(
            on_send=self._on_user_send,
            on_record_press=self._on_record_press,
            on_record_release=self._on_record_release,
        )

        # ── 键盘自适应 ──
        from kivy.core.window import Window
        Window.softinput_mode = 'below_target'

        # ── 组装 ──
        self._root.add_widget(self._status_banner)
        self._root.add_widget(nav_bar)
        self._root.add_widget(nav_sep)
        self._root.add_widget(self._scroll)
        self._root.add_widget(input_sep)
        self._root.add_widget(self._input_bar)
        self.add_widget(self._root)

        Clock.schedule_interval(self._check_network, 5)

    def _update_bg(self, instance, value):
        self._bg_rect.pos = instance.pos
        self._bg_rect.size = instance.size

    def _update_nav_bg(self, instance, value):
        self._nav_rect.pos = instance.pos
        self._nav_rect.size = instance.size

    # ══════════════════════════════════════════════
    # 以下业务逻辑全部保留不变
    # ══════════════════════════════════════════════

    def add_message(self, text, is_user=False, is_changnuo=False):
        timestamp = time.strftime('%H:%M')
        bubble = ChatBubble(
            text=text, is_user=is_user, is_changnuo=is_changnuo, timestamp=timestamp,
        )
        self._chat_list.add_widget(bubble)
        Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.1)

    def _scroll_to_bottom(self):
        self._scroll.scroll_y = 0

    def _on_user_send(self, text):
        if not text:
            return
        self.add_message(text, is_user=True)
        from brain import get_network_status
        if not get_network_status():
            self._message_queue.append(text)
            self._status_banner.show()
            self.add_message('消息已保存，网络恢复后自动处理', is_user=False)
            return
        self._process_message(text)

    def _process_message(self, text):
        self._is_processing = True
        self.add_message('正在处理...', is_user=False)
        import threading
        def _worker():
            from brain import dispatch
            try:
                result = dispatch(text)
                Clock.schedule_once(lambda dt: self._on_dispatch_done(result), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_dispatch_error(str(e)), 0)
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _on_dispatch_done(self, result):
        self._is_processing = False
        if result is None:
            self.add_message('处理失败，请重试', is_user=False)
            return
        chat_text = result.get('chat', '')
        changnuo_text = result.get('changnuo')
        if chat_text:
            self.add_message(chat_text, is_user=False)
        if changnuo_text:
            self.add_message(changnuo_text, is_user=False, is_changnuo=True)
            try:
                from skills.xfyun_tts import speak
                speak(changnuo_text)
            except Exception:
                pass

    def _on_dispatch_error(self, error_msg):
        self._is_processing = False
        self.add_message(f'出错了：{error_msg}', is_user=False)

    def _check_network(self, dt):
        from brain import get_network_status
        if get_network_status():
            if self._status_banner._visible:
                self._status_banner.hide()
                self.add_message('网络已恢复', is_user=False)
                self._process_queue()
        else:
            if self._message_queue:
                self._status_banner.show('网络不可用，消息待处理')

    def _process_queue(self):
        if not self._message_queue or self._is_processing:
            return
        text = self._message_queue.pop(0)
        self._process_message(text)
        Clock.schedule_once(lambda dt: self._process_queue(), 2)

    def _on_settings_pressed(self, instance):
        if self.app:
            self.app.open_settings()

    def _on_record_press(self):
        try:
            from skills.xfyun_asr import start_recording
            start_recording()
        except Exception:
            self.add_message('[语音输入不可用]', is_user=True)

    def _on_record_release(self):
        try:
            from skills.xfyun_asr import stop_recording
            text = stop_recording()
            if text:
                self._input_bar.text_input.text = text
            else:
                self.add_message('未识别到内容', is_user=False)
        except Exception as e:
            self.add_message(f'语音识别出错：{e}', is_user=False)

    def on_pre_enter(self):
        Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.2)

    def on_pre_leave(self):
        try:
            from skills.xfyun_tts import shutdown_tts
            shutdown_tts()
        except Exception:
            pass
