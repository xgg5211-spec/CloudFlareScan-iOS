import os
import sys
import glob
import time
import json
import socket
import ssl
import random
import re
import queue
import threading
import ipaddress
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.core.text import LabelBase, DEFAULT_FONT
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty, DictProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.switch import Switch
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.popup import Popup

# ==================== 1. iOS 中文字体适配 ====================
def init_ios_cjk_font():
    font_candidates = [
        "/System/Library/Fonts/LanguageSupport/PingFang.ttc",
        "/System/Library/Fonts/CoreUI/PingFang.ttc",
        "/System/Library/Fonts/AppFonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]
    chosen_font = None
    for path in font_candidates:
        if os.path.exists(path):
            chosen_font = path
            break

    if not chosen_font:
        matches = glob.glob("/System/Library/Fonts/**/*PingFang*.ttc", recursive=True)
        if matches:
            chosen_font = matches[0]

    if chosen_font:
        try:
            LabelBase.register(name=DEFAULT_FONT, fn_regular=chosen_font)
            LabelBase.register(name="Roboto", fn_regular=chosen_font)
        except Exception as e:
            print(f"[Font Warning]: {e}")

try:
    init_ios_cjk_font()
except Exception:
    pass

# ==================== 2. 全球 Cloudflare COLO 地区字典 ====================
BUILTIN_IPV4_OFFICIAL = [
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
    "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22"
]

BUILTIN_IPV6_OFFICIAL = [
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32",
    "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32"
]

# 对应图二格式的全球国家/地区字典 mapping
COUNTRY_REGION_MAP = {
    'HKG': ('中国香港', 'HK'), 'MFM': ('中国澳门', 'MO'), 'TPE': ('中国台湾', 'TW'), 'KHH': ('中国台湾', 'TW'),
    'NRT': ('日本', 'JP'), 'HND': ('日本', 'JP'), 'KIX': ('日本', 'JP'), 'ICN': ('韩国', 'KR'),
    'SIN': ('新加坡', 'SG'), 'BKK': ('泰国', 'TH'), 'KUL': ('马来西亚', 'MY'), 'CGK': ('印度尼西亚', 'ID'),
    'MNL': ('菲律宾', 'PH'), 'SGN': ('越南', 'VN'), 'HAN': ('越南', 'VN'), 'DEL': ('印度', 'IN'),
    'LAX': ('美国', 'US'), 'SJC': ('美国', 'US'), 'SFO': ('美国', 'US'), 'SEA': ('美国', 'US'),
    'ORD': ('美国', 'US'), 'JFK': ('美国', 'US'), 'IAD': ('美国', 'US'), 'DFW': ('美国', 'US'),
    'MIA': ('美国', 'US'), 'DEN': ('美国', 'US'), 'YVR': ('加拿大', 'CA'), 'YYZ': ('加拿大', 'CA'),
    'LHR': ('英国', 'GB'), 'CDG': ('法国', 'FR'), 'FRA': ('德国', 'DE'), 'AMS': ('荷兰', 'NL'),
    'BRU': ('比利时', 'BE'), 'ZRH': ('瑞士', 'CH'), 'VIE': ('奥地利', 'AT'), 'MAD': ('西班牙', 'ES'),
    'FCO': ('意大利', 'IT'), 'ARN': ('瑞典', 'SE'), 'HEL': ('芬兰', 'FI'), 'CPH': ('丹麦', 'DK'),
    'EZE': ('阿根廷', 'AR'), 'DUB': ('爱尔兰', 'IE'), 'CAI': ('埃及', 'EG'), 'TLL': ('爱沙尼亚', 'EE'),
    'DXB': ('阿联酋', 'AE'), 'SYD': ('澳大利亚', 'AU'), 'GYD': ('阿塞拜疆', 'AZ'), 'MSQ': ('白俄罗斯', 'BY'),
    'SOF': ('保加利亚', 'BG'), 'GRU': ('巴西', 'BR'), 'KEF': ('冰岛', 'IS')
}

PORTS_HTTPS = "443, 2053, 2083, 2087, 2096, 8443"
PORTS_HTTP = "80, 8080, 8880, 2052, 2082, 2086, 2095"
PORTS_ALL = f"{PORTS_HTTPS}, {PORTS_HTTP}"

def parse_ips_safe(text, max_samples=3000):
    found_items = []
    if not text:
        return []

    lines = text.splitlines()
    for line in lines:
        if len(found_items) >= max_samples:
            break
        line = line.strip().strip('"\'[],;')
        if not line or line.startswith('#'):
            continue

        try:
            if ':' in line and '/' not in line and not line.startswith('['):
                parts = line.split(':')
                if len(parts) == 2 and parts[1].isdigit():
                    found_items.append((parts[0], int(parts[1])))
                    continue

            if '/' in line:
                net = ipaddress.ip_network(line, strict=False)
                num = net.num_addresses
                if num <= 2:
                    found_items.append((str(net.network_address), None))
                else:
                    sample_size = min(15, num - 2)
                    indices = random.sample(range(1, num - 1), sample_size)
                    for idx in indices:
                        found_items.append((str(net[idx]), None))
                        if len(found_items) >= max_samples:
                            break
            else:
                ip_obj = ipaddress.ip_address(line)
                found_items.append((str(ip_obj), None))
        except Exception:
            pass

    return found_items

# ==================== 3. Kivy UI 样式定义 ====================
KV_STYLE = """
#:kivy 2.0.0

<CyberCard@BoxLayout>:
    orientation: 'vertical'
    padding: dp(10)
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: (0.10, 0.13, 0.18, 0.95)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10),]
        Color:
            rgba: (0/255, 229/255, 255/255, 0.25)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(10))
            width: dp(1)

<CyberButton@Button>:
    background_normal: ''
    background_color: (0, 0, 0, 0)
    font_size: '11sp'
    bold: True
    color: (1, 1, 1, 1)
    btn_color: (0/255, 180/255, 216/255, 1)
    canvas.before:
        Color:
            rgba: self.btn_color if self.state == 'normal' else (self.btn_color[0]*0.7, self.btn_color[1]*0.7, self.btn_color[2]*0.7, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(6),]

<FormInput@TextInput>:
    multiline: False
    background_normal: ''
    background_active: ''
    background_color: (0.16, 0.20, 0.28, 1)
    foreground_color: (1, 1, 1, 1)
    hint_text_color: (0.55, 0.60, 0.70, 1)
    font_size: '12sp'
    padding: [dp(8), dp(8), dp(8), dp(8)]
    size_hint_y: None
    height: dp(34)
    cursor_color: (0, 229/255, 255/255, 1)

<ResultRow>:
    orientation: 'horizontal'
    padding: [dp(8), dp(4)]
    spacing: dp(4)
    canvas.before:
        Color:
            rgba: (0.14, 0.18, 0.25, 0.9)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(6),]

    Label:
        text: root.ip_text
        font_size: '11sp'
        bold: True
        color: (0/255, 229/255, 255/255, 1)
        size_hint_x: 0.42
        halign: 'left'
        valign: 'middle'
        text_size: self.size

    Label:
        text: root.region_text
        font_size: '10sp'
        color: (200/255, 200/255, 220/255, 1)
        size_hint_x: 0.24
        halign: 'center'
        valign: 'middle'
        text_size: self.size

    Label:
        text: root.latency_text
        font_size: '11sp'
        bold: True
        color: (0/255, 230/255, 118/255, 1) if 'ms' in root.latency_text else (0.5, 0.5, 0.5, 1)
        size_hint_x: 0.17
        halign: 'right'
        valign: 'middle'
        text_size: self.size

    Label:
        text: root.proxy_text
        font_size: '10sp'
        bold: True
        color: (0/255, 230/255, 118/255, 1) if 'PASS' in root.proxy_text else (230/255, 57/255, 70/255, 1)
        size_hint_x: 0.17
        halign: 'right'
        valign: 'middle'
        text_size: self.size

<MainUI>:
    canvas.before:
        Color:
            rgba: (0.05, 0.07, 0.10, 1)
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: [dp(10), dp(28), dp(10), dp(10)]
        spacing: dp(8)

        # 顶部标题栏
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: dp(38)
            Label:
                text: "[b]⚡ CYBERSCANNER 优选与 PROXYIP 筛选[/b]"
                markup: True
                font_size: '15sp'
                color: (0/255, 229/255, 255/255, 1)
                halign: 'center'
            Label:
                text: root.isp_info_text
                font_size: '10sp'
                color: (180/255, 180/255, 200/255, 1)
                halign: 'center'

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: 'vertical'
                spacing: dp(8)
                size_hint_y: None
                height: self.minimum_height

                # 1. 自定义导入 IP / 订阅库
                CyberCard:
                    size_hint_y: None
                    height: dp(135)
                    Label:
                        text: "[b]1. 自定义导入 IP / 订阅库[/b]"
                        markup: True
                        font_size: '12sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(16)
                        halign: 'left'
                        text_size: self.size

                    BoxLayout:
                        spacing: dp(6)
                        size_hint_y: None
                        height: dp(30)

                        CyberButton:
                            text: "官方 IPv4"
                            btn_color: (0/255, 119/255, 182/255, 1)
                            on_release: root.load_preset_ip("v4")

                        CyberButton:
                            text: "官方 IPv6"
                            btn_color: (0/255, 180/255, 216/255, 1)
                            on_release: root.load_preset_ip("v6")

                        CyberButton:
                            text: "粘贴剪贴板"
                            btn_color: (114/255, 9/255, 183/255, 1)
                            on_release: root.paste_from_clipboard()

                    BoxLayout:
                        spacing: dp(6)
                        size_hint_y: None
                        height: dp(34)
                        FormInput:
                            id: custom_url_input
                            hint_text: "自定义订阅/TXT URL (http://...)"
                        CyberButton:
                            text: "网络加载"
                            size_hint_x: 0.28
                            btn_color: (247/255, 37/255, 133/255, 1)
                            on_release: root.load_from_url()

                    Label:
                        text: root.import_status_text
                        font_size: '10sp'
                        color: (150/255, 160/255, 180/255, 1)
                        size_hint_y: None
                        height: dp(14)
                        halign: 'left'
                        text_size: self.size

                # 2. 扫描参数设置
                CyberCard:
                    size_hint_y: None
                    height: dp(260)
                    Label:
                        text: "[b]2. 扫描与 常用 验证设置[/b]"
                        markup: True
                        font_size: '12sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(16)
                        halign: 'left'
                        text_size: self.size

                    GridLayout:
                        cols: 2
                        spacing: dp(6)
                        size_hint_y: None
                        height: dp(112)

                        BoxLayout:
                            orientation: 'vertical'
                            spacing: dp(2)
                            Label:
                                text: "采样数量 (Max)"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                size_hint_y: None
                                height: dp(14)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: count_input
                                text: "800"

                        BoxLayout:
                            orientation: 'vertical'
                            spacing: dp(2)
                            Label:
                                text: "并发线程"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                size_hint_y: None
                                height: dp(14)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: threads_input
                                text: "150"

                        BoxLayout:
                            orientation: 'vertical'
                            spacing: dp(2)
                            Label:
                                text: "端口设置 (多端口逗号分隔)"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                size_hint_y: None
                                height: dp(14)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: ports_input
                                text: "443, 8443, 2053"

                        BoxLayout:
                            orientation: 'vertical'
                            spacing: dp(2)
                            Label:
                                text: "超时 (秒)"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                size_hint_y: None
                                height: dp(14)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: timeout_input
                                text: "3.0"

                    # 端口预设按键
                    BoxLayout:
                        size_hint_y: None
                        height: dp(24)
                        spacing: dp(4)
                        CyberButton:
                            text: "HTTPS 常用"
                            btn_color: (0.15, 0.2, 0.3, 1)
                            on_release: root.set_port_preset("https")
                        CyberButton:
                            text: "HTTP 常用"
                            btn_color: (0.15, 0.2, 0.3, 1)
                            on_release: root.set_port_preset("http")
                        CyberButton:
                            text: "全量 13 端口"
                            btn_color: (0.15, 0.2, 0.3, 1)
                            on_release: root.set_port_preset("all")

                    # 按钮控制
                    BoxLayout:
                        spacing: dp(6)
                        size_hint_y: None
                        height: dp(32)

                        CyberButton:
                            text: "⚡ 开始普通扫描" if not root.is_scanning else "正在扫描中..."
                            btn_color: (0/255, 180/255, 216/255, 1)
                            on_release: root.start_scan(mode="normal")

                        CyberButton:
                            text: "停止"
                            size_hint_x: 0.3
                            btn_color: (230/255, 57/255, 70/255, 1)
                            on_release: root.stop_scan()

                    Label:
                        text: root.scan_status_text
                        font_size: '10sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(14)
                        halign: 'left'
                        text_size: self.size

                # 3. 专属 check.proxyip.cmliussss.net 深度验证区
                CyberCard:
                    size_hint_y: None
                    height: dp(125)
                    canvas.before:
                        Color:
                            rgba: (0.12, 0.15, 0.24, 0.95)
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(10),]
                        Color:
                            rgba: (247/255, 37/255, 133/255, 0.6)
                        Line:
                            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(10))
                            width: dp(1)

                    Label:
                        text: "[b]3. check.proxyip.cmliussss.net 专属批量深度验真[/b]"
                        markup: True
                        font_size: '12sp'
                        color: (247/255, 37/255, 133/255, 1)
                        size_hint_y: None
                        height: dp(16)
                        halign: 'left'
                        text_size: self.size

                    FormInput:
                        id: proxy_target_input
                        text: "check.proxyip.cmliussss.net"
                        hint_text: "完整校验域名"

                    CyberButton:
                        text: "🚀 批量验证 check.proxyip.cmliussss.net 节点"
                        size_hint_y: None
                        height: dp(34)
                        btn_color: (247/255, 37/255, 133/255, 1)
                        on_release: root.start_scan(mode="cmliussss_proxy")

                # 4. 验真结果与图二同款地区筛选
                CyberCard:
                    size_hint_y: None
                    height: dp(320)
                    BoxLayout:
                        size_hint_y: None
                        height: dp(28)
                        spacing: dp(6)

                        Label:
                            text: "[b]4. 验真结果[/b]"
                            markup: True
                            font_size: '12sp'
                            color: (0/255, 229/255, 255/255, 1)
                            size_hint_x: 0.28
                            halign: 'left'
                            valign: 'middle'
                            text_size: self.size

                        # 图二同款弹窗按钮
                        CyberButton:
                            text: "🌐 图二同款地区筛选 ▼"
                            btn_color: (0/255, 119/255, 182/255, 1)
                            size_hint_x: 0.44
                            on_release: root.open_region_select_popup()

                        CyberButton:
                            text: "📋 复制 IP"
                            btn_color: (0/255, 230/255, 118/255, 1)
                            size_hint_x: 0.28
                            on_release: root.copy_ips_to_clipboard()

                    RecycleView:
                        id: rv
                        viewclass: 'ResultRow'
                        RecycleBoxLayout:
                            default_size: None, dp(32)
                            default_size_hint: 1, None
                            size_hint_y: None
                            height: self.minimum_height
                            orientation: 'vertical'
                            spacing: dp(2)
"""

Builder.load_string(KV_STYLE)


class ResultRow(RecycleDataViewBehavior, BoxLayout):
    ip_text = StringProperty('')
    region_text = StringProperty('')
    latency_text = StringProperty('')
    proxy_text = StringProperty('')


class MainUI(BoxLayout):
    import_status_text = StringProperty("默认已载入官方 IPv4 网段")
    scan_status_text = StringProperty("系统就绪")
    isp_info_text = StringProperty("正在检测网络...")
    is_scanning = BooleanProperty(False)
    valid_ips_data = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stop_requested = False
        self.raw_ip_pool = BUILTIN_IPV4_OFFICIAL[:]
        self.result_queue = queue.Queue()
        self.all_scanned_items = []
        self.selected_region_codes = set()

        threading.Thread(target=self._fetch_local_isp, daemon=True).start()
        Clock.schedule_interval(self._drain_result_queue, 0.08)

    def _fetch_local_isp(self):
        try:
            req = urllib.request.Request("http://ip-api.com/json/?lang=zh-CN", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode('utf-8'))
                ip = data.get('query', '未知')
                isp = data.get('isp', '未知运营商')
                country = data.get('country', '')
                Clock.schedule_once(lambda dt: setattr(self, 'isp_info_text', f"当前网络: {isp} ({country}) | 公网IP: {ip}"))
        except Exception:
            Clock.schedule_once(lambda dt: setattr(self, 'isp_info_text', "网络检测完成 | 优选扫描就绪"))

    def load_preset_ip(self, ip_type):
        if ip_type == "v4":
            self.raw_ip_pool = BUILTIN_IPV4_OFFICIAL[:]
            self.import_status_text = f"已载入 {len(BUILTIN_IPV4_OFFICIAL)} 个官方 IPv4 网段"
        else:
            self.raw_ip_pool = BUILTIN_IPV6_OFFICIAL[:]
            self.import_status_text = f"已载入 {len(BUILTIN_IPV6_OFFICIAL)} 个官方 IPv6 网段"

    def paste_from_clipboard(self):
        try:
            from kivy.core.clipboard import Clipboard
            text = Clipboard.paste()
            if text and text.strip():
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                self.raw_ip_pool = lines
                self.import_status_text = f"已载入剪贴板 {len(lines)} 行自定义 IP/网段"
            else:
                self.import_status_text = "剪贴板为空！"
        except Exception:
            self.import_status_text = "剪贴板读取失败"

    def load_from_url(self):
        url = self.ids.custom_url_input.text.strip()
        if not url.startswith("http"):
            self.import_status_text = "❌ 请输入有效的 URL"
            return

        self.import_status_text = "正在拉取网络订阅..."
        def _fetch():
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    content = resp.read().decode('utf-8', errors='ignore')
                    lines = [l.strip() for l in content.splitlines() if l.strip()]
                    self.raw_ip_pool = lines
                    Clock.schedule_once(lambda dt: setattr(self, 'import_status_text', f"✓ 加载网络库成功: {len(lines)} 条"))
            except Exception:
                Clock.schedule_once(lambda dt: setattr(self, 'import_status_text', "❌ 网络订阅拉取失败"))

        threading.Thread(target=_fetch, daemon=True).start()

    def set_port_preset(self, ptype):
        if ptype == "https":
            self.ids.ports_input.text = PORTS_HTTPS
        elif ptype == "http":
            self.ids.ports_input.text = PORTS_HTTP
        else:
            self.ids.ports_input.text = PORTS_ALL

    def open_region_select_popup(self):
        """图二同款“只扫描/筛选指定地区”弹窗"""
        # 统计现有机房或默认区域数据
        counts = {}
        for item in self.all_scanned_items:
            code = item.get('code', 'OTHER')
            counts[code] = counts.get(code, 0) + 1

        # 构建图二样式弹窗
        content = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))

        # 顶部按钮工具栏: 清空 | 全选 | 标题 | 完成
        top_bar = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        btn_clear = Button(text="清空", font_size='12sp', size_hint_x=0.2, background_color=(0.2, 0.2, 0.2, 1))
        btn_select_all = Button(text="全选", font_size='12sp', size_hint_x=0.2, background_color=(0.2, 0.2, 0.2, 1))
        lbl_title = Label(text="[b]只扫描指定地区[/b]", markup=True, font_size='14sp', color=(1, 1, 1, 1), size_hint_x=0.4, halign='center')
        btn_done = Button(text="完成", font_size='12sp', size_hint_x=0.2, background_color=(0/255, 180/255, 216/255, 1))

        top_bar.add_widget(btn_clear)
        top_bar.add_widget(btn_select_all)
        top_bar.add_widget(lbl_title)
        top_bar.add_widget(btn_done)
        content.add_widget(top_bar)

        # 滚动显示图二同款国家地区列表
        from kivy.uix.scrollview import ScrollView
        scroll = ScrollView()
        list_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(2))
        list_box.bind(minimum_height=list_box.setter('height'))

        checkbox_map = {}

        # 整理预设列表 (包含图二中出现的全部国家地区)
        all_regions = [
            ('中国香港', 'HK'), ('中国澳门', 'MO'), ('中国台湾', 'TW'), ('阿根廷', 'AR'),
            ('爱尔兰', 'IE'), ('埃及', 'EG'), ('爱沙尼亚', 'EE'), ('阿联酋', 'AE'),
            ('澳大利亚', 'AU'), ('奥地利', 'AT'), ('阿塞拜疆', 'AZ'), ('白俄罗斯', 'BY'),
            ('保加利亚', 'BG'), ('巴西', 'BR'), ('比利时', 'BE'), ('冰岛', 'IS'),
            ('日本', 'JP'), ('韩国', 'KR'), ('新加坡', 'SG'), ('美国', 'US'), ('英国', 'GB'), ('德国', 'DE')
        ]

        for name, code in all_regions:
            row = BoxLayout(size_hint_y=None, height=dp(32), padding=[dp(8), 0])
            count_num = counts.get(code, 0)
            lbl_item = Label(
                text=f"{name} ({code}) ({count_num})",
                font_size='12sp',
                color=(0.9, 0.9, 0.9, 1),
                halign='left',
                valign='middle',
                size_hint_x=0.8
            )
            lbl_item.bind(size=lbl_item.setter('text_size'))

            cb = CheckBox(size_hint_x=0.2, active=(code in self.selected_region_codes or not self.selected_region_codes))
            checkbox_map[code] = cb

            row.add_widget(lbl_item)
            row.add_widget(cb)
            list_box.add_widget(row)

        scroll.add_widget(list_box)
        content.add_widget(scroll)

        popup = Popup(title="", content=content, size_hint=(0.9, 0.82), auto_dismiss=False)

        def do_clear(instance):
            for cb in checkbox_map.values():
                cb.active = False

        def do_select_all(instance):
            for cb in checkbox_map.values():
                cb.active = True

        def do_done(instance):
            self.selected_region_codes = {code for code, cb in checkbox_map.items() if cb.active}
            self.filter_results_by_selected_regions()
            popup.dismiss()

        btn_clear.bind(on_release=do_clear)
        btn_select_all.bind(on_release=do_select_all)
        btn_done.bind(on_release=do_done)

        popup.open()

    def filter_results_by_selected_regions(self):
        if not self.selected_region_codes:
            filtered = self.all_scanned_items
        else:
            filtered = [
                item for item in self.all_scanned_items
                if item.get('code') in self.selected_region_codes
            ]

        self.valid_ips_data = filtered
        self.ids.rv.data = sorted(filtered, key=lambda x: x['raw_latency'])

    def start_scan(self, mode="normal"):
        if self.is_scanning:
            return

        try:
            max_count = int(self.ids.count_input.text.strip())
        except ValueError:
            max_count = 800

        try:
            threads_num = int(self.ids.threads_input.text.strip())
        except ValueError:
            threads_num = 150

        try:
            timeout_sec = float(self.ids.timeout_input.text.strip())
        except ValueError:
            timeout_sec = 3.0

        ports_str = self.ids.ports_input.text.strip()
        ports = [int(p.strip()) for p in re.findall(r'\d+', ports_str)] if ports_str else [443]

        parsed_items = parse_ips_safe("\n".join(self.raw_ip_pool), max_samples=max_count)
        if not parsed_items:
            self.scan_status_text = "❌ 未检测到有效的 IP 节点"
            return

        target_host = self.ids.proxy_target_input.text.strip() if mode == "cmliussss_proxy" else "speed.cloudflare.com"

        self.is_scanning = True
        self.stop_requested = False
        self.valid_ips_data.clear()
        self.all_scanned_items.clear()
        self.ids.rv.data = []
        self.scan_status_text = f"正在针对 {target_host} 进行深度验真..."

        threading.Thread(
            target=self._scan_runner,
            args=(parsed_items, ports, threads_num, timeout_sec, target_host, mode),
            daemon=True
        ).start()

    def _test_ip_worker(self, ip_tuple, default_ports, timeout_sec, target_host, mode):
        if self.stop_requested:
            return

        ip, single_port = ip_tuple
        ports_to_test = [single_port] if single_port else default_ports

        for port in ports_to_test:
            if self.stop_requested:
                break

            s = socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout_sec)
            start_t = time.perf_counter()
            colo_code = "UNKNOWN"
            region_disp = "未知"
            country_code = "OTHER"
            proxy_ok = False

            try:
                # 专属针对 check.proxyip.cmliussss.net 发起精确 HTTPS 握手与 HTTP 请求
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                tls_sock = ctx.wrap_socket(s, server_hostname=target_host)
                tls_sock.connect((ip, port))
                latency = int((time.perf_counter() - start_t) * 1000)

                # 发送完整 HTTP/1.1 请求
                http_req = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {target_host}\r\n"
                    f"User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15\r\n"
                    f"Accept: */*\r\n"
                    f"Connection: close\r\n\r\n"
                )
                tls_sock.sendall(http_req.encode('utf-8'))

                resp_bytes = b""
                while True:
                    chunk = tls_sock.recv(1024)
                    if not chunk:
                        break
                    resp_bytes += chunk
                    if len(resp_bytes) > 2048:
                        break

                tls_sock.close()
                resp_str = resp_bytes.decode('utf-8', errors='ignore')

                # 解析 check.proxyip.cmliussss.net 返回的特征字段
                if "HTTP/1.1 200" in resp_str or "colo=" in resp_str or "uag=" in resp_str:
                    proxy_ok = True

                match = re.search(r'colo=([A-Z]{3})', resp_str)
                if match:
                    colo_code = match.group(1)
                    if colo_code in COUNTRY_REGION_MAP:
                        name, country_code = COUNTRY_REGION_MAP[colo_code]
                        region_disp = f"{name} ({country_code})"
                    else:
                        region_disp = colo_code

                if mode == "cmliussss_proxy" and not proxy_ok:
                    continue  # 未通过 check.proxyip.cmliussss.net 深度验证直接舍弃

                self.result_queue.put({
                    'ip': ip, 'port': port, 'latency': latency,
                    'colo_disp': region_disp, 'code': country_code,
                    'proxy_ok': proxy_ok, 'success': True
                })
                return
            except Exception:
                pass
            finally:
                try:
                    s.close()
                except Exception:
                    pass

        self.result_queue.put({'ip': ip, 'success': False})

    def _scan_runner(self, items, default_ports, threads_num, timeout_sec, target_host, mode):
        with ThreadPoolExecutor(max_workers=min(threads_num, 180)) as pool:
            futures = [
                pool.submit(self._test_ip_worker, item, default_ports, timeout_sec, target_host, mode)
                for item in items
            ]
            for future in futures:
                if self.stop_requested:
                    break
                future.result()

        Clock.schedule_once(lambda dt: self._finish_scan())

    def _drain_result_queue(self, dt):
        if self.result_queue.empty():
            return

        new_items = []
        while not self.result_queue.empty():
            try:
                res = self.result_queue.get_nowait()
                if res.get('success'):
                    ip = res['ip']
                    port = res['port']
                    latency = res['latency']
                    colo_disp = res['colo_disp']
                    code = res['code']
                    proxy_ok = res['proxy_ok']

                    item_dict = {
                        'ip_text': f"{ip}:{port}",
                        'region_text': colo_disp,
                        'latency_text': f"{latency} ms",
                        'proxy_text': "PASS" if proxy_ok else "直连",
                        'raw_ip': ip,
                        'raw_port': port,
                        'raw_latency': latency,
                        'code': code
                    }

                    self.valid_ips_data.append(item_dict)
                    self.all_scanned_items.append(item_dict)

                    if not self.selected_region_codes or code in self.selected_region_codes:
                        new_items.append(item_dict)
            except queue.Empty:
                break

        if new_items:
            self.ids.rv.data.extend(new_items)
            self.scan_status_text = f"正在验证... 已找到 {len(self.valid_ips_data)} 个通过节点"

    def _finish_scan(self):
        self.is_scanning = False
        self.ids.rv.data = sorted(self.ids.rv.data, key=lambda x: x['raw_latency'])
        self.scan_status_text = f"✓ 批量深度验证完成！共获取 {len(self.valid_ips_data)} 个有效 IP 节点"

    def stop_scan(self):
        self.stop_requested = True
        self.is_scanning = False
        self.scan_status_text = "已停止"

    def copy_ips_to_clipboard(self):
        try:
            if not self.valid_ips_data:
                self._show_toast("列表中无有效 IP，请先执行扫描！")
                return

            lines = [item['ip_text'] for item in self.valid_ips_data]
            export_text = "\n".join(lines)

            from kivy.core.clipboard import Clipboard
            Clipboard.copy(str(export_text))

            self._show_toast(f"✅ 成功复制 {len(lines)} 个通过验真 IP！")
        except Exception:
            self._show_toast("复制成功！")

    def _show_toast(self, message):
        content = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))
        lbl = Label(text=message, font_size='11sp', color=(1, 1, 1, 1), halign='center')
        btn = Button(text="确定", size_hint_y=None, height=dp(30), font_size='11sp')
        content.add_widget(lbl)
        content.add_widget(btn)

        popup = Popup(title="系统提示", content=content, size_hint=(0.8, 0.22))
        btn.bind(on_release=popup.dismiss)
        popup.open()


class CloudflareScannerApp(App):
    def build(self):
        self.title = "CYBERSCANNER 优选与 PROXYIP 筛选"
        return MainUI()


if __name__ == '__main__':
    CloudflareScannerApp().run()
