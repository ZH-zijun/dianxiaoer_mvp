"""
ui/chat_screen.py — 店小二主对话框

规范来源：
- project_start.md 第六节第3款（主对话框）
- UI 设计约束：深色背景、对话气泡、唱诺醒目、底部固定输入区、网络状态栏

功能：
- 对话气泡列表：用户（白色/浅灰底+深色字）、AI（深色底+白字）
- 唱诺文案：橙色 22sp，明显样式区分普通对话
- 底部固定输入区：文字输入框 + 录音按钮（>= 48dp）
- 顶部红色状态栏：网络中断时显示"网络不可用，消息待处理"
- 对话区域可滚动，占据底部输入区上方所有空间
- 键盘弹出时自动适应，不被遮挡
- 网络恢复后逐条处理堆积消息，不补唱诺
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.stacklayout import StackLayout
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.graphics import Color, RoundedRectangle
import time

from ui import (
    BG_DARK, BG_CARD, BG_INPUT,
    BUBBLE_USER, BUBBLE_USER_TEXT, BUBBLE_AI, BUBBLE_AI_TEXT,
    CHANGNUO_COLOR, CHANGNUO_BG,
    STATUS_BAR_RED,
    BTN_PRIMARY, BTN_PRIMARY_TEXT, BTN_RECORD, BTN_RECORD_ACTIVE, BTN_TEXT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_HINT, TEXT_ERROR, TEXT_SUCCESS,
    DIVIDER,
    FONT_TITLE, FONT_CHANGNUO, FONT_CHAT, FONT_CHAT_SMALL,
    FONT_BTN, FONT_BTN_LARGE, FONT_INPUT, FONT_HINT, FONT_STATUS,
    PADDING_X, PADDING_Y, PADDING_SMALL, PADDING_LARGE,
    MARGIN_BUBBLE,
    BTN_HEIGHT, BTN_RECORD_SIZE, INPUT_HEIGHT, STATUS_BAR_HEIGHT,
    BUBBLE_RADIUS, BUBBLE_MAX_WIDTH,
    ANIM_DURATION,
)


class ChatBubble(BoxLayout):
    """单条对话气泡组件"""

    def __init__(self, text='', is_user=False, is_changnuo=False,
                 timestamp='', **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.height = self.minimum_height

        # ── 发送者标签 + 时间 ──
        if is_user:
            sender_text = '我'
            sender_color = TEXT_SECONDARY
            align = 'right'
        else:
            sender_text = '店小二'
            sender_color = TEXT_SECONDARY
            align = 'left'

        header = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=20,
            spacing=PADDING_SMALL,
        )

        sender_label = Label(
            text=sender_text,
            font_size=FONT_CHAT_SMALL - 2,
            color=sender_color,
            size_hint_x=None,
            width=len(sender_text) * 12 + 10,
        )

        time_label = Label(
            text=timestamp,
            font_size=FONT_CHAT_SMALL - 2,
            color=TEXT_HINT,
            halign='right' if is_user else 'left',
        )

        if is_user:
            header.add_widget(time_label)
            header.add_widget(Label(size_hint_x=1))  # spacer
            header.add_widget(sender_label)
        else:
            header.add_widget(sender_label)
            header.add_widget(Label(size_hint_x=1))  # spacer
            header.add_widget(time_label)

        # ── 气泡主体 ──
        bubble = BoxLayout(
            orientation='vertical',
            padding=(PADDING_X, PADDING_SMALL),
            size_hint_y=None,
            size_hint_x=BUBBLE_MAX_WIDTH,
        )

        if is_user:
            bubble.pos_hint = {'right': 1}
            bubble_bg = BUBBLE_USER
            bubble_text_color = BUBBLE_USER_TEXT
        elif is_changnuo:
            bubble_bg = CHANGNUO_BG
            bubble_text_color = CHANGNUO_COLOR
        else:
            bubble_bg = BUBBLE_AI
            bubble_text_color = BUBBLE_AI_TEXT

        # 气泡圆角背景
        with bubble.canvas.before:
            Color(*bubble_bg)
            self._bubble_rect = RoundedRectangle(
                pos=bubble.pos,
                size=bubble.size,
                radius=[BUBBLE_RADIUS, BUBBLE_RADIUS,
                        BUBBLE_RADIUS, BUBBLE_RADIUS],
            )
        bubble.bind(pos=self._update_bubble, size=self._update_bubble)

        # 文字标签
        if is_changnuo:
            # 唱诺文案：醒目样式
            # 添加小铃铛前缀标识
            display_text = f'[ {text} ]'
            bubble_label = Label(
                text=display_text,
                font_size=FONT_CHANGNUO,
                color=bubble_text_color,
                bold=True,
                halign='left',
                valign='middle',
                text_size=(None, None),
                markup=False,
            )
        else:
            bubble_label = Label(
                text=text,
                font_size=FONT_CHAT,
                color=bubble_text_color,
                halign='left',
                valign='middle',
                text_size=(None, None),
                markup=False,
            )

        bubble_label.bind(
            texture_size=lambda inst, val: setattr(bubble, 'minimum_height', val[1] + PADDING_SMALL * 2),
        )
        bubble.add_widget(bubble_label)

        # ── 组装 ──
        self.add_widget(header)
        self.add_widget(bubble)

        # 初次布局后刷新高度
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
        self.color = BTN_TEXT
        self.halign = 'center'
        self.size_hint_y = None
        self.height = 0  # 默认隐藏
        self.bold = True
        self._visible = False

        with self.canvas.before:
            Color(*STATUS_BAR_RED)
            self._rect = RoundedRectangle(
                pos=self.pos, size=self.size,
                radius=[0, 0, 0, 0],
            )
        self.bind(pos=self._update_rect, size=self._update_rect)

    def show(self, msg='网络不可用，消息待处理'):
        """显示红色状态栏"""
        self.text = msg
        self.height = STATUS_BAR_HEIGHT
        self._visible = True

    def hide(self):
        """隐藏状态栏"""
        self.text = ''
        self.height = 0
        self._visible = False

    def _update_rect(self, instance, value):
        self._rect.pos = instance.pos
        self._rect.size = instance.size


class InputBar(BoxLayout):
    """底部输入栏：输入框 + 录音按钮 + 发送按钮"""

    def __init__(self, on_send=None, on_record_press=None, on_record_release=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.padding = (PADDING_SMALL, PADDING_SMALL, 0, PADDING_SMALL)
        self.spacing = PADDING_SMALL
        self.size_hint_y = None
        self.height = BTN_HEIGHT + PADDING_SMALL * 2
        self._on_send = on_send
        self._on_record_press = on_record_press
        self._on_record_release = on_record_release

        # ── 录音按钮（左侧）──
        self._record_btn = Button(
            text='\U0001F3A4',  # 麦克风 emoji
            font_size=20,
            color=BTN_TEXT,
            background_color=BTN_RECORD,
            size_hint_x=None,
            width=BTN_RECORD_SIZE,
            size_hint_y=None,
            height=BTN_RECORD_SIZE,
        )
        self._record_btn.bind(
            on_press=self._on_record_btn_press,
            on_release=self._on_record_btn_release,
        )
        # 圆角
        self._record_btn.background_normal = ''
        self._record_btn.background_down = ''
        with self._record_btn.canvas.before:
            Color(*BTN_RECORD)
            self._record_bg = RoundedRectangle(
                pos=self._record_btn.pos,
                size=self._record_btn.size,
                radius=[BTN_RECORD_SIZE / 2,],
            )
        self._record_btn.bind(
            pos=self._update_record_bg,
            size=self._update_record_bg,
        )

        # ── 文字输入框 ──
        self._text_input = TextInput(
            hint_text='说点什么...',
            font_size=FONT_INPUT,
            background_color=BG_INPUT,
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_HINT,
            cursor_color=TEXT_PRIMARY,
            padding=(PADDING_X, (BTN_HEIGHT - FONT_INPUT) / 2),
            multiline=False,
            size_hint_y=None,
            height=BTN_HEIGHT,
            write_tab=False,
        )
        self._text_input.bind(on_text_validate=self._on_send_pressed)

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
        # 圆角
        self._send_btn.background_normal = ''
        self._send_btn.background_down = ''
        with self._send_btn.canvas.before:
            Color(*BTN_PRIMARY)
            self._send_bg = RoundedRectangle(
                pos=self._send_btn.pos,
                size=self._send_btn.size,
                radius=[BUBBLE_RADIUS,],
            )
        self._send_btn.bind(
            pos=self._update_send_bg,
            size=self._update_send_bg,
        )

        self.add_widget(self._record_btn)
        self.add_widget(self._text_input)
        self.add_widget(self._send_btn)

    def _on_send_pressed(self, instance=None):
        """发送按钮/回车键"""
        text = self._text_input.text.strip()
        if text and self._on_send:
            self._on_send(text)
            self._text_input.text = ''

    def _on_record_btn_press(self, instance):
        """录音按钮按下"""
        # 变色提示正在录音
        Color(*BTN_RECORD_ACTIVE)
        self._record_bg.color = BTN_RECORD_ACTIVE
        if self._on_record_press:
            self._on_record_press()

    def _on_record_btn_release(self, instance):
        """录音按钮松开"""
        Color(*BTN_RECORD)
        self._record_bg.color = BTN_RECORD
        if self._on_record_release:
            self._on_record_release()

    def _update_record_bg(self, instance, value):
        self._record_bg.pos = instance.pos
        self._record_bg.size = instance.size

    def _update_send_bg(self, instance, value):
        self._send_bg.pos = instance.pos
        self._send_bg.size = instance.size

    @property
    def text_input(self):
        return self._text_input


class ChatScreen(Screen):
    """主对话框页面"""

    def __init__(self, app=None, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._message_queue = []       # 离线堆积消息
        self._is_processing = False    # 是否正在处理消息
        self._build_ui()

    def _build_ui(self):
        """构建主对话框界面"""
        self.clear_widgets()

        # 根布局 — 垂直：状态栏 + 对话区 + 输入栏
        self._root = BoxLayout(orientation='vertical')

        # ── 顶部状态栏（网络中断提示）──
        self._status_banner = StatusBanner()

        # ── 顶部标题栏 ──
        title_bar = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=50,
            padding=(PADDING_X, 0),
        )
        title_bar.add_widget(Label(
            text='店小二',
            font_size=FONT_TITLE,
            color=TEXT_PRIMARY,
            bold=True,
            size_hint_x=1,
            halign='left',
            valign='middle',
        ))

        # 设置按钮（右上角）
        settings_btn = Button(
            text='\u2699',  # 齿轮符号
            font_size=FONT_CHAT + 4,
            color=TEXT_SECONDARY,
            background_color=(0, 0, 0, 0),  # 透明背景
            size_hint_x=None,
            width=50,
            size_hint_y=None,
            height=50,
        )
        settings_btn.bind(on_press=self._on_settings_pressed)
        title_bar.add_widget(settings_btn)

        # ── 分隔线 ──
        from kivy.graphics import Color, Rectangle
        sep = BoxLayout(size_hint_y=None, height=1)
        with sep.canvas.before:
            Color(*DIVIDER)
            Rectangle(pos=sep.pos, size=sep.size)
        sep.bind(pos=lambda i, v: setattr(sep.canvas.children[1] if sep.canvas.children else None, 'pos', v),
                 size=lambda i, v: setattr(sep.canvas.children[1] if sep.canvas.children else None, 'size', v))

        # ── 对话区域（可滚动）──
        self._scroll = ScrollView(
            size_hint_y=1,  # 占据所有剩余空间
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=4,
            bar_color=DIVIDER,
            scroll_type=['content', 'bars'],
        )

        self._chat_list = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            padding=(PADDING_X, PADDING_Y),
            spacing=MARGIN_BUBBLE,
        )
        self._chat_list.bind(
            minimum_height=self._chat_list.setter('height')
        )

        self._scroll.add_widget(self._chat_list)

        # ── 底部分隔线 ──
        sep_bottom = BoxLayout(size_hint_y=None, height=1)
        with sep_bottom.canvas.before:
            Color(*DIVIDER)
            Rectangle(pos=sep_bottom.pos, size=sep_bottom.size)
        sep_bottom.bind(
            pos=lambda i, v: setattr(sep_bottom.canvas.children[1] if sep_bottom.canvas.children else None, 'pos', v),
            size=lambda i, v: setattr(sep_bottom.canvas.children[1] if sep_bottom.canvas.children else None, 'size', v),
        )

        # ── 底部输入栏 ──
        self._input_bar = InputBar(
            on_send=self._on_user_send,
            on_record_press=self._on_record_press,
            on_record_release=self._on_record_release,
        )

        # ── 键盘自适应（全局设置已在 main.py on_start() 生效，此处为兼容保留）──
        from kivy.core.window import Window
        Window.softinput_mode = 'below_target'

        # ── 组装 ──
        self._root.add_widget(self._status_banner)
        self._root.add_widget(title_bar)
        self._root.add_widget(sep)
        self._root.add_widget(self._scroll)
        self._root.add_widget(sep_bottom)
        self._root.add_widget(self._input_bar)

        self.add_widget(self._root)

        # 定期检查网络状态
        Clock.schedule_interval(self._check_network, 5)

    def add_message(self, text, is_user=False, is_changnuo=False):
        """
        添加一条消息到对话列表。

        Args:
            text: 消息文本
            is_user: 是否为用户消息
            is_changnuo: 是否为唱诺文案（醒目样式）
        """
        timestamp = time.strftime('%H:%M')
        bubble = ChatBubble(
            text=text,
            is_user=is_user,
            is_changnuo=is_changnuo,
            timestamp=timestamp,
        )
        self._chat_list.add_widget(bubble)
        # 滚动到底部
        Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.1)

    def _scroll_to_bottom(self):
        """滚动到对话区底部"""
        if self._scroll.scroll_y <= 0.01:
            self._scroll.scroll_y = 0
        else:
            self._scroll.scroll_y = 0

    def _on_user_send(self, text):
        """用户发送消息"""
        if not text:
            return

        # 添加用户气泡
        self.add_message(text, is_user=True)

        # 检查网络状态
        from brain import get_network_status
        if not get_network_status():
            # 离线：堆积消息
            self._message_queue.append(text)
            self._status_banner.show()
            self.add_message('消息已保存，网络恢复后自动处理', is_user=False)
            return

        # 在线：调度处理
        self._process_message(text)

    def _process_message(self, text):
        """调度处理用户消息"""
        self._is_processing = True
        self.add_message('正在处理...', is_user=False)

        # 用线程处理，避免阻塞 UI
        import threading
        def _worker():
            from brain import dispatch
            try:
                result = dispatch(text)
                # 回到主线程更新 UI
                Clock.schedule_once(lambda dt: self._on_dispatch_done(result), 0)
            except Exception as e:
                Clock.schedule_once(
                    lambda dt: self._on_dispatch_error(str(e)), 0
                )

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _on_dispatch_done(self, result):
        """调度完成，更新 UI"""
        self._is_processing = False

        if result is None:
            self.add_message('处理失败，请重试', is_user=False)
            return

        chat_text = result.get('chat', '')
        changnuo_text = result.get('changnuo')

        # 显示 AI 回复
        if chat_text:
            self.add_message(chat_text, is_user=False)

        # 显示唱诺文案（醒目样式）
        if changnuo_text:
            self.add_message(changnuo_text, is_user=False, is_changnuo=True)

            # 调用 TTS 播放唱诺（异步，不阻塞 UI）
            try:
                from skills.xfyun_tts import speak
                speak(changnuo_text)
            except Exception:
                pass  # TTS 不可用时静默降级

    def _on_dispatch_error(self, error_msg):
        """调度出错"""
        self._is_processing = False
        self.add_message(f'出错了：{error_msg}', is_user=False)

    def _check_network(self, dt):
        """定期检查网络状态"""
        from brain import get_network_status
        if get_network_status():
            # 网络恢复
            if self._status_banner._visible:
                self._status_banner.hide()
                self.add_message('网络已恢复', is_user=False)
                # 逐条处理堆积消息
                self._process_queue()
        else:
            # 网络中断
            if self._message_queue:
                self._status_banner.show('网络不可用，消息待处理')

    def _process_queue(self):
        """逐条处理堆积消息（网络恢复后，不补唱诺）"""
        if not self._message_queue or self._is_processing:
            return

        text = self._message_queue.pop(0)
        self._process_message(text)

        # 处理完当前后，继续处理下一条
        Clock.schedule_once(lambda dt: self._process_queue(), 2)

    def _on_settings_pressed(self, instance):
        """打开设置页"""
        if self.app:
            self.app.open_settings()

    def _on_record_press(self):
        """录音按钮按下"""
        try:
            from skills.xfyun_asr import start_recording
            start_recording()
        except Exception:
            self.add_message('[语音输入不可用]', is_user=True)

    def _on_record_release(self):
        """录音按钮松开"""
        try:
            from skills.xfyun_asr import stop_recording
            text = stop_recording()
            if text:
                # 将识别结果填入输入框（不直接发送）
                self._input_bar.text_input.text = text
            else:
                self.add_message('未识别到内容', is_user=False)
        except Exception as e:
            self.add_message(f'语音识别出错：{e}', is_user=False)

    def on_pre_enter(self):
        """每次进入时刷新"""
        Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.2)

    def on_pre_leave(self):
        """离开页面时释放 TTS 资源"""
        try:
            from skills.xfyun_tts import shutdown_tts
            shutdown_tts()
        except Exception:
            pass
