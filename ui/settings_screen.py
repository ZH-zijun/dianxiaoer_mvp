"""
ui/settings_screen.py — 店小二设置页

规范来源：
- project_start.md 第六节第7款（设置页）
- project_start.md 第三节（功能范围 P0：设置页）

功能：
- 【账户安全】修改密码
- 【大模型配置】主API地址、Key、模型名、备用API地址、Key
- 【偏好】语音唱诺开关、方言模式切换
- 【数据管理】导出加密备份、导入恢复、重置所有数据
- 【关于】版本号、试用倒计时
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.togglebutton import ToggleButton
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle

import os

from ui import (
    BG_DARK, BG_CARD, BG_INPUT,
    BTN_PRIMARY, BTN_PRIMARY_TEXT, BTN_TEXT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_HINT, TEXT_ERROR, TEXT_SUCCESS,
    DIVIDER,
    FONT_TITLE, FONT_CHAT, FONT_CHAT_SMALL, FONT_BTN, FONT_BTN_LARGE,
    FONT_INPUT, FONT_HINT, FONT_STATUS,
    PADDING_X, PADDING_Y, PADDING_SMALL, PADDING_LARGE,
    BTN_HEIGHT, BUBBLE_RADIUS,
    ANIM_DURATION,
)


class SectionHeader(Label):
    """设置页分区标题"""

    def __init__(self, text='', **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.font_size = FONT_CHAT
        self.color = TEXT_PRIMARY
        self.bold = True
        self.size_hint_y = None
        self.height = 36
        self.halign = 'left'
        self.valign = 'middle'


class SettingRow(BoxLayout):
    """设置行：标签 + 控件"""

    def __init__(self, label='', widget=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = BTN_HEIGHT + PADDING_SMALL
        self.padding = (0, PADDING_SMALL // 2)
        self.spacing = PADDING_SMALL

        lbl = Label(
            text=label,
            font_size=FONT_CHAT_SMALL,
            color=TEXT_PRIMARY,
            size_hint_x=None,
            width=100,
            halign='left',
            valign='middle',
        )
        self.add_widget(lbl)

        if widget:
            self.add_widget(widget)
        else:
            self.add_widget(Label(size_hint_x=1))  # spacer


class SettingsScreen(Screen):
    """设置页面"""

    def __init__(self, app=None, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._popup = None
        self._build_ui()

    def _build_ui(self):
        """构建设置界面"""
        self.clear_widgets()

        # 根布局
        root = BoxLayout(orientation='vertical')

        # ── 顶部标题栏 ──
        title_bar = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=50,
            padding=(PADDING_X, 0),
        )
        back_btn = Button(
            text='<',
            font_size=FONT_CHAT + 8,
            color=TEXT_PRIMARY,
            background_color=(0, 0, 0, 0),
            size_hint_x=None,
            width=50,
            size_hint_y=None,
            height=50,
        )
        back_btn.bind(on_press=self._on_back)
        title_bar.add_widget(back_btn)

        title_bar.add_widget(Label(
            text='设置',
            font_size=FONT_TITLE,
            color=TEXT_PRIMARY,
            bold=True,
            size_hint_x=1,
            halign='center',
            valign='middle',
        ))

        title_bar.add_widget(Label(size_hint_x=None, width=50))  # balance

        # 分隔线
        sep = BoxLayout(size_hint_y=None, height=1)
        with sep.canvas.before:
            Color(*DIVIDER)
            from kivy.graphics import Rectangle
            self._sep_rect = Rectangle(pos=sep.pos, size=sep.size)
        sep.bind(pos=self._update_sep, size=self._update_sep)

        # ── 可滚动内容区 ──
        scroll = ScrollView(
            size_hint_y=1,
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=4,
        )

        content = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            padding=(PADDING_X, PADDING_Y),
            spacing=PADDING_SMALL,
        )
        content.bind(minimum_height=content.setter('height'))

        # ══════════════════════════════════
        # 【账户安全】
        # ══════════════════════════════════
        content.add_widget(SectionHeader(text='账户安全'))

        change_pwd_btn = Button(
            text='修改密码',
            font_size=FONT_CHAT_SMALL,
            color=TEXT_PRIMARY,
            background_color=BG_INPUT,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        change_pwd_btn.bind(on_press=self._on_change_password)
        content.add_widget(change_pwd_btn)

        # ══════════════════════════════════
        # 【大模型配置】
        # ══════════════════════════════════
        content.add_widget(SectionHeader(text='大模型配置'))

        # 主 API 地址
        content.add_widget(SettingRow(
            label='API 地址',
            widget=self._make_input('llm_api_url', hint='https://api.deepseek.com/v1/chat/completions'),
        ))

        # 主 API Key
        content.add_widget(SettingRow(
            label='API Key',
            widget=self._make_input('llm_api_key', hint='sk-...', password=True),
        ))

        # 模型名
        content.add_widget(SettingRow(
            label='模型名',
            widget=self._make_input('llm_model', hint='deepseek-chat'),
        ))

        # 备用 API 地址
        content.add_widget(SettingRow(
            label='备用地址',
            widget=self._make_input('llm_backup_url', hint='（可选）'),
        ))

        # 备用 API Key
        content.add_widget(SettingRow(
            label='备用Key',
            widget=self._make_input('llm_backup_key', hint='（可选）', password=True),
        ))

        save_llm_btn = Button(
            text='保存大模型配置',
            font_size=FONT_CHAT_SMALL,
            color=BTN_PRIMARY_TEXT,
            background_color=BTN_PRIMARY,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        save_llm_btn.bind(on_press=self._on_save_llm)
        content.add_widget(save_llm_btn)

        # ══════════════════════════════════
        # 【偏好】
        # ══════════════════════════════════
        content.add_widget(SectionHeader(text='偏好'))

        # 语音唱诺开关
        self._voice_toggle = ToggleButton(
            text='语音唱诺：开',
            font_size=FONT_CHAT_SMALL,
            color=TEXT_PRIMARY,
            background_color=BG_INPUT,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        self._voice_toggle.bind(on_press=self._on_voice_toggle)
        content.add_widget(self._voice_toggle)

        # 方言模式切换
        self._dialect_toggle = ToggleButton(
            text='东北话模式：开',
            font_size=FONT_CHAT_SMALL,
            color=TEXT_PRIMARY,
            background_color=BG_INPUT,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        self._dialect_toggle.bind(on_press=self._on_dialect_toggle)
        content.add_widget(self._dialect_toggle)

        # ══════════════════════════════════
        # 【数据管理】
        # ══════════════════════════════════
        content.add_widget(SectionHeader(text='数据管理'))

        backup_btn = Button(
            text='导出加密备份',
            font_size=FONT_CHAT_SMALL,
            color=TEXT_PRIMARY,
            background_color=BG_INPUT,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        backup_btn.bind(on_press=self._on_export_backup)
        content.add_widget(backup_btn)

        restore_btn = Button(
            text='导入恢复备份',
            font_size=FONT_CHAT_SMALL,
            color=TEXT_PRIMARY,
            background_color=BG_INPUT,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        restore_btn.bind(on_press=self._on_import_backup)
        content.add_widget(restore_btn)

        reset_btn = Button(
            text='重置所有数据',
            font_size=FONT_CHAT_SMALL,
            color=TEXT_ERROR,
            background_color=BG_INPUT,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        reset_btn.bind(on_press=self._on_reset_data)
        content.add_widget(reset_btn)

        # ══════════════════════════════════
        # 【关于】
        # ══════════════════════════════════
        content.add_widget(SectionHeader(text='关于'))

        self._version_label = Label(
            text='店小二 V1.0 MVP',
            font_size=FONT_HINT,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=24,
            halign='left',
        )
        content.add_widget(self._version_label)

        self._trial_label = Label(
            text='',
            font_size=FONT_HINT,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=24,
            halign='left',
        )
        content.add_widget(self._trial_label)

        # 占位底部
        content.add_widget(Label(size_hint_y=None, height=40))

        scroll.add_widget(content)

        # ── 组装 ──
        root.add_widget(title_bar)
        root.add_widget(sep)
        root.add_widget(scroll)

        self.add_widget(root)

        # 加载当前设置
        Clock.schedule_once(lambda dt: self._load_settings(), 0.2)

    def _update_sep(self, instance, value):
        self._sep_rect.pos = instance.pos
        self._sep_rect.size = instance.size

    def _make_input(self, setting_key, hint='', password=False):
        """创建设置输入框"""
        inp = TextInput(
            hint_text=hint,
            font_size=FONT_CHAT_SMALL,
            background_color=BG_INPUT,
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_HINT,
            password=password,
            multiline=False,
            size_hint_y=None,
            height=BTN_HEIGHT,
            write_tab=False,
        )
        inp.setting_key = setting_key  # 附加属性，方便保存时获取
        return inp

    def _load_settings(self):
        """加载当前设置到 UI"""
        from data.db import get_setting

        # 大模型配置
        for child in self.children[0].children[2].children[0].children:
            if isinstance(child, SettingRow) and hasattr(child.children[-1], 'setting_key'):
                inp = child.children[-1]
                if isinstance(inp, TextInput):
                    val = get_setting(inp.setting_key) or ''
                    inp.text = val

        # 语音开关
        voice = get_setting('voice_enabled')
        if voice is None or voice == '1' or voice == 1:
            self._voice_toggle.state = 'normal'
            self._voice_toggle.text = '语音唱诺：开'
        else:
            self._voice_toggle.state = 'down'
            self._voice_toggle.text = '语音唱诺：关'

        # 方言模式
        dialect = get_setting('dialect_mode')
        if dialect is None or dialect != 'standard':
            self._dialect_toggle.state = 'normal'
            self._dialect_toggle.text = '东北话模式：开'
        else:
            self._dialect_toggle.state = 'down'
            self._dialect_toggle.text = '东北话模式：关'

        # 试用信息
        trial_end = get_setting('trial_end_date')
        if trial_end:
            from datetime import datetime, date
            try:
                end = datetime.strptime(trial_end, '%Y-%m-%d').date()
                remaining = (end - date.today()).days
                if remaining > 0:
                    self._trial_label.text = f'试用版，剩余 {remaining} 天'
                    self._trial_label.color = TEXT_SECONDARY
                else:
                    self._trial_label.text = '试用期已到期'
                    self._trial_label.color = TEXT_ERROR
            except ValueError:
                self._trial_label.text = '试用版'
        else:
            self._trial_label.text = '正式版'

    def _save_input(self, inp):
        """保存单个输入框的值到数据库"""
        from data.db import set_setting
        set_setting(inp.setting_key, inp.text.strip())

    def _on_save_llm(self, instance):
        """保存大模型配置"""
        from data.db import set_setting, get_setting
        from data.db import _get_conn, _db_lock

        # 遍历设置行，保存输入框值
        # 直接从 setting_key 获取
        for key in ['llm_api_url', 'llm_api_key', 'llm_model', 'llm_backup_url', 'llm_backup_key']:
            val = get_setting(key)
            # 需要遍历子组件找到对应的 TextInput
        # 简化方式：直接从所有 TextInput 收集
        self._collect_and_save_inputs()

        self._show_toast('大模型配置已保存')

    def _collect_and_save_inputs(self):
        """收集所有带 setting_key 的 TextInput 并保存"""
        from data.db import set_setting

        # 递归查找所有 TextInput
        def find_inputs(widget):
            inputs = []
            if hasattr(widget, 'children'):
                for child in widget.children:
                    if isinstance(child, TextInput) and hasattr(child, 'setting_key'):
                        inputs.append(child)
                    inputs.extend(find_inputs(child))
            return inputs

        inputs = find_inputs(self)
        for inp in inputs:
            set_setting(inp.setting_key, inp.text.strip())

    def _on_voice_toggle(self, instance):
        """语音开关切换"""
        from data.db import set_setting

        if instance.state == 'normal':
            set_setting('voice_enabled', '1')
            instance.text = '语音唱诺：开'
        else:
            set_setting('voice_enabled', '0')
            instance.text = '语音唱诺：关'

    def _on_dialect_toggle(self, instance):
        """方言模式切换"""
        from data.db import set_setting

        if instance.state == 'normal':
            set_setting('dialect_mode', 'dongbei')
            instance.text = '东北话模式：开'
        else:
            set_setting('dialect_mode', 'standard')
            instance.text = '东北话模式：关'

    def _on_change_password(self, instance):
        """修改密码"""
        self._show_password_popup()

    def _show_password_popup(self):
        """显示修改密码弹窗"""
        content = BoxLayout(
            orientation='vertical',
            padding=(PADDING_X, PADDING_Y),
            spacing=PADDING_SMALL,
            size_hint=(0.85, None),
        )
        content.minimum_height = 300

        content.add_widget(Label(
            text='修改密码',
            font_size=FONT_CHAT,
            color=TEXT_PRIMARY,
            bold=True,
            size_hint_y=None,
            height=32,
        ))

        content.add_widget(Label(
            text='当前密码：',
            font_size=FONT_HINT,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=22,
            halign='left',
        ))

        old_pwd = TextInput(
            password=True,
            font_size=FONT_INPUT,
            background_color=BG_INPUT,
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_HINT,
            size_hint_y=None,
            height=BTN_HEIGHT,
            multiline=False,
        )
        content.add_widget(old_pwd)

        content.add_widget(Label(
            text='新密码（至少6位）：',
            font_size=FONT_HINT,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=22,
            halign='left',
        ))

        new_pwd = TextInput(
            password=True,
            font_size=FONT_INPUT,
            background_color=BG_INPUT,
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_HINT,
            size_hint_y=None,
            height=BTN_HEIGHT,
            multiline=False,
        )
        content.add_widget(new_pwd)

        self._pwd_status = Label(
            text='',
            font_size=FONT_HINT,
            color=TEXT_ERROR,
            size_hint_y=None,
            height=22,
            halign='center',
        )
        content.add_widget(self._pwd_status)

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
        confirm_btn.bind(on_press=lambda i: self._do_change_password(old_pwd, new_pwd))

        cancel_btn = Button(
            text='取消',
            font_size=FONT_BTN,
            color=TEXT_PRIMARY,
            background_color=BG_INPUT,
        )
        cancel_btn.bind(on_press=lambda i: self._close_popup())

        btn_box.add_widget(confirm_btn)
        btn_box.add_widget(cancel_btn)
        content.add_widget(btn_box)

        self._popup = Popup(
            title='修改密码',
            content=content,
            size_hint=(0.85, None),
            height=380,
            background_color=BG_CARD,
            separator_color=DIVIDER,
            title_color=TEXT_PRIMARY,
            title_size=FONT_CHAT,
            auto_dismiss=False,
        )
        self._popup.open()

    def _do_change_password(self, old_inp, new_inp):
        """执行修改密码"""
        from auth import change_password

        old = old_inp.text.strip()
        new = new_inp.text.strip()

        if not old or not new:
            self._pwd_status.text = '密码不能为空'
            self._pwd_status.color = TEXT_ERROR
            return

        if len(new) < 6:
            self._pwd_status.text = '新密码至少6位'
            self._pwd_status.color = TEXT_ERROR
            return

        result = change_password(old, new)
        if result == 'ok':
            self._pwd_status.text = '密码修改成功！'
            self._pwd_status.color = TEXT_SUCCESS
            Clock.schedule_once(lambda dt: self._close_popup(), 0.8)
        elif result == 'wrong_old':
            self._pwd_status.text = '当前密码错误'
            self._pwd_status.color = TEXT_ERROR
        elif result == 'same_password':
            self._pwd_status.text = '新旧密码不能相同'
            self._pwd_status.color = TEXT_ERROR
        else:
            self._pwd_status.text = f'修改失败：{result}'
            self._pwd_status.color = TEXT_ERROR

    def _on_export_backup(self, instance):
        """导出加密备份"""
        self._show_backup_password_popup(export=True)

    def _on_import_backup(self, instance):
        """导入恢复备份"""
        self._show_backup_password_popup(export=False)

    def _show_backup_password_popup(self, export=True):
        """显示备份密码输入弹窗"""
        content = BoxLayout(
            orientation='vertical',
            padding=(PADDING_X, PADDING_Y),
            spacing=PADDING_SMALL,
            size_hint=(0.85, None),
        )
        content.minimum_height = 200

        title = '导出加密备份' if export else '导入恢复备份'
        content.add_widget(Label(
            text=title,
            font_size=FONT_CHAT,
            color=TEXT_PRIMARY,
            bold=True,
            size_hint_y=None,
            height=32,
        ))

        content.add_widget(Label(
            text='请输入密码：',
            font_size=FONT_HINT,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=22,
            halign='left',
        ))

        pwd_input = TextInput(
            password=True,
            font_size=FONT_INPUT,
            background_color=BG_INPUT,
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_HINT,
            size_hint_y=None,
            height=BTN_HEIGHT,
            multiline=False,
        )
        content.add_widget(pwd_input)

        self._backup_status = Label(
            text='',
            font_size=FONT_HINT,
            color=TEXT_ERROR,
            size_hint_y=None,
            height=22,
            halign='center',
        )
        content.add_widget(self._backup_status)

        btn_box = BoxLayout(
            orientation='horizontal',
            spacing=PADDING_SMALL,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        confirm_btn = Button(
            text='确认',
            font_size=FONT_BTN,
            color=BTN_PRIMARY_TEXT,
            background_color=BTN_PRIMARY,
        )
        if export:
            confirm_btn.bind(on_press=lambda i: self._do_export(pwd_input))
        else:
            confirm_btn.bind(on_press=lambda i: self._do_import(pwd_input))

        cancel_btn = Button(
            text='取消',
            font_size=FONT_BTN,
            color=TEXT_PRIMARY,
            background_color=BG_INPUT,
        )
        cancel_btn.bind(on_press=lambda i: self._close_popup())

        btn_box.add_widget(confirm_btn)
        btn_box.add_widget(cancel_btn)
        content.add_widget(btn_box)

        self._popup = Popup(
            title=title,
            content=content,
            size_hint=(0.85, None),
            height=280,
            background_color=BG_CARD,
            separator_color=DIVIDER,
            title_color=TEXT_PRIMARY,
            title_size=FONT_CHAT,
            auto_dismiss=False,
        )
        self._popup.open()

    def _do_export(self, pwd_input):
        """执行导出备份"""
        from utils.backup import export_backup

        password = pwd_input.text.strip()
        if not password:
            self._backup_status.text = '密码不能为空'
            self._backup_status.color = TEXT_ERROR
            return

        # 选择输出路径
        if self.app:
            output_dir = self.app.user_data_dir
        else:
            output_dir = os.path.expanduser('~')

        from datetime import datetime
        filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bbk"
        output_path = os.path.join(output_dir, filename)

        result = export_backup(password, output_path)

        if result == 'ok':
            self._backup_status.text = f'备份成功：{filename}'
            self._backup_status.color = TEXT_SUCCESS
            Clock.schedule_once(lambda dt: self._close_popup(), 1.5)
        else:
            self._backup_status.text = f'导出失败：{result}'
            self._backup_status.color = TEXT_ERROR

    def _do_import(self, pwd_input):
        """执行导入备份"""
        from utils.backup import import_backup

        password = pwd_input.text.strip()
        if not password:
            self._backup_status.text = '密码不能为空'
            self._backup_status.color = TEXT_ERROR
            return

        # 查找备份文件
        if self.app:
            backup_dir = self.app.user_data_dir
        else:
            backup_dir = os.path.expanduser('~')

        # 找最新的 .bbk 文件
        bbk_files = [
            f for f in os.listdir(backup_dir)
            if f.endswith('.bbk')
        ]

        if not bbk_files:
            self._backup_status.text = '未找到备份文件'
            self._backup_status.color = TEXT_ERROR
            return

        # 使用最新的备份文件
        bbk_files.sort(reverse=True)
        backup_path = os.path.join(backup_dir, bbk_files[0])

        result = import_backup(password, backup_path)

        if result == 'ok':
            self._backup_status.text = '恢复成功！请重新登录'
            self._backup_status.color = TEXT_SUCCESS
            Clock.schedule_once(lambda dt: self._restart_app(), 1.5)
        else:
            self._backup_status.text = f'恢复失败：{result}'
            self._backup_status.color = TEXT_ERROR

    def _on_reset_data(self, instance):
        """重置所有数据"""
        self._show_confirm_popup(
            '确认重置',
            '重置所有数据将清除全部订单、客户、品类等信息，恢复默认密码。\n\n此操作不可撤销！',
            self._do_reset,
        )

    def _show_confirm_popup(self, title, message, callback):
        """显示确认弹窗"""
        content = BoxLayout(
            orientation='vertical',
            padding=(PADDING_X, PADDING_Y),
            spacing=PADDING_SMALL,
        )

        content.add_widget(Label(
            text=message,
            font_size=FONT_CHAT_SMALL,
            color=TEXT_PRIMARY,
            halign='left',
            valign='top',
            text_size=(None, None),
        ))

        btn_box = BoxLayout(
            orientation='horizontal',
            spacing=PADDING_SMALL,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        confirm_btn = Button(
            text='确认重置',
            font_size=FONT_BTN,
            color=BTN_TEXT,
            background_color=(0.8, 0.2, 0.2, 1),
        )
        confirm_btn.bind(on_press=lambda i: self._close_popup_then(callback))

        cancel_btn = Button(
            text='取消',
            font_size=FONT_BTN,
            color=TEXT_PRIMARY,
            background_color=BG_INPUT,
        )
        cancel_btn.bind(on_press=lambda i: self._close_popup())

        btn_box.add_widget(confirm_btn)
        btn_box.add_widget(cancel_btn)
        content.add_widget(btn_box)

        self._popup = Popup(
            title=title,
            content=content,
            size_hint=(0.85, None),
            height=280,
            background_color=BG_CARD,
            separator_color=DIVIDER,
            title_color=TEXT_PRIMARY,
            title_size=FONT_CHAT,
            auto_dismiss=False,
        )
        self._popup.open()

    def _close_popup_then(self, callback):
        """关闭弹窗后执行回调"""
        self._close_popup()
        Clock.schedule_once(lambda dt: callback(), 0.2)

    def _do_reset(self):
        """执行重置"""
        from auth import reset_to_default
        reset_to_default()
        self._show_toast('数据已重置，请重新登录')
        Clock.schedule_once(lambda dt: self._restart_app(), 1)

    def _restart_app(self):
        """重启 App"""
        if self.app:
            self.app.restart()

    def _show_toast(self, msg):
        """显示简短提示"""
        if self.app:
            self.app._chat_screen.add_message(msg, is_user=False)

    def _close_popup(self, instance=None):
        """关闭弹窗"""
        if self._popup:
            self._popup.dismiss()
            self._popup = None

    def _on_back(self, instance):
        """返回上一页"""
        if self.app:
            self.app.sm.current = 'chat'
