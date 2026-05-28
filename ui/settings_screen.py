"""
ui/settings_screen.py — 店小二设置页

规范来源：
- ui_spec.md 2.2（设置页布局网格）
- ui_spec.md 3.x（各种组件状态机）
- ui_spec.md 5.3（密码修改流程）

功能（完整保留）：
- 账户安全、大模型配置、偏好、数据管理、关于
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
from kivy.graphics import Color, RoundedRectangle, Rectangle
import os

from ui import (
    BG_PAGE, BG_CARD,
    PRIMARY_RED, PRIMARY_ORANGE,
    BTN_PRIMARY, BTN_PRIMARY_TEXT, BTN_TEXT,
    COLOR_DISABLED,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_PLACEHOLDER, TEXT_ERROR, TEXT_SUCCESS,
    DIVIDER,
    FONT_TITLE, FONT_BODY, FONT_SMALL, FONT_BTN, FONT_INPUT, FONT_HINT,
    PADDING_X, PADDING_Y, PADDING_SMALL, PADDING_LARGE,
    BTN_HEIGHT, RADIUS_LG, RADIUS_XL, NAV_BAR_HEIGHT,
    ANIM_DURATION,
)


class SectionHeader(Label):
    def __init__(self, text='', **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.font_size = FONT_BODY
        self.color = TEXT_PRIMARY
        self.bold = True
        self.size_hint_y = None
        self.height = 36
        self.halign = 'left'
        self.valign = 'middle'


class SettingRow(BoxLayout):
    def __init__(self, label='', widget=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = BTN_HEIGHT + PADDING_SMALL
        self.padding = (0, PADDING_SMALL // 2)
        self.spacing = PADDING_SMALL

        lbl = Label(
            text=label,
            font_size=FONT_SMALL,
            color=TEXT_PRIMARY,
            size_hint_x=None,
            width=90,
            halign='left',
            valign='middle',
        )
        self.add_widget(lbl)
        if widget:
            self.add_widget(widget)
        else:
            self.add_widget(Label(size_hint_x=1))


class SettingsScreen(Screen):

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

        root = BoxLayout(orientation='vertical')

        # ── 导航栏 ──
        nav_bar = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=NAV_BAR_HEIGHT,
            padding=(4, 0, PADDING_X, 0),
        )
        with nav_bar.canvas.before:
            Color(*BG_CARD)
            self._nav_rect = Rectangle(pos=nav_bar.pos, size=nav_bar.size)
        nav_bar.bind(pos=self._update_nav, size=self._update_nav)

        back_btn = Button(
            text='< 返回',
            font_size=FONT_SMALL,
            color=PRIMARY_ORANGE,
            background_color=(0, 0, 0, 0),
            size_hint_x=None,
            width=72,
            size_hint_y=None,
            height=NAV_BAR_HEIGHT,
        )
        back_btn.background_normal = ''
        back_btn.background_down = ''
        back_btn.bind(on_press=self._on_back)
        nav_bar.add_widget(back_btn)
        nav_bar.add_widget(Label(
            text='设置',
            font_size=FONT_TITLE,
            color=TEXT_PRIMARY,
            bold=True,
            size_hint_x=1,
            halign='center',
            valign='middle',
        ))
        nav_bar.add_widget(Label(size_hint_x=None, width=72))

        # 分隔线
        nav_sep = BoxLayout(size_hint_y=None, height=1)
        with nav_sep.canvas.before:
            Color(*DIVIDER)
            Rectangle(pos=nav_sep.pos, size=nav_sep.size)
        nav_sep.bind(
            pos=lambda i, v: setattr(nav_sep.canvas.children[-1], 'pos', i.pos),
            size=lambda i, v: setattr(nav_sep.canvas.children[-1], 'size', i.size),
        )

        # ── 可滚动内容 ──
        scroll = ScrollView(size_hint_y=1, do_scroll_x=False, do_scroll_y=True, bar_width=4)
        content = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            padding=(PADDING_X, PADDING_Y, PADDING_X, PADDING_Y),
            spacing=PADDING_LARGE,
        )
        content.bind(minimum_height=content.setter('height'))

        # ═══ 账户安全 ═══
        content.add_widget(SectionHeader(text='账户安全'))
        change_pwd_btn = Button(
            text='修改密码',
            font_size=FONT_BTN,
            color=PRIMARY_RED,
            background_color=(1, 1, 1, 0),
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        change_pwd_btn.background_normal = ''
        change_pwd_btn.bind(on_press=self._on_change_password)
        # 红色描边按钮
        with change_pwd_btn.canvas.before:
            Color(*PRIMARY_RED)
            self._pwd_btn_rect = RoundedRectangle(
                pos=change_pwd_btn.pos, size=change_pwd_btn.size, radius=[RADIUS_XL],
            )
        change_pwd_btn.bind(pos=self._up_pwd_btn, size=self._up_pwd_btn)
        content.add_widget(change_pwd_btn)

        # ═══ 大模型配置 ═══
        content.add_widget(SectionHeader(text='大模型配置'))
        content.add_widget(SettingRow(label='API 地址', widget=self._make_input('llm_api_url', hint='https://api.deepseek.com/v1/chat/completions')))
        content.add_widget(SettingRow(label='API Key', widget=self._make_input('llm_api_key', hint='sk-...', password=True)))
        content.add_widget(SettingRow(label='模型名', widget=self._make_input('llm_model', hint='deepseek-chat')))
        content.add_widget(SettingRow(label='备用地址', widget=self._make_input('llm_backup_url', hint='（可选）')))
        content.add_widget(SettingRow(label='备用Key', widget=self._make_input('llm_backup_key', hint='（可选）', password=True)))

        save_llm_btn = Button(
            text='保存大模型配置',
            font_size=FONT_BTN,
            color=BTN_PRIMARY_TEXT,
            background_color=BTN_PRIMARY,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        save_llm_btn.background_normal = ''
        save_llm_btn.background_down = ''
        with save_llm_btn.canvas.before:
            Color(*BTN_PRIMARY)
            self._save_btn_bg = RoundedRectangle(
                pos=save_llm_btn.pos, size=save_llm_btn.size, radius=[RADIUS_XL],
            )
        save_llm_btn.bind(pos=self._up_save_btn, size=self._up_save_btn)
        save_llm_btn.bind(on_press=self._on_save_llm)
        content.add_widget(save_llm_btn)

        # ═══ 偏好 ═══
        content.add_widget(SectionHeader(text='偏好'))
        self._voice_toggle = ToggleButton(
            text='语音唱诺：开',
            font_size=FONT_SMALL,
            color=TEXT_PRIMARY,
            background_color=BG_CARD,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        self._voice_toggle.bind(on_press=self._on_voice_toggle)
        content.add_widget(self._voice_toggle)

        self._dialect_toggle = ToggleButton(
            text='东北话模式：开',
            font_size=FONT_SMALL,
            color=TEXT_PRIMARY,
            background_color=BG_CARD,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        self._dialect_toggle.bind(on_press=self._on_dialect_toggle)
        content.add_widget(self._dialect_toggle)

        # ═══ 数据管理 ═══
        content.add_widget(SectionHeader(text='数据管理'))
        for label, cb in [
            ('导出加密备份', self._on_export_backup),
            ('导入恢复备份', self._on_import_backup),
        ]:
            btn = Button(
                text=label,
                font_size=FONT_BTN,
                color=TEXT_PRIMARY,
                background_color=BG_CARD,
                size_hint_y=None,
                height=BTN_HEIGHT,
            )
            btn.bind(on_press=cb)
            content.add_widget(btn)

        reset_btn = Button(
            text='重置所有数据',
            font_size=FONT_BTN,
            color=PRIMARY_RED,
            background_color=BG_CARD,
            size_hint_y=None,
            height=BTN_HEIGHT,
        )
        reset_btn.bind(on_press=self._on_reset_data)
        content.add_widget(reset_btn)

        # ═══ 关于 ═══
        content.add_widget(SectionHeader(text='关于'))
        self._version_label = Label(
            text='店小二 V1.0 MVP',
            font_size=FONT_SMALL,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=24,
            halign='left',
        )
        content.add_widget(self._version_label)
        self._trial_label = Label(
            text='',
            font_size=FONT_SMALL,
            color=TEXT_SECONDARY,
            size_hint_y=None,
            height=24,
            halign='left',
        )
        content.add_widget(self._trial_label)
        content.add_widget(Label(size_hint_y=None, height=40))

        scroll.add_widget(content)

        root.add_widget(nav_bar)
        root.add_widget(nav_sep)
        root.add_widget(scroll)
        self.add_widget(root)

        self._all_setting_row_inputs = []
        Clock.schedule_once(lambda dt: self._load_settings(), 0.2)

    def _update_bg(self, i, v): self._bg_rect.pos, self._bg_rect.size = i.pos, i.size
    def _update_nav(self, i, v): self._nav_rect.pos, self._nav_rect.size = i.pos, i.size
    def _up_pwd_btn(self, i, v): self._pwd_btn_rect.pos, self._pwd_btn_rect.size = i.pos, i.size
    def _up_save_btn(self, i, v): self._save_btn_bg.pos, self._save_btn_bg.size = i.pos, i.size

    def _make_input(self, setting_key, hint='', password=False):
        inp = TextInput(
            hint_text=hint,
            font_size=FONT_SMALL,
            background_color=BG_CARD,
            foreground_color=TEXT_PRIMARY,
            hint_text_color=TEXT_PLACEHOLDER,
            password=password,
            multiline=False,
            size_hint_y=None,
            height=BTN_HEIGHT,
            write_tab=False,
        )
        inp.setting_key = setting_key
        self._all_setting_row_inputs.append(inp)
        return inp

    def _load_settings(self):
        from data.db import get_setting
        for inp in self._all_setting_row_inputs:
            val = get_setting(inp.setting_key) or ''
            inp.text = val

        voice = get_setting('voice_enabled')
        if voice is None or voice == '1' or voice == 1:
            self._voice_toggle.state = 'normal'
            self._voice_toggle.text = '语音唱诺：开'
        else:
            self._voice_toggle.state = 'down'
            self._voice_toggle.text = '语音唱诺：关'

        dialect = get_setting('dialect_mode')
        if dialect is None or dialect != 'standard':
            self._dialect_toggle.state = 'normal'
            self._dialect_toggle.text = '东北话模式：开'
        else:
            self._dialect_toggle.state = 'down'
            self._dialect_toggle.text = '东北话模式：关'

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

    # ══════════════════════════════════════════════
    # 以下业务逻辑全部保留不变
    # ══════════════════════════════════════════════

    def _on_save_llm(self, instance):
        from data.db import set_setting
        for inp in self._all_setting_row_inputs:
            set_setting(inp.setting_key, inp.text.strip())
        self._show_toast('大模型配置已保存')

    def _on_voice_toggle(self, instance):
        from data.db import set_setting
        if instance.state == 'normal':
            set_setting('voice_enabled', '1')
            instance.text = '语音唱诺：开'
        else:
            set_setting('voice_enabled', '0')
            instance.text = '语音唱诺：关'

    def _on_dialect_toggle(self, instance):
        from data.db import set_setting
        if instance.state == 'normal':
            set_setting('dialect_mode', 'dongbei')
            instance.text = '东北话模式：开'
        else:
            set_setting('dialect_mode', 'standard')
            instance.text = '东北话模式：关'

    def _on_change_password(self, instance):
        content = BoxLayout(orientation='vertical', padding=(PADDING_X, PADDING_Y), spacing=PADDING_SMALL, size_hint=(0.85, None))
        content.minimum_height = 300
        content.add_widget(Label(text='修改密码', font_size=FONT_BODY, color=TEXT_PRIMARY, bold=True, size_hint_y=None, height=32))
        content.add_widget(Label(text='当前密码：', font_size=FONT_SMALL, color=TEXT_SECONDARY, size_hint_y=None, height=22, halign='left'))
        old_pwd = TextInput(password=True, font_size=FONT_INPUT, background_color=BG_CARD, foreground_color=TEXT_PRIMARY, size_hint_y=None, height=BTN_HEIGHT, multiline=False)
        content.add_widget(old_pwd)
        content.add_widget(Label(text='新密码（至少6位）：', font_size=FONT_SMALL, color=TEXT_SECONDARY, size_hint_y=None, height=22, halign='left'))
        new_pwd = TextInput(password=True, font_size=FONT_INPUT, background_color=BG_CARD, foreground_color=TEXT_PRIMARY, size_hint_y=None, height=BTN_HEIGHT, multiline=False)
        content.add_widget(new_pwd)
        self._pwd_status = Label(text='', font_size=FONT_SMALL, color=TEXT_ERROR, size_hint_y=None, height=22, halign='center')
        content.add_widget(self._pwd_status)
        btn_box = BoxLayout(orientation='horizontal', spacing=PADDING_SMALL, size_hint_y=None, height=BTN_HEIGHT)
        confirm_btn = Button(text='确认修改', font_size=FONT_BTN, color=BTN_PRIMARY_TEXT, background_color=BTN_PRIMARY)
        confirm_btn.bind(on_press=lambda i: self._do_change_password(old_pwd, new_pwd))
        cancel_btn = Button(text='取消', font_size=FONT_BTN, color=TEXT_PRIMARY, background_color=(1, 1, 1, 0.5))
        cancel_btn.bind(on_press=lambda i: self._close_popup())
        btn_box.add_widget(confirm_btn); btn_box.add_widget(cancel_btn)
        content.add_widget(btn_box)
        self._popup = Popup(title='修改密码', content=content, size_hint=(0.85, None), height=400, background_color=BG_CARD, separator_color=DIVIDER, title_color=TEXT_PRIMARY, title_size=FONT_BODY, auto_dismiss=False)
        self._popup.open()

    def _do_change_password(self, old_inp, new_inp):
        from auth import change_password
        old, new = old_inp.text.strip(), new_inp.text.strip()
        if not old or not new:
            self._pwd_status.text, self._pwd_status.color = '密码不能为空', TEXT_ERROR
            return
        if len(new) < 6:
            self._pwd_status.text, self._pwd_status.color = '新密码至少6位', TEXT_ERROR
            return
        result = change_password(old, new)
        if result == 'ok':
            self._pwd_status.text, self._pwd_status.color = '密码修改成功！', TEXT_SUCCESS
            Clock.schedule_once(lambda dt: self._close_popup(), 0.8)
        elif result == 'wrong_old':
            self._pwd_status.text, self._pwd_status.color = '当前密码错误', TEXT_ERROR
        elif result == 'same_password':
            self._pwd_status.text, self._pwd_status.color = '新旧密码不能相同', TEXT_ERROR
        else:
            self._pwd_status.text, self._pwd_status.color = f'修改失败：{result}', TEXT_ERROR

    def _on_export_backup(self, instance): self._show_backup_pwd_popup(True)
    def _on_import_backup(self, instance): self._show_backup_pwd_popup(False)

    def _show_backup_pwd_popup(self, export):
        content = BoxLayout(orientation='vertical', padding=(PADDING_X, PADDING_Y), spacing=PADDING_SMALL, size_hint=(0.85, None))
        content.minimum_height = 200
        title_label = '导出加密备份' if export else '导入恢复备份'
        content.add_widget(Label(text=title_label, font_size=FONT_BODY, color=TEXT_PRIMARY, bold=True, size_hint_y=None, height=32))
        content.add_widget(Label(text='请输入密码：', font_size=FONT_SMALL, color=TEXT_SECONDARY, size_hint_y=None, height=22, halign='left'))
        pwd = TextInput(password=True, font_size=FONT_INPUT, background_color=BG_CARD, foreground_color=TEXT_PRIMARY, size_hint_y=None, height=BTN_HEIGHT, multiline=False)
        content.add_widget(pwd)
        self._backup_status = Label(text='', font_size=FONT_SMALL, color=TEXT_ERROR, size_hint_y=None, height=22, halign='center')
        content.add_widget(self._backup_status)
        btn_box = BoxLayout(orientation='horizontal', spacing=PADDING_SMALL, size_hint_y=None, height=BTN_HEIGHT)
        confirm_btn = Button(text='确认', font_size=FONT_BTN, color=BTN_PRIMARY_TEXT, background_color=BTN_PRIMARY)
        confirm_btn.bind(on_press=lambda i: self._do_export(pwd) if export else self._do_import(pwd))
        cancel_btn = Button(text='取消', font_size=FONT_BTN, color=TEXT_PRIMARY, background_color=(1, 1, 1, 0.5))
        cancel_btn.bind(on_press=lambda i: self._close_popup())
        btn_box.add_widget(confirm_btn); btn_box.add_widget(cancel_btn)
        content.add_widget(btn_box)
        self._popup = Popup(title=title_label, content=content, size_hint=(0.85, None), height=300, background_color=BG_CARD, separator_color=DIVIDER, title_color=TEXT_PRIMARY, title_size=FONT_BODY, auto_dismiss=False)
        self._popup.open()

    def _do_export(self, pwd_input):
        from utils.backup import export_backup
        password = pwd_input.text.strip()
        if not password: self._backup_status.text, self._backup_status.color = '密码不能为空', TEXT_ERROR; return
        output_dir = self.app.user_data_dir if self.app else os.path.expanduser('~')
        from datetime import datetime
        output_path = os.path.join(output_dir, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bbk")
        result = export_backup(password, output_path)
        if result == 'ok':
            self._backup_status.text, self._backup_status.color = '备份成功！', TEXT_SUCCESS
            Clock.schedule_once(lambda dt: self._close_popup(), 1.5)
        else:
            self._backup_status.text, self._backup_status.color = f'导出失败：{result}', TEXT_ERROR

    def _do_import(self, pwd_input):
        from utils.backup import import_backup
        password = pwd_input.text.strip()
        if not password: self._backup_status.text, self._backup_status.color = '密码不能为空', TEXT_ERROR; return
        backup_dir = self.app.user_data_dir if self.app else os.path.expanduser('~')
        bbk_files = sorted([f for f in os.listdir(backup_dir) if f.endswith('.bbk')], reverse=True)
        if not bbk_files: self._backup_status.text, self._backup_status.color = '未找到备份文件', TEXT_ERROR; return
        result = import_backup(password, os.path.join(backup_dir, bbk_files[0]))
        if result == 'ok':
            self._backup_status.text, self._backup_status.color = '恢复成功！请重新登录', TEXT_SUCCESS
            Clock.schedule_once(lambda dt: self._restart_app(), 1.5)
        else:
            self._backup_status.text, self._backup_status.color = f'恢复失败：{result}', TEXT_ERROR

    def _on_reset_data(self, instance):
        self._show_confirm_popup('确认重置', '重置所有数据将清除全部订单、客户、品类等信息，恢复默认密码。\n\n此操作不可撤销！', self._do_reset)

    def _show_confirm_popup(self, title, message, callback):
        content = BoxLayout(orientation='vertical', padding=(PADDING_X, PADDING_Y), spacing=PADDING_SMALL)
        content.add_widget(Label(text=message, font_size=FONT_SMALL, color=TEXT_PRIMARY, halign='left', valign='top'))
        btn_box = BoxLayout(orientation='horizontal', spacing=PADDING_SMALL, size_hint_y=None, height=BTN_HEIGHT)
        confirm_btn = Button(text='确认重置', font_size=FONT_BTN, color=BTN_TEXT, background_color=PRIMARY_RED)
        confirm_btn.bind(on_press=lambda i: self._close_popup_then(callback))
        cancel_btn = Button(text='取消', font_size=FONT_BTN, color=TEXT_PRIMARY, background_color=(1, 1, 1, 0.5))
        cancel_btn.bind(on_press=lambda i: self._close_popup())
        btn_box.add_widget(confirm_btn); btn_box.add_widget(cancel_btn)
        content.add_widget(btn_box)
        self._popup = Popup(title=title, content=content, size_hint=(0.85, None), height=280, background_color=BG_CARD, separator_color=DIVIDER, title_color=TEXT_PRIMARY, title_size=FONT_BODY, auto_dismiss=False)
        self._popup.open()

    def _close_popup_then(self, callback): self._close_popup(); Clock.schedule_once(lambda dt: callback(), 0.2)
    def _do_reset(self):
        from auth import reset_to_default
        reset_to_default()
        self._show_toast('数据已重置，请重新登录')
        Clock.schedule_once(lambda dt: self._restart_app(), 1)
    def _restart_app(self):
        if self.app: self.app.restart()
    def _show_toast(self, msg):
        if self.app: self.app._chat_screen.add_message(msg, is_user=False)
    def _close_popup(self, instance=None):
        if self._popup: self._popup.dismiss(); self._popup = None
    def _on_back(self, instance):
        if self.app: self.app.sm.current = 'chat'
