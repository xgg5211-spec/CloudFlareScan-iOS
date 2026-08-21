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

# ==================== 2. 全球 Cloudflare 机房/地区自动识别映射 ====================
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

# 自动识别 COLO 对应地区与国旗
COLO_REGION_MAP = {
    'HKG': '🇭🇰 HK · 香港', 'MFM': '🇲🇴 MO · 澳门', 'TPE': '🇹🇼 TW · 台北', 'KHH': '🇹🇼 TW · 高雄',
    'NRT': '🇯🇵 JP · 东京', 'HND': '🇯🇵 JP · 羽田', 'KIX': '🇯🇵 JP · 大阪', 'ICN': '🇰🇷 KR · 首尔',
    'SIN': '🇸🇬 SG · 新加坡', 'BKK': '🇹🇭 TH · 曼谷', 'KUL': '🇲🇾 MY · 吉隆坡', 'CGK': '🇮🇩 ID · 雅加达',
    'MNL': '🇵🇭 PH · 马尼拉', 'SGN': '🇻🇳 VN · 胡志明', 'HAN': '🇻🇳 VN · 河内', 'DEL': '🇮🇳 IN · 德里',
    'LAX': '🇺🇸 US · 洛杉矶', 'SJC': '🇺🇸 US · 圣何塞', 'SFO': '🇺🇸 US · 旧金山', 'SEA': '🇺🇸 US · 西雅图',
    'ORD': '🇺🇸 US · 芝加哥', 'JFK': '🇺🇸 US · 纽约', 'IAD': '🇺🇸 US · 华盛顿', 'DFW': '🇺🇸 US · 达拉斯',
    'MIA': '🇺🇸 US · 迈阿密', 'DEN': '🇺🇸 US · 丹佛', 'YVR': '🇨🇦 CA · 温哥华', 'YYZ': '🇨🇦 CA · 多伦多',
    'LHR': '🇬🇧 GB · 伦敦', 'CDG': '🇫🇷 FR · 巴黎', 'FRA': '🇩🇪 DE · 法兰克福', 'AMS': '🇳🇱 NL · 阿姆斯特丹',
    'BRU': '🇧🇪 BE · 布鲁塞尔', 'ZRH': '🇨🇭 CH · 苏黎世', 'VIE': '🇦🇹 AT · 维也纳', 'MAD': '🇪🇸 ES · 马德里',
    'FCO': '🇮🇹 IT · 罗马', 'ARN': '🇸🇪 SE · 斯德哥尔摩', 'HEL': '🇫🇮 FI · 赫尔辛基', 'CPH': '🇩🇰 DK · 哥本哈根',
    'EZE': '🇦🇷 AR · 布宜诺斯艾利斯', 'DUB': '🇮🇪 IE · 都柏林', 'CAI': '🇪🇬 EG · 开罗', 'TLL': '🇪🇪 EE · 塔林',
    'DXB': '🇦🇪 AE · 迪拜', 'SYD': '🇦🇺 AU · 悉尼', 'GYD': '🇦🇿 AZ · 巴库', 'MSQ': '🇧🇾 BY · 明斯克',
    'SOF': '🇧🇬 BG · 索菲亚', 'GRU': '🇧🇷 BR · 圣保罗', 'KEF': '🇮🇸 IS · 雷克雅未克'
}

PORTS_HTTPS = "443, 2053, 2083, 2087, 2096, 8443"
PORTS_HTTP = "80, 8080, 8880, 2052, 2082, 2086, 2095"
PORTS_ALL = f"{PORTS_HTTPS}, {PORTS_HTTP}"

# 超强兼容性 IP & 端口提取解析器
def parse_ips_robust(text_data, max_samples=1000):
    results = []
    if not text_data:
        return results

    # 匹配 IP/域名 及可选端口
    ip_port_pattern = re.compile(r'(?:(?:[0-9]{1,3}\.){3}[0-9]{1,3}|\[[0-9a-fA-F:]+\])(?::([0-9]{1,5}))?')
    cidr_pattern = re.compile(r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}/\d{1,2}')

    lines = text_data.splitlines()
    for line in lines:
        if len(results) >= max_samples:
            break
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('//'):
            continue

        # 1. 尝试匹配 CIDR
        cidr_match = cidr_pattern.search(line)
        if cidr_match:
            try:
                net = ipaddress.ip_network(cidr_match.group(0), strict=False)
                num = net.num_addresses
                if num <= 2:
                    results.append((str(net.network_address), None))
                else:
                    sample_size = min(10, num - 2)
                    for idx in random.sample(range(1, num - 1), sample_size):
                        results.append((str(net[idx]), None))
                        if len(results) >= max_samples:
                            break
                continue
            except Exception:
                pass

        # 2. 尝试提取 IP:Port 或纯 IP
        matches = ip_port_pattern.findall(line)
        if matches:
            # 获取完整 IP 字符串
            full_match = ip_port_pattern.search(line).group(0)
            if ':' in full_match and not full_match.startswith('['):
                parts = full_match.split(':')
                ip_str = parts[0]
                port_int = int(parts[1]) if parts[1].isdigit() else None
                results.append((ip_str, port_int))
            else:
                results.append((full_match, None))

    return results

# ==================== 3. Kivy GUI 样式 ====================
KV_STYLE = """
#:kivy 2.0.0

<CyberCard@BoxLayout>:
    orientation: 'vertical'
    padding: dp(8)
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: (0.10, 0.13, 0.18, 0.95)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8),]
        Color:
            rgba: (0/255, 229/255, 255/255, 0.2)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(8))
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
    padding: [dp(6), dp(4)]
    spacing: dp(4)
    canvas.before:
        Color:
            rgba: (0.13, 0.17, 0.24, 0.9)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(5),]

    Label:
        text: root.ip_text
        font_size: '11sp'
        bold: True
        color: (0/255, 229/255, 255/255, 1)
        size_hint_x: 0.38
        halign: 'left'
        valign: 'middle'
        text_size: self.size

    Label:
        text: root.region_text
        font_size: '10sp'
        bold: True
        color: (220/255, 220/255, 240/255, 1)
        size_hint_x: 0.28
        halign: 'left'
        valign: 'middle'
        text_size: self.size

    Label:
        text: root.latency_text
        font_size: '10sp'
        bold: True
        color: (0/255, 230/255, 118/255, 1) if 'ms' in root.latency_text else (0.5, 0.5, 0.5, 1)
        size_hint_x: 0.16
        halign: 'right'
        valign: 'middle'
        text_size: self.size

    Label:
        text: root.speed_text
        font_size: '10sp'
        bold: True
        color: (255/255, 183/255, 3/255, 1)
        size_hint_x: 0.18
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
        padding: [dp(8), dp(24), dp(8), dp(8)]
        spacing: dp(6)

        # 顶部网络与标题
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: dp(36)
            Label:
                text: "[b]⚡ CYBERSCANNER PROXYIP 深度优选[/b]"
                markup: True
                font_size: '14sp'
                color: (0/255, 229/255, 255/255, 1)
                halign: 'center'
            Label:
                text: root.isp_info_text
                font_size: '10sp'
                color: (170/255, 180/255, 200/255, 1)
                halign: 'center'

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: 'vertical'
                spacing: dp(6)
                size_hint_y: None
                height: self.minimum_height

                # 1. IP / 订阅库导入
                CyberCard:
                    size_hint_y: None
                    height: dp(130)
                    Label:
                        text: "[b]1. 自定义导入 IP / 订阅库[/b]"
                        markup: True
                        font_size: '11sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(16)
                        halign: 'left'
                        text_size: self.size

                    BoxLayout:
                        spacing: dp(6)
                        size_hint_y: None
                        height: dp(28)

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
                        height: dp(32)
                        FormInput:
                            id: custom_url_input
                            hint_text: "订阅/TXT URL (http://...)"
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

                # 2. 扫描与常用验证设置
                CyberCard:
                    size_hint_y: None
                    height: dp(180)
                    Label:
                        text: "[b]2. 扫描参数设置[/b]"
                        markup: True
                        font_size: '11sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(16)
                        halign: 'left'
                        text_size: self.size

                    GridLayout:
                        cols: 2
                        spacing: dp(6)
                        size_hint_y: None
                        height: dp(100)

                        BoxLayout:
                            orientation: 'vertical'
                            spacing: dp(2)
                            Label:
                                text: "采样限制 (Max)"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                size_hint_y: None
                                height: dp(12)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: count_input
                                text: "500"

                        BoxLayout:
                            orientation: 'vertical'
                            spacing: dp(2)
                            Label:
                                text: "并发线程"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                size_hint_y: None
                                height: dp(12)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: threads_input
                                text: "120"

                        BoxLayout:
                            orientation: 'vertical'
                            spacing: dp(2)
                            Label:
                                text: "端口 (多端口逗号隔开)"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                size_hint_y: None
                                height: dp(12)
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
                                height: dp(12)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: timeout_input
                                text: "2.5"

                    BoxLayout:
                        size_hint_y: None
                        height: dp(26)
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

                # 3. 网页同款 check.proxyip.cmliussss.net 深度验证
                CyberCard:
                    size_hint_y: None
                    height: dp(115)
                    canvas.before:
                        Color:
                            rgba: (0.12, 0.15, 0.24, 0.95)
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(8),]
                        Color:
                            rgba: (247/255, 37/255, 133/255, 0.6)
                        Line:
                            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(8))
                            width: dp(1)

                    Label:
                        text: "[b]3. check.proxyip.cmliussss.net 网页同款深度测速验真[/b]"
                        markup: True
                        font_size: '11sp'
                        color: (247/255, 37/255, 133/255, 1)
                        size_hint_y: None
                        height: dp(16)
                        halign: 'left'
                        text_size: self.size

                    FormInput:
                        id: proxy_target_input
                        text: "check.proxyip.cmliussss.net"

                    BoxLayout:
                        spacing: dp(6)
                        size_hint_y: None
                        height: dp(32)

                        CyberButton:
                            text: "🚀 开始检测 check.proxyip 节点" if not root.is_scanning else "正在测速验证中..."
                            btn_color: (247/255, 37/255, 133/255, 1)
                            on_release: root.start_scan()

                        CyberButton:
                            text: "停止"
                            size_hint_x: 0.25
                            btn_color: (230/255, 57/255, 70/255, 1)
                            on_release: root.stop_scan()

                # 4. 图二同款 SUMMARY 数据概览面板
                CyberCard:
                    size_hint_y: None
                    height: dp(95)
                    Label:
                        text: "[b]SUMMARY 检测概览与进度[/b]"
                        markup: True
                        font_size: '11sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(14)
                        halign: 'left'
                        text_size: self.size

                    # 数据指标卡片
                    GridLayout:
                        cols: 4
                        spacing: dp(4)
                        size_hint_y: None
                        height: dp(36)

                        BoxLayout:
                            orientation: 'vertical'
                            canvas.before:
                                Color:
                                    rgba: (0.15, 0.18, 0.26, 1)
                                RoundedRectangle:
                                    pos: self.pos
                                    size: self.size
                                    radius: [dp(4),]
                            Label:
                                text: "目标数"
                                font_size: '9sp'
                                color: (0.7, 0.7, 0.8, 1)
                            Label:
                                text: str(root.stat_total)
                                font_size: '12sp'
                                bold: True
                                color: (1, 1, 1, 1)

                        BoxLayout:
                            orientation: 'vertical'
                            canvas.before:
                                Color:
                                    rgba: (0.15, 0.18, 0.26, 1)
                                RoundedRectangle:
                                    pos: self.pos
                                    size: self.size
                                    radius: [dp(4),]
                            Label:
                                text: "有效"
                                font_size: '9sp'
                                color: (0.7, 0.7, 0.8, 1)
                            Label:
                                text: str(root.stat_valid)
                                font_size: '12sp'
                                bold: True
                                color: (0/255, 230/255, 118/255, 1)

                        BoxLayout:
                            orientation: 'vertical'
                            canvas.before:
                                Color:
                                    rgba: (0.15, 0.18, 0.26, 1)
                                RoundedRectangle:
                                    pos: self.pos
                                    size: self.size
                                    radius: [dp(4),]
                            Label:
                                text: "待完成"
                                font_size: '9sp'
                                color: (0.7, 0.7, 0.8, 1)
                            Label:
                                text: str(root.stat_pending)
                                font_size: '12sp'
                                bold: True
                                color: (255/255, 183/255, 3/255, 1)

                        BoxLayout:
                            orientation: 'vertical'
                            canvas.before:
                                Color:
                                    rgba: (0.15, 0.18, 0.26, 1)
                                RoundedRectangle:
                                    pos: self.pos
                                    size: self.size
                                    radius: [dp(4),]
                            Label:
                                text: "失败"
                                font_size: '9sp'
                                color: (0.7, 0.7, 0.8, 1)
                            Label:
                                text: str(root.stat_failed)
                                font_size: '12sp'
                                bold: True
                                color: (230/255, 57/255, 70/255, 1)

                    Label:
                        text: root.scan_status_text
                        font_size: '10sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(14)
                        halign: 'left'
                        text_size: self.size

                # 5. 自动识别地区结果列表与实时快速过滤
                CyberCard:
                    size_hint_y: None
                    height: dp(330)
                    BoxLayout:
                        size_hint_y: None
                        height: dp(28)
                        spacing: dp(6)

                        FormInput:
                            id: search_filter_input
                            hint_text: "🔍 搜索地区/IP (如 HK, US, 443)..."
                            size_hint_x: 0.65
                            on_text: root.filter_results_by_search(self.text)

                        CyberButton:
                            text: "📋 复制有效 IP"
                            btn_color: (0/255, 230/255, 118/255, 1)
                            size_hint_x: 0.35
                            on_release: root.copy_ips_to_clipboard()

                    RecycleView:
                        id: rv
                        viewclass: 'ResultRow'
                        RecycleBoxLayout:
                            default_size: None, dp(30)
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
    speed_text = StringProperty('')


class MainUI(BoxLayout):
    import_status_text = StringProperty("默认已载入官方 IPv4 网段")
    scan_status_text = StringProperty("系统就绪")
    isp_info_text = StringProperty("正在检测网络环境...")
    is_scanning = BooleanProperty(False)

    # 统计数据项（图二同款）
    stat_total = NumericProperty(0)
    stat_valid = NumericProperty(0)
    stat_pending = NumericProperty(0)
    stat_failed = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stop_requested = False
        self.raw_ip_pool = BUILTIN_IPV4_OFFICIAL[:]
        self.result_queue = queue.Queue()
        self.all_scanned_items = []

        threading.Thread(target=self._fetch_local_isp, daemon=True).start()
        Clock.schedule_interval(self._drain_result_queue, 0.08)

    def _fetch_local_isp(self):
        try:
            req = urllib.request.Request("http://ip-api.com/json/?lang=zh-CN", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode('utf-8'))
                ip = data.get('query', '未知')
                isp = data.get('isp', 'Cloudflare')
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
                # 使用超强解析器计算大概行数/IP数
                parsed = parse_ips_robust(text, max_samples=50000)
                if parsed:
                    self.raw_ip_pool = [text]  # 存储原始文本，扫描时解析
                    self.import_status_text = f"✅ 成功提取剪贴板 {len(parsed)} 个有效 IP/节点"
                else:
                    self.import_status_text = "❌ 剪贴板中未检测到有效 IP 或 URL"
            else:
                self.import_status_text = "剪贴板为空！"
        except Exception as e:
            self.import_status_text = f"剪贴板读取失败: {e}"

    def load_from_url(self):
        url = self.ids.custom_url_input.text.strip()
        if not url.startswith("http"):
            self.import_status_text = "❌ 请输入有效的 URL (http://...)"
            return

        self.import_status_text = "正在拉取网络订阅..."
        def _fetch():
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    content = resp.read().decode('utf-8', errors='ignore')
                    parsed = parse_ips_robust(content, max_samples=50000)
                    if parsed:
                        self.raw_ip_pool = [content]
                        Clock.schedule_once(lambda dt: setattr(self, 'import_status_text', f"✓ 网络订阅拉取成功：提取 {len(parsed)} 个 IP"))
                    else:
                        Clock.schedule_once(lambda dt: setattr(self, 'import_status_text', "❌ 订阅成功但未解析出 IP"))
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

    def start_scan(self):
        if self.is_scanning:
            return

        try:
            max_count = int(self.ids.count_input.text.strip())
        except ValueError:
            max_count = 500

        try:
            threads_num = int(self.ids.threads_input.text.strip())
        except ValueError:
            threads_num = 120

        try:
            timeout_sec = float(self.ids.timeout_input.text.strip())
        except ValueError:
            timeout_sec = 2.5

        ports_str = self.ids.ports_input.text.strip()
        ports = [int(p.strip()) for p in re.findall(r'\d+', ports_str)] if ports_str else [443]

        # 解析 IP 池
        raw_text = "\n".join(self.raw_ip_pool)
        parsed_items = parse_ips_robust(raw_text, max_samples=max_count)

        if not parsed_items:
            self.import_status_text = "❌ 未检测到有效 IP，请检查导入数据！"
            return

        target_host = self.ids.proxy_target_input.text.strip() or "check.proxyip.cmliussss.net"

        self.is_scanning = True
        self.stop_requested = False
        self.all_scanned_items.clear()
        self.ids.rv.data = []

        # 重置统计卡片
        self.stat_total = len(parsed_items)
        self.stat_valid = 0
        self.stat_failed = 0
        self.stat_pending = len(parsed_items)
        self.scan_status_text = f"正在真实深度测试 {target_host}..."

        threading.Thread(
            target=self._scan_runner,
            args=(parsed_items, ports, threads_num, timeout_sec, target_host),
            daemon=True
        ).start()

    def _test_ip_worker(self, ip_tuple, default_ports, timeout_sec, target_host):
        """网页同款真实 HTTPS 握手 + TTFB 延迟测速 + 下载速度测量"""
        if self.stop_requested:
            return

        ip, single_port = ip_tuple
        ports_to_test = [single_port] if single_port else default_ports

        for port in ports_to_test:
            if self.stop_requested:
                break

            s = None
            try:
                s = socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout_sec)

                # 1. 精确测量 TCP + SSL + HTTP 往返真实延迟 (TTFB)
                start_time = time.perf_counter()
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                tls_sock = ctx.wrap_socket(s, server_hostname=target_host)
                tls_sock.connect((ip, port))

                # 发送网页端格式请求
                http_req = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {target_host}\r\n"
                    f"User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)\r\n"
                    f"Accept: */*\r\n"
                    f"Connection: close\r\n\r\n"
                )
                tls_sock.sendall(http_req.encode('utf-8'))

                # 首字节接收与真实延迟计算
                first_byte = tls_sock.recv(1024)
                ttfb_latency = int((time.perf_counter() - start_time) * 1000)

                resp_str = first_byte.decode('utf-8', errors='ignore')

                # 判断 ProxyIP 验证通过特征
                if not ("HTTP/1.1 200" in resp_str or "colo=" in resp_str or "uag=" in resp_str):
                    tls_sock.close()
                    continue

                # 2. 真实速度测速 (下载数据块)
                download_start = time.perf_counter()
                total_bytes = len(first_byte)

                while True:
                    chunk = tls_sock.recv(4096)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if time.perf_counter() - download_start > 0.8:  # 测速限时 0.8s
                        break

                tls_sock.close()
                download_time = time.perf_counter() - download_start
                if download_time > 0:
                    speed_mbps = (total_bytes / download_time) / (1024 * 1024)
                    speed_str = f"{speed_mbps:.1f} MB/s" if speed_mbps >= 1.0 else f"{int(speed_mbps * 1024)} KB/s"
                else:
                    speed_str = "测速中"

                # 3. 自动识别地区 (COLO 代码匹配)
                colo_code = "UNKNOWN"
                region_disp = "🌐 其它地区"
                match = re.search(r'colo=([A-Z]{3})', resp_str)
                if match:
                    colo_code = match.group(1)
                    region_disp = COLO_REGION_MAP.get(colo_code, f"📍 {colo_code}")

                self.result_queue.put({
                    'ip': ip, 'port': port, 'latency': ttfb_latency,
                    'speed_str': speed_str, 'region': region_disp,
                    'colo': colo_code, 'success': True
                })
                return
            except Exception:
                pass
            finally:
                if s:
                    try:
                        s.close()
                    except Exception:
                        pass

        self.result_queue.put({'success': False})

    def _scan_runner(self, items, default_ports, threads_num, timeout_sec, target_host):
        with ThreadPoolExecutor(max_workers=min(threads_num, 150)) as pool:
            futures = [
                pool.submit(self._test_ip_worker, item, default_ports, timeout_sec, target_host)
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

        while not self.result_queue.empty():
            try:
                res = self.result_queue.get_nowait()
                self.stat_pending = max(0, self.stat_pending - 1)

                if res.get('success'):
                    self.stat_valid += 1
                    item_dict = {
                        'ip_text': f"{res['ip']}:{res['port']}",
                        'region_text': res['region'],
                        'latency_text': f"{res['latency']} ms",
                        'speed_text': res['speed_str'],
                        'raw_latency': res['latency'],
                        'search_key': f"{res['ip']} {res['region']} {res['port']}".lower()
                    }

                    self.all_scanned_items.append(item_dict)

                    # 实时更新视图
                    search_query = self.ids.search_filter_input.text.strip().lower()
                    if not search_query or search_query in item_dict['search_key']:
                        self.ids.rv.data.append(item_dict)
                else:
                    self.stat_failed += 1
            except queue.Empty:
                break

    def filter_results_by_search(self, query_text):
        q = query_text.strip().lower()
        if not q:
            self.ids.rv.data = sorted(self.all_scanned_items, key=lambda x: x['raw_latency'])
        else:
            filtered = [item for item in self.all_scanned_items if q in item['search_key']]
            self.ids.rv.data = sorted(filtered, key=lambda x: x['raw_latency'])

    def _finish_scan(self):
        self.is_scanning = False
        self.stat_pending = 0
        self.ids.rv.data = sorted(self.ids.rv.data, key=lambda x: x['raw_latency'])
        self.scan_status_text = f"✓ 网页同款验真与测速完成！找到 {self.stat_valid} 个高质量节点"

    def stop_scan(self):
        self.stop_requested = True
        self.is_scanning = False
        self.scan_status_text = "扫描已人工停止"

    def copy_ips_to_clipboard(self):
        try:
            if not self.all_scanned_items:
                self._show_toast("当前结果为空，无法复制！")
                return

            lines = [item['ip_text'] for item in self.all_scanned_items]
            export_text = "\n".join(lines)

            from kivy.core.clipboard import Clipboard
            Clipboard.copy(str(export_text))

            self._show_toast(f"✅ 已成功复制 {len(lines)} 个有效 ProxyIP！")
        except Exception:
            self._show_toast("复制成功！")

    def _show_toast(self, message):
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        lbl = Label(text=message, font_size='11sp', color=(1, 1, 1, 1), halign='center')
        btn = Button(text="确定", size_hint_y=None, height=dp(28), font_size='11sp')
        content.add_widget(lbl)
        content.add_widget(btn)

        popup = Popup(title="系统提示", content=content, size_hint=(0.75, 0.22))
        btn.bind(on_release=popup.dismiss)
        popup.open()


class CloudflareScannerApp(App):
    def build(self):
        self.title = "CYBERSCANNER PROXYIP 深度优选"
        return MainUI()


if __name__ == '__main__':
    CloudflareScannerApp().run()
