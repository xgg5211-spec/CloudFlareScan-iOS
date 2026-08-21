import gc
import glob
import ipaddress
import json
import os
import queue
import random
import re
import socket
import ssl
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.text import DEFAULT_FONT, LabelBase
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

# ==================== 1. iOS 中文字体自动修复 ====================
def init_ios_cjk_font():
    font_candidates = [
        "/System/Library/Fonts/LanguageSupport/PingFang.ttc",
        "/System/Library/Fonts/CoreUI/PingFang.ttc",
        "/System/Library/Fonts/Core/STHeiti-Light.ttc",
        "/System/Library/Fonts/Core/STHeiti-Medium.ttc",
        "/System/Library/Fonts/STHeiti-Light.ttc",
        "/System/Library/Fonts/AppFonts/PingFang.ttc",
    ]
    chosen_font = None
    for path in font_candidates:
        if os.path.exists(path):
            chosen_font = path
            break

    if not chosen_font:
        matches = glob.glob("/System/Library/Fonts/**/*PingFang*.ttc", recursive=True)
        if not matches:
            matches = glob.glob("/System/Library/Fonts/**/*Heiti*.ttc", recursive=True)
        if matches:
            chosen_font = matches[0]

    if chosen_font:
        try:
            LabelBase.register(name=DEFAULT_FONT, fn_regular=chosen_font)
            LabelBase.register(name="Roboto", fn_regular=chosen_font)
        except Exception as e:
            print(f"[FontManager] 注册字体失败: {e}")

init_ios_cjk_font()

# ==================== 2. 内置 IP 库与零内存万能流式解析引擎 ====================
BUILTIN_IPV4_OFFICIAL = [
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
    "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22"
]

BUILTIN_APAC_PREFERRED = [
    "104.16.0.0/15", "104.18.0.0/15", "104.20.0.0/15", "104.22.0.0/15",
    "172.64.0.0/15", "172.66.0.0/15", "162.159.0.0/16", "108.162.192.0/19",
    "141.101.64.0/19", "188.114.96.0/20"
]

BUILTIN_IPV6_OFFICIAL = [
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32",
    "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32"
]

COLO_MAP = {
    'HKG': '🇭🇰 香港',
    'NRT': '🇯🇵 东京', 'HND': '🇯🇵 羽田', 'KIX': '🇯🇵 大阪',
    'SIN': '🇸🇬 新加坡', 'ICN': '🇰🇷 首尔', 'TPE': '🇹🇼 台北',
    'LAX': '🇺🇸 洛杉矶', 'SJC': '🇺🇸 圣何塞', 'SEA': '🇺🇸 西雅图',
    'SFO': '🇺🇸 旧金山', 'ORD': '🇺🇸 芝加哥', 'JFK': '🇺🇸 纽约',
    'FRA': '🇩🇪 法兰克福', 'LHR': '🇬🇧 伦敦', 'CDG': '🇫🇷 巴黎',
    'SYD': '🇦🇺 悉尼', 'MEL': '🇦🇺 墨尔本', 'BKK': '🇹🇭 曼谷',
    'MNL': '🇵🇭 马尼拉', 'SGN': '🇻🇳 胡志明', 'KUL': '🇲🇾 吉隆坡',
}

def mask_ip_addr(ip_str):
    """IP 隐藏脱敏算法"""
    if not ip_str or ip_str == "未知":
        return "未知"
    if ":" in ip_str and not ip_str.startswith("http"):  # IPv6
        parts = ip_str.split(":")
        if len(parts) >= 4:
            return f"{parts[0]}:{parts[1]}:****:****"
        return ip_str[:8] + "****"
    parts = ip_str.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.***.***"
    return ip_str

def ultra_fast_ip_parser_capped(text, max_total_samples=3000):
    """零内存流式解析引擎：支持上万 IP 及大网段快速抽样"""
    found_ips = set()
    if not text:
        return []

    lines = text.splitlines()
    cidr_pattern = re.compile(r'(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}')
    ip_pattern = re.compile(r'(?:\d{1,3}\.){3}\d{1,3}')

    for line in lines:
        if len(found_ips) >= max_total_samples:
            break
        line = line.strip().strip('"\'[],;')
        if not line or line.startswith('#'):
            continue

        cidr_match = cidr_pattern.search(line)
        if cidr_match:
            cidr_str = cidr_match.group(0)
            try:
                net = ipaddress.ip_network(cidr_str, strict=False)
                num_hosts = net.num_addresses
                if num_hosts <= 2:
                    found_ips.add(str(net.network_address))
                else:
                    samples_to_take = min(15, num_hosts - 2)
                    sample_indices = random.sample(range(1, num_hosts - 1), samples_to_take)
                    for idx in sample_indices:
                        found_ips.add(str(net[idx]))
                        if len(found_ips) >= max_total_samples:
                            break
            except Exception:
                pass
            continue

        ip_match = ip_pattern.search(line)
        if ip_match:
            ip_str = ip_match.group(0)
            try:
                parts = ip_str.split('.')
                if len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts):
                    found_ips.add(ip_str)
            except Exception:
                pass

    return list(found_ips)

# ==================== 3. 赛博朋克 GUI 界面 ====================
KV_STYLE = """
#:kivy 2.0.0

<StatCard@BoxLayout>:
    orientation: 'vertical'
    padding: [dp(4), dp(2)]
    title: ''
    value: ''
    value_color: (0/255, 243/255, 255/255, 1)
    canvas.before:
        Color:
            rgba: (18/255, 24/255, 35/255, 0.95)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(6),]
        Color:
            rgba: (0/255, 243/255, 255/255, 0.35)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(6))
            width: 0.9
    Label:
        text: root.title
        font_size: '10sp'
        color: (140/255, 155/255, 175/255, 1)
        size_hint_y: 0.4
        shorten: True
    Label:
        text: root.value
        font_size: '12sp'
        bold: True
        color: root.value_color
        size_hint_y: 0.6
        shorten: True

<CyberButton@Button>:
    background_normal: ''
    background_color: 0, 0, 0, 0
    font_size: '11sp'
    bold: True
    color: (0/255, 243/255, 255/255, 1) if self.state == 'normal' else (1, 1, 1, 1)
    canvas.before:
        Color:
            rgba: (0/255, 243/255, 255/255, 0.8) if self.state == 'normal' else (255/255, 0/255, 85/255, 1)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(6))
            width: 1.1
        Color:
            rgba: (14/255, 20/255, 30/255, 0.9)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(6),]

<RegionBtn@Button>:
    background_normal: ''
    background_color: 0, 0, 0, 0
    font_size: '10sp'
    bold: True
    is_selected: False
    color: (255/255, 0/255, 136/255, 1) if self.is_selected else (170/255, 185/255, 200/255, 1)
    canvas.before:
        Color:
            rgba: (255/255, 0/255, 136/255, 0.9) if self.is_selected else (40/255, 55/255, 75/255, 0.6)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(4))
            width: 1
        Color:
            rgba: (22/255, 30/255, 45/255, 0.95)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(4),]

<MainUI>:
    canvas.before:
        Color:
            rgba: (9/255, 13/255, 20/255, 1)
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: [dp(10), dp(28), dp(10), dp(8)]
        spacing: dp(5)

        # 1. 顶部标题栏
        BoxLayout:
            size_hint_y: None
            height: dp(24)
            Label:
                text: "[b][color=00f3ff]CLOUDFLARE[/color] [color=ff0055]CYBER[/color] [color=888888]v4.2[/color][/b]"
                markup: True
                font_size: '15sp'
                halign: 'left'
                text_size: self.size
                valign: 'middle'

            Label:
                text: root.status_text
                color: (0/255, 255/255, 136/255, 1)
                font_size: '11sp'
                halign: 'right'
                text_size: self.size
                valign: 'middle'

        # 2. 运营商看板
        BoxLayout:
            size_hint_y: None
            height: dp(26)
            canvas.before:
                Color:
                    rgba: (20/255, 30/255, 45/255, 0.85)
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [dp(4),]
            padding: [dp(8), 0]
            Label:
                text: root.isp_info_text
                markup: True
                font_size: '11sp'
                color: (0/255, 243/255, 255/255, 1)
                halign: 'left'
                text_size: self.size
                valign: 'middle'
                shorten: True

        # 3. 统计看板
        BoxLayout:
            size_hint_y: None
            height: dp(40)
            spacing: dp(5)

            StatCard:
                title: "测试进度"
                value: f"{root.scanned_count}/{root.total_count}"
                value_color: (0/255, 243/255, 255/255, 1)

            StatCard:
                title: "有效 IP"
                value: str(root.valid_count)
                value_color: (0/255, 255/255, 136/255, 1)

            StatCard:
                title: "最低 TLS"
                value: root.min_latency_text
                value_color: (255/255, 204/255, 0/255, 1)

            StatCard:
                title: "最高下载"
                value: root.max_speed_text
                value_color: (255/255, 0/255, 136/255, 1)

        # 4. 端口与库选择菜单（含 ▼ 符号指示）
        BoxLayout:
            size_hint_y: None
            height: dp(28)
            spacing: dp(4)

            Spinner:
                id: port_spinner
                text: '🔌 端口: 443 ▼'
                values: ['🔌 端口: 443 ▼', '⚡ 自适应端口 ▼', '🔌 端口: 8443 ▼', '🔌 端口: 2053 ▼', '🔌 端口: 80 ▼']
                size_hint_x: 0.38
                font_size: '10sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (0/255, 243/255, 255/255, 1)

            Spinner:
                id: source_spinner
                text: '📦 库: 亚太优选 ▼'
                values: ['📦 库: 亚太优选 ▼', '📦 库: 官方IPv4 ▼', '📦 库: 官方IPv6 ▼', '🌐 库: 在线URL ▼', '📋 库: 剪贴板 ▼']
                size_hint_x: 0.38
                font_size: '10sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (0/255, 255/255, 136/255, 1)
                on_text: root.on_source_change(self.text)

            Spinner:
                id: count_spinner
                text: '🎯 测 300个 ▼'
                values: ['🎯 测 100个 ▼', '🎯 测 300个 ▼', '🎯 测 500个 ▼', '🎯 测 1000个 ▼']
                size_hint_x: 0.24
                font_size: '10sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (255/255, 204/255, 0/255, 1)

        # 5. 地区快速筛选
        BoxLayout:
            size_hint_y: None
            height: dp(26)
            spacing: dp(4)

            RegionBtn:
                text: "🌐 全部"
                is_selected: root.selected_region == "ALL"
                on_release: root.select_region("ALL")

            RegionBtn:
                text: "🇭🇰 香港"
                is_selected: root.selected_region == "HK"
                on_release: root.select_region("HK")

            RegionBtn:
                text: "🇯🇵 日本"
                is_selected: root.selected_region == "JP"
                on_release: root.select_region("JP")

            RegionBtn:
                text: "🇸🇬 新加坡"
                is_selected: root.selected_region == "SG"
                on_release: root.select_region("SG")

            RegionBtn:
                text: "🇺🇸 美国"
                is_selected: root.selected_region == "US"
                on_release: root.select_region("US")

            RegionBtn:
                text: "🌐 其他"
                is_selected: root.selected_region == "OTHER"
                on_release: root.select_region("OTHER")

        # 6. IP 输入框
        BoxLayout:
            size_hint_y: 0.18
            TextInput:
                id: ip_input
                hint_text: "点击下拉菜单选择 IP 库，或直接在框内粘贴上万自定义 CIDR / IP 文本..."
                background_color: (15/255, 20/255, 28/255, 1)
                foreground_color: (0/255, 243/255, 255/255, 1)
                cursor_color: (255/255, 0/255, 85/255, 1)
                font_size: '10sp'
                padding: [dp(6), dp(6)]

        # 7. 操作按钮栏（纯【复制 IP】按钮）
        BoxLayout:
            size_hint_y: None
            height: dp(32)
            spacing: dp(4)

            CyberButton:
                text: "刷新 IP 库"
                size_hint_x: 0.22
                on_release: root.load_current_source_ip()

            CyberButton:
                text: root.mask_button_text
                size_hint_x: 0.24
                on_release: root.toggle_ip_mask()

            CyberButton:
                text: "🛑 停止" if root.is_scanning else "🚀 开始 TLS 测速"
                size_hint_x: 0.32
                on_release: root.toggle_scan()

            CyberButton:
                text: "📋 复制 IP"
                size_hint_x: 0.22
                on_release: root.copy_ips_to_clipboard()

        # 8. 终端日志视窗
        BoxLayout:
            orientation: 'vertical'
            canvas.before:
                Color:
                    rgba: (8/255, 11/255, 16/255, 0.95)
                Rectangle:
                    pos: self.pos
                    size: self.size
                Color:
                    rgba: (0/255, 243/255, 255/255, 0.25)
                Line:
                    rounded_rectangle: (self.x, self.y, self.width, self.height, dp(6))
                    width: 1
            Label:
                id: log_label
                text: root.log_content
                markup: True
                font_size: '10sp'
                padding: [dp(6), dp(6)]
                halign: 'left'
                valign: 'top'
                text_size: self.size
"""

Builder.load_string(KV_STYLE)


class MainUI(BoxLayout):
    status_text = StringProperty("系统就绪")
    isp_info_text = StringProperty("🔍 正在识别本地运营商与出口 IP...")
    log_content = StringProperty("[color=00f3ff]=== Cloudflare CyberScanner v4.2 ===[/color]\n• 已增加 [▼] 下拉提示符\n• 测速引擎丝滑不卡顿，支持万级 IP 快速解析\n• 测速完成后点击 [📋 复制 IP] 即可复制 IP 列表\n")
    is_scanning = BooleanProperty(False)
    is_ip_masked = BooleanProperty(False)
    mask_button_text = StringProperty("🙈 遮罩: 关")
    selected_region = StringProperty("ALL")

    scanned_count = NumericProperty(0)
    total_count = NumericProperty(0)
    valid_count = NumericProperty(0)
    min_latency_text = StringProperty("-- ms")
    max_speed_text = StringProperty("-- MB/s")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stop_requested = False
        self.best_ips = []
        self.display_log_lines = self.log_content.splitlines()

        self.result_queue = queue.Queue()

        self.raw_public_ip = "未知"
        self.raw_isp_name = "未知"
        self.raw_city = ""

        # 主线程 80ms 批量更新队列，保证 60 帧极丝滑
        Clock.schedule_interval(self._drain_result_queue, 0.08)

        Clock.schedule_once(lambda dt: self.load_current_source_ip(), 0.2)
        Clock.schedule_once(lambda dt: self.detect_isp_info(), 0.5)

    def append_log(self, text):
        self.display_log_lines.append(text)
        if len(self.display_log_lines) > 25:
            self.display_log_lines = self.display_log_lines[-25:]
        self.log_content = "\n".join(self.display_log_lines)

    def select_region(self, region_code):
        self.selected_region = region_code
        names = {"ALL": "全部分区", "HK": "🇭🇰 香港", "JP": "🇯🇵 日本", "SG": "🇸🇬 新加坡", "US": "🇺🇸 美国", "OTHER": "🌐 其他地区"}
        self.append_log(f"[🌐 筛选] 已切换目标: [color=ff0088]{names.get(region_code)}[/color]")

    def toggle_ip_mask(self):
        self.is_ip_masked = not self.is_ip_masked
        if self.is_ip_masked:
            self.mask_button_text = "🙈 遮罩: 开"
            self.append_log("[🔒 隐私] 已开启 IP 隐私遮罩。")
        else:
            self.mask_button_text = "🙈 遮罩: 关"
            self.append_log("[🔓 隐私] 已关闭 IP 隐私遮罩。")

        self.update_isp_display()

    def update_isp_display(self):
        display_ip = mask_ip_addr(self.raw_public_ip) if self.is_ip_masked else self.raw_public_ip
        city_str = f" ({self.raw_city})" if self.raw_city else ""
        self.isp_info_text = f"🌐 运营商: [color=00ff88]{self.raw_isp_name}[/color]  公网IP: [color=00f3ff]{display_ip}[/color]{city_str}"

    def detect_isp_info(self):
        threading.Thread(target=self._detect_isp_worker, daemon=True).start()

    def _detect_isp_worker(self):
        try:
            req = urllib.request.Request("http://ip-api.com/json/?lang=zh-CN", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                self.raw_public_ip = data.get('query', '未知')
                isp = data.get('isp', data.get('org', '未知'))
                self.raw_city = data.get('city', '')

                if "Telecom" in isp or "电信" in isp:
                    self.raw_isp_name = "中国电信"
                elif "Unicom" in isp or "联通" in isp:
                    self.raw_isp_name = "中国联通"
                elif "Mobile" in isp or "移动" in isp:
                    self.raw_isp_name = "中国移动"
                else:
                    self.raw_isp_name = isp
        except Exception:
            pass

        Clock.schedule_once(lambda dt: self.update_isp_display())

    def on_source_change(self, source_text):
        self.load_current_source_ip(source_text)

    def load_current_source_ip(self, source_name=None):
        if not source_name:
            source_name = self.ids.source_spinner.text

        if "亚太优选" in source_name:
            self.ids.ip_input.text = "\n".join(BUILTIN_APAC_PREFERRED)
            self.status_text = f"已载入 {len(BUILTIN_APAC_PREFERRED)} 网段"
            self.append_log(f"[✓] 已载入 {len(BUILTIN_APAC_PREFERRED)} 个【亚太优选网段】")

        elif "官方IPv4" in source_name:
            self.ids.ip_input.text = "\n".join(BUILTIN_IPV4_OFFICIAL)
            self.status_text = f"已载入 {len(BUILTIN_IPV4_OFFICIAL)} 网段"
            self.append_log(f"[✓] 已载入 {len(BUILTIN_IPV4_OFFICIAL)} 个【官方 IPv4 网段】")

        elif "官方IPv6" in source_name:
            self.ids.ip_input.text = "\n".join(BUILTIN_IPV6_OFFICIAL)
            self.status_text = f"已载入 {len(BUILTIN_IPV6_OFFICIAL)} 网段"
            self.append_log(f"[✓] 已载入 {len(BUILTIN_IPV6_OFFICIAL)} 个【官方 IPv6 网段】")

        elif "剪贴板" in source_name:
            text = Clipboard.paste()
            if text and text.strip():
                self.ids.ip_input.text = text.strip()
                self.append_log("[✓] 已成功读取并粘贴剪贴板内容！")
            else:
                self.append_log("[!] 剪贴板为空。")

        elif "在线URL" in source_name:
            self.show_url_import_dialog()

    def show_url_import_dialog(self):
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        url_input = TextInput(
            text="https://raw.githubusercontent.com/ip-thailand/cloudflare-ip/main/cloudflare-ipv4.txt",
            hint_text="输入 TXT 订阅链接",
            multiline=False, size_hint_y=None, height=dp(38), font_size='11sp'
        )
        btn_box = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
        btn_confirm = CyberButton(text="下载导入")
        btn_cancel = CyberButton(text="取消")
        btn_box.add_widget(btn_confirm)
        btn_box.add_widget(btn_cancel)
        content.add_widget(url_input)
        content.add_widget(btn_box)

        popup = Popup(title="🌐 下载在线 IP 库", content=content, size_hint=(0.88, 0.32))

        def on_confirm(instance):
            url = url_input.text.strip()
            if url:
                popup.dismiss()
                self.status_text = "下载中..."
                self.append_log(f"[+] 下载在线 IP 库: {url}")
                threading.Thread(target=self._fetch_url_worker, args=(url,), daemon=True).start()

        btn_confirm.bind(on_release=on_confirm)
        btn_cancel.bind(on_release=popup.dismiss)
        popup.open()

    def _fetch_url_worker(self, url):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, context=ctx, timeout=7) as response:
                content = response.read().decode('utf-8')
                Clock.schedule_once(lambda dt: self._on_ip_fetch_success(content))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.append_log(f"[X] 下载失败: {e}"))

    def _on_ip_fetch_success(self, content):
        self.ids.ip_input.text = content
        self.append_log("[✓] 在线 IP 库拉取成功！已填入。")

    def toggle_scan(self):
        if self.is_scanning:
            self.stop_scan()
        else:
            self.start_scan()

    def start_scan(self):
        raw_text = self.ids.ip_input.text.strip()
        if not raw_text:
            self.append_log("[!] 请先选择或粘贴 IP 文本。")
            return

        sample_str = self.ids.count_spinner.text
        max_samples = 300
        if "100" in sample_str:
            max_samples = 100
        elif "500" in sample_str:
            max_samples = 500
        elif "1000" in sample_str:
            max_samples = 1000

        parsed_ips = ultra_fast_ip_parser_capped(raw_text, max_total_samples=max_samples * 2)
        if not parsed_ips:
            self.append_log("[!] 未能解析到可用 IP，请检查输入。")
            return

        self.is_scanning = True
        self.stop_requested = False
        self.status_text = "⚡ 测速中..."
        self.scanned_count = 0
        self.valid_count = 0
        self.min_latency_text = "-- ms"
        self.max_speed_text = "-- MB/s"
        self.best_ips.clear()

        random.shuffle(parsed_ips)
        target_ips = parsed_ips[:max_samples]
        self.total_count = len(target_ips)

        port_selection = self.ids.port_spinner.text
        self.append_log(f"[+] 开始对 [color=00f3ff]{len(target_ips)}[/color] 个节点执行 TLS 真实握手测速...")

        threading.Thread(target=self._scan_runner, args=(target_ips, port_selection), daemon=True).start()

    def _test_single_ip(self, ip, port_selection):
        if self.stop_requested:
            return

        if "自适应" in port_selection:
            test_ports = [443, 8443, 2053, 80]
        else:
            nums = re.findall(r'\d+', port_selection)
            test_ports = [int(nums[0])] if nums else [443]

        for port in test_ports:
            if self.stop_requested:
                break
            is_ssl = port in [443, 8443, 2053, 2083]
            s = socket.socket(socket.AF_INET if ":" not in ip else socket.AF_INET6, socket.SOCK_STREAM)
            s.settimeout(1.1)
            start_t = time.perf_counter()
            colo_str = "未知"

            try:
                if is_ssl:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    tls_sock = ctx.wrap_socket(s, server_hostname="speed.cloudflare.com")
                    tls_sock.connect((ip, port))
                    latency = round((time.perf_counter() - start_t) * 1000, 1)

                    try:
                        req = "GET /cdn-cgi/trace HTTP/1.1\r\nHost: speed.cloudflare.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
                        tls_sock.sendall(req.encode('utf-8'))
                        resp = tls_sock.recv(1024)
                        text = resp.decode('utf-8', errors='ignore')
                        match = re.search(r'colo=([A-Z]{3})', text)
                        if match:
                            raw_colo = match.group(1).upper()
                            colo_str = COLO_MAP.get(raw_colo, f"🌐 {raw_colo}")
                    except Exception:
                        pass
                    tls_sock.close()
                else:
                    s.connect((ip, port))
                    latency = round((time.perf_counter() - start_t) * 1000, 1)
                    s.close()

                self.result_queue.put({'ip': ip, 'latency': latency, 'colo': colo_str, 'port': port, 'success': True})
                return
            except Exception:
                pass
            finally:
                try:
                    s.close()
                except Exception:
                    pass

        self.result_queue.put({'ip': ip, 'latency': None, 'colo': "超时", 'port': 443, 'success': False})

    def _scan_runner(self, ip_list, port_selection):
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(self._test_single_ip, ip, port_selection) for ip in ip_list]
            for future in futures:
                if self.stop_requested:
                    break
                future.result()

        if self.best_ips and not self.stop_requested:
            Clock.schedule_once(lambda dt: self.append_log("[+] 发起 [color=ff0088]HTTP 真实下载速度测试[/color]..."))
            top_3 = sorted(self.best_ips, key=lambda x: x['latency'])[:3]
            for item in top_3:
                if self.stop_requested:
                    break
                speed = self._test_download_speed_sync(item['ip'], item['port'])
                item['speed'] = speed
                display_ip = mask_ip_addr(item['ip']) if self.is_ip_masked else item['ip']
                if speed > 0:
                    Clock.schedule_once(lambda dt, dip=display_ip, spd=speed: self.append_log(f"[🚀 测速] {dip:<15} 速度: [color=ff0088]{spd} MB/s[/color]"))

            max_s = max(x['speed'] for x in self.best_ips)
            if max_s > 0:
                Clock.schedule_once(lambda dt, ms=max_s: setattr(self, 'max_speed_text', f"{ms} MB/s"))

        Clock.schedule_once(lambda dt: self._finish_scan())

    def _drain_result_queue(self, dt):
        if self.result_queue.empty():
            return

        batch_count = 0
        while not self.result_queue.empty() and batch_count < 30:
            try:
                res = self.result_queue.get_nowait()
                batch_count += 1
                self.scanned_count += 1

                if res['success']:
                    ip = res['ip']
                    latency = res['latency']
                    colo = res['colo']
                    used_port = res['port']

                    region_ok = False
                    if self.selected_region == "ALL":
                        region_ok = True
                    elif self.selected_region == "HK" and "香港" in colo:
                        region_ok = True
                    elif self.selected_region == "JP" and ("东京" in colo or "大阪" in colo or "羽田" in colo):
                        region_ok = True
                    elif self.selected_region == "SG" and "新加坡" in colo:
                        region_ok = True
                    elif self.selected_region == "US" and ("洛杉矶" in colo or "圣何塞" in colo or "西雅图" in colo or "旧金山" in colo or "芝加哥" in colo or "纽约" in colo):
                        region_ok = True
                    elif self.selected_region == "OTHER" and not any(k in colo for k in ["香港", "东京", "大阪", "羽田", "新加坡", "洛杉矶", "圣何塞"]):
                        region_ok = True

                    if region_ok:
                        self.valid_count += 1
                        self.best_ips.append({'ip': ip, 'port': used_port, 'latency': latency, 'colo': colo, 'speed': 0.0})

                        min_lat = min(x['latency'] for x in self.best_ips)
                        self.min_latency_text = f"{min_lat} ms"

                        display_ip = mask_ip_addr(ip) if self.is_ip_masked else ip
                        self.append_log(f"[✓] {display_ip:<15} [{colo}] TLS:{latency}ms ({used_port}端口)")
            except queue.Empty:
                break

    def _test_download_speed_sync(self, ip, port):
        is_ssl = port in [443, 8443, 2053, 2083]
        s = socket.socket(socket.AF_INET if ":" not in ip else socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout(2.2)
        try:
            start_t = time.perf_counter()
            if is_ssl:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                tls_sock = ctx.wrap_socket(s, server_hostname="speed.cloudflare.com")
                tls_sock.connect((ip, port))
                conn = tls_sock
            else:
                s.connect((ip, port))
                conn = s

            req = f"GET /__down?bytes=2500000 HTTP/1.1\r\nHost: speed.cloudflare.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
            conn.sendall(req.encode('utf-8'))

            downloaded = 0
            while True:
                chunk = conn.recv(16384)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded >= 2500000:
                    break

            conn.close()
            duration = time.perf_counter() - start_t
            if duration > 0 and downloaded > 50000:
                return round((downloaded / (1024 * 1024)) / duration, 2)
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
        return 0.0

    def _finish_scan(self):
        if self.best_ips:
            self.best_ips.sort(key=lambda x: (x['latency'], -x['speed']))
            self.append_log("\n[b][color=00ff88]🏆 TOP 5 优选节点榜单:[/color][/b]")
            for idx, item in enumerate(self.best_ips[:5], start=1):
                display_ip = mask_ip_addr(item['ip']) if self.is_ip_masked else item['ip']
                speed_str = f" | {item['speed']} MB/s" if item['speed'] > 0 else ""
                self.append_log(f" {idx}. {display_ip:<15} [{item['colo']}] - {item['latency']}ms ({item['port']}端口){speed_str}")

        self.append_log("\n[✓] [color=00f3ff]测速完成！点击【📋 复制 IP】直接复制优选 IP 列表。[/color]")
        self.is_scanning = False
        self.status_text = "✓ 完成"
        gc.collect()

    # ---------------- 纯粹【一键复制 IP】功能 ----------------
    def copy_ips_to_clipboard(self):
        if not self.best_ips:
            self.append_log("[!] 暂无可用测速数据，请先开始测速。")
            return

        # 仅生成干净的 IP:端口 列表，每行一个，无任何多余注释或复杂格式
        ip_lines = [f"{item['ip']}:{item['port']}" for item in self.best_ips]
        export_text = "\n".join(ip_lines)

        Clipboard.copy(export_text)  # 写入系统剪贴板

        copied_count = len(ip_lines)
        self.append_log(f"[📋 复制] [color=00ff88]已将 {copied_count} 个优选 IP 写入剪贴板！[/color]")

        # 简洁的弹出提示
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        msg = Label(
            text=f"✅ 成功复制 {copied_count} 个优选 IP！\n\n格式为标准的「IP:端口」（每行一个），可直接粘贴使用。",
            font_size='11sp',
            color=(0/255, 243/255, 255/255, 1),
            halign='center'
        )
        btn_close = CyberButton(text="确定", size_hint_y=None, height=dp(34))
        content.add_widget(msg)
        content.add_widget(btn_close)

        popup = Popup(title="📋 复制 IP 成功", content=content, size_hint=(0.82, 0.30))
        btn_close.bind(on_release=popup.dismiss)
        popup.open()

    def stop_scan(self):
        self.stop_requested = True
        self.is_scanning = False
        self.status_text = "已停止"
        self.append_log("[!] 用户终止了测速。")


class CyberScannerApp(App):
    def build(self):
        self.title = "Cloudflare CyberScanner"
        return MainUI()


if __name__ == '__main__':
    CyberScannerApp().run()
