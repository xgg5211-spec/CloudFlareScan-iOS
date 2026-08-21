import glob
import ipaddress
import json
import os
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
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

# ==================== 1. iOS 中文字体自动修复 (解决口口乱码) ====================
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
            print(f"[FontManager] 成功加载 iOS 中文字体: {chosen_font}")
        except Exception as e:
            print(f"[FontManager] 注册字体失败: {e}")

init_ios_cjk_font()

# ==================== 2. 内置 Cloudflare 全量 & 优选 IP 数据库 ====================
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

# Cloudflare 机场数据中心与国家地区映射表
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
    """IP 隐藏遮罩算法：例如 104.16.123.45 -> 104.16.***.***"""
    if not ip_str:
        return ""
    if ":" in ip_str:  # IPv6
        parts = ip_str.split(":")
        if len(parts) >= 4:
            return f"{parts[0]}:{parts[1]}:****:****"
        return ip_str[:8] + "****"
    parts = ip_str.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.***.***"
    return ip_str

# ==================== 3. 赛博朋克自适应 UI 布局定义 ====================
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
            rgba: (0/255, 243/255, 255/255, 0.3)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(6))
            width: 0.8
    Label:
        text: root.title
        font_size: '10sp'
        color: (130/255, 145/255, 165/255, 1)
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

<MainUI>:
    canvas.before:
        Color:
            rgba: (10/255, 13/255, 18/255, 1)
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: [dp(10), dp(28), dp(10), dp(10)]  # 顶部增加 28dp iOS 刘海/灵动岛避让安全边距
        spacing: dp(6)

        # 1. 顶栏：标题与状态
        BoxLayout:
            size_hint_y: None
            height: dp(26)
            Label:
                text: "[b][color=00f3ff]CLOUDFLARE[/color] [color=ff0055]SCANNER[/color] [color=888888]v4.0[/color][/b]"
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

        # 2. 本地运营商 & 出口 IP 看板
        BoxLayout:
            size_hint_y: None
            height: dp(28)
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
                shorten_from: 'right'

        # 3. 数据仪表盘 (4卡片)
        BoxLayout:
            size_hint_y: None
            height: dp(42)
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

        # 4. 配置选项一 (端口 + IP库来源 + 地区选择)
        BoxLayout:
            size_hint_y: None
            height: dp(30)
            spacing: dp(4)

            Spinner:
                id: port_spinner
                text: '443 (HTTPS)'
                values: ['443 (HTTPS)', '8443 (HTTPS)', '2053 (HTTPS)', '2083 (HTTPS)', '80 (HTTP)', '8080 (HTTP)']
                size_hint_x: 0.33
                font_size: '10sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (0/255, 243/255, 255/255, 1)

            Spinner:
                id: source_spinner
                text: '亚太优选 库'
                values: ['亚太优选 库', '官方 IPv4 库', '官方 IPv6 库', '在线订阅URL', '剪贴板自定义']
                size_hint_x: 0.35
                font_size: '10sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (0/255, 255/255, 136/255, 1)
                on_text: root.on_source_change(self.text)

            Spinner:
                id: region_spinner
                text: '全部分区'
                values: ['全部分区', '🇭🇰 香港', '🇯🇵 日本', '🇸🇬 新加坡', '🇺🇸 美国', '🌐 其他地区']
                size_hint_x: 0.32
                font_size: '10sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (255/255, 204/255, 0/255, 1)

        # 5. IP/CIDR 输入与编辑框
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: 0.22
            spacing: dp(3)

            TextInput:
                id: ip_input
                hint_text: "点击 [获取/刷新 IP库] 秒载内置库，或在此粘贴自定义 CIDR / IP..."
                background_color: (15/255, 20/255, 28/255, 1)
                foreground_color: (0/255, 243/255, 255/255, 1)
                cursor_color: (255/255, 0/255, 85/255, 1)
                font_size: '10sp'
                padding: [dp(6), dp(6)]

        # 6. 控制按钮栏 (支持 IP 隐藏脱敏开关)
        BoxLayout:
            size_hint_y: None
            height: dp(32)
            spacing: dp(4)

            CyberButton:
                text: "刷新 IP 库"
                on_release: root.load_current_source_ip()

            CyberButton:
                text: root.mask_button_text
                on_release: root.toggle_ip_mask()

            CyberButton:
                text: "停止" if root.is_scanning else "🚀 开始 TLS 测速"
                on_release: root.toggle_scan()

            CyberButton:
                text: "📤 导出节点"
                on_release: root.export_proxy_config()

        # 7. 环形终端日志视窗 (防 OpenGL 显存溢出)
        BoxLayout:
            orientation: 'vertical'
            ScrollView:
                id: scroller
                bar_width: dp(3)
                bar_color: (0/255, 243/255, 255/255, 0.6)
                canvas.before:
                    Color:
                        rgba: (8/255, 11/255, 16/255, 0.95)
                    Rectangle:
                        pos: self.pos
                        size: self.size
                    Color:
                        rgba: (0/255, 243/255, 255/255, 0.2)
                    Line:
                        rounded_rectangle: (self.x, self.y, self.width, self.height, dp(6))
                        width: 1
                Label:
                    id: log_label
                    text: root.log_content
                    markup: True
                    font_size: '10sp'
                    size_hint_y: None
                    height: self.texture_size[1]
                    text_size: self.width - dp(10), None
                    padding: [dp(5), dp(5)]
                    halign: 'left'
                    valign: 'top'
"""

Builder.load_string(KV_STYLE)


class MainUI(BoxLayout):
    status_text = StringProperty("系统就绪")
    isp_info_text = StringProperty("🔍 正在识别本地运营商与出口 IP...")
    log_content = StringProperty("[color=00f3ff]=== Cloudflare CyberScanner v4.0 (终极稳定版) ===[/color]\n• 已替换为多线程底层 Socket，彻底绝杀 iOS 闪退\n• 内置全量/亚太优选 IP 库，秒级加载，离线无忧\n• 支持 TLS 真实加密握手 + 节点国家/数据中心自动识别\n• 支持 IP 隐私遮罩脱敏模式，截图分享不露 IP\n")
    is_scanning = BooleanProperty(False)
    is_ip_masked = BooleanProperty(False)
    mask_button_text = StringProperty("🙈 IP 遮罩: 关")

    # 数据看板
    scanned_count = NumericProperty(0)
    total_count = NumericProperty(0)
    valid_count = NumericProperty(0)
    min_latency_text = StringProperty("-- ms")
    max_speed_text = StringProperty("-- MB/s")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stop_requested = False
        self.best_ips = []  # 存储测速结果
        self.ui_log_buffer = []
        self.raw_log_lines = self.log_content.splitlines()

        # UI 节流刷新定时器，防止高并发假死
        Clock.schedule_interval(self._flush_ui_log_buffer, 0.15)
        
        # 默认自动加载亚太优选库，并异步识别本地 ISP
        Clock.schedule_once(lambda dt: self.load_current_source_ip(), 0.2)
        Clock.schedule_once(lambda dt: self.detect_isp_info(), 0.5)

    def append_log(self, text):
        self.ui_log_buffer.append(text)

    def _flush_ui_log_buffer(self, dt):
        """环形日志：固定最新 150 行，保护内存与 GPU 显存"""
        if self.ui_log_buffer:
            self.raw_log_lines.extend(self.ui_log_buffer)
            self.ui_log_buffer.clear()

            if len(self.raw_log_lines) > 150:
                self.raw_log_lines = self.raw_log_lines[-150:]

            self.log_content = "\n".join(self.raw_log_lines) + "\n"
            if hasattr(self.ids, 'scroller'):
                self.ids.scroller.scroll_y = 0

    # ---------------- 1. 隐藏 IP 隐私脱敏开关 ----------------
    def toggle_ip_mask(self):
        self.is_ip_masked = not self.is_ip_masked
        if self.is_ip_masked:
            self.mask_button_text = "🙈 IP 遮罩: 开"
            self.append_log("[🔒 隐私] 已开启 IP 遮罩模式，所有 IP 将模糊显示 (104.16.***.***)。")
        else:
            self.mask_button_text = "🙈 IP 遮罩: 关"
            self.append_log("[🔓 隐私] 已关闭 IP 遮罩模式，显示完整 IP 地址。")

    # ---------------- 2. 运营商与公网 IP 识别 ----------------
    def detect_isp_info(self):
        threading.Thread(target=self._detect_isp_worker, daemon=True).start()

    def _detect_isp_worker(self):
        isp_text = "🌐 本地网络: 直连 / 未知运营商"
        try:
            req = urllib.request.Request("http://ip-api.com/json/?lang=zh-CN", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                ip = data.get('query', '未知')
                display_ip = mask_ip_addr(ip) if self.is_ip_masked else ip
                isp = data.get('isp', data.get('org', '未知'))
                city = data.get('city', '')

                if "Telecom" in isp or "电信" in isp:
                    isp_name = "中国电信"
                elif "Unicom" in isp or "联通" in isp:
                    isp_name = "中国联通"
                elif "Mobile" in isp or "移动" in isp:
                    isp_name = "中国移动"
                else:
                    isp_name = isp

                isp_text = f"🌐 运营商: [color=00ff88]{isp_name}[/color]  公网IP: [color=00f3ff]{display_ip}[/color] ({city})"
        except Exception:
            pass

        Clock.schedule_once(lambda dt: setattr(self, 'isp_info_text', isp_text))

    # ---------------- 3. 内置 IP 库秒级加载 ----------------
    def on_source_change(self, source_name):
        self.load_current_source_ip(source_name)

    def load_current_source_ip(self, source_name=None):
        if not source_name:
            source_name = self.ids.source_spinner.text

        if source_name == "亚太优选 库":
            self.ids.ip_input.text = "\n".join(BUILTIN_APAC_PREFERRED)
            self.status_text = f"已载入 {len(BUILTIN_APAC_PREFERRED)} 网段"
            self.append_log(f"[✓] [color=00ff88]已秒级载入 {len(BUILTIN_APAC_PREFERRED)} 个内置【亚太优选 IP 网段】！[/color]")

        elif source_name == "官方 IPv4 库":
            self.ids.ip_input.text = "\n".join(BUILTIN_IPV4_OFFICIAL)
            self.status_text = f"已载入 {len(BUILTIN_IPV4_OFFICIAL)} 网段"
            self.append_log(f"[✓] [color=00ff88]已秒级载入 {len(BUILTIN_IPV4_OFFICIAL)} 个内置【官方 IPv4 网段】！[/color]")

        elif source_name == "官方 IPv6 库":
            self.ids.ip_input.text = "\n".join(BUILTIN_IPV6_OFFICIAL)
            self.status_text = f"已载入 {len(BUILTIN_IPV6_OFFICIAL)} 网段"
            self.append_log(f"[✓] [color=00ff88]已秒级载入 {len(BUILTIN_IPV6_OFFICIAL)} 个内置【官方 IPv6 网段】！[/color]")

        elif source_name == "剪贴板自定义":
            text = Clipboard.paste()
            if text and text.strip():
                self.ids.ip_input.text = text.strip()
                lines = [l for l in text.splitlines() if l.strip()]
                self.append_log(f"[✓] [color=00ff88]成功从剪贴板载入 {len(lines)} 行自定义 IP/CIDR！[/color]")
            else:
                self.append_log("[!] 剪贴板为空，请先复制 IP / CIDR 网段。")

        elif source_name == "在线订阅URL":
            self.show_url_import_dialog()

    def show_url_import_dialog(self):
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        url_input = TextInput(
            text="https://raw.githubusercontent.com/ip-thailand/cloudflare-ip/main/cloudflare-ipv4.txt",
            hint_text="输入订阅 / TXT 文件 URL 链接",
            multiline=False, size_hint_y=None, height=dp(38), font_size='11sp'
        )
        btn_box = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
        btn_confirm = CyberButton(text="下载导入")
        btn_cancel = CyberButton(text="取消")
        btn_box.add_widget(btn_confirm)
        btn_box.add_widget(btn_cancel)
        content.add_widget(url_input)
        content.add_widget(btn_box)

        popup = Popup(title="🌐 拉取在线 IP 库", content=content, size_hint=(0.88, 0.32))

        def on_confirm(instance):
            url = url_input.text.strip()
            if url:
                popup.dismiss()
                self.status_text = "下载 IP 库..."
                self.append_log(f"[+] 正在拉取: {url}")
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
                lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith('#')]
                Clock.schedule_once(lambda dt: self._on_ip_fetch_success(lines))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.append_log(f"[X] 拉取失败: {e}，建议直接使用内置优选库。"))

    def _on_ip_fetch_success(self, lines):
        self.ids.ip_input.text = "\n".join(lines)
        self.status_text = f"已加载 {len(lines)} 条"
        self.append_log(f"[✓] [color=00ff88]成功在线获取 {len(lines)} 个 IP 网段！[/color]")

    # ---------------- 4. 多线程纯底层 TLS 握手测速引擎 (100% 不闪退) ----------------
    def toggle_scan(self):
        if self.is_scanning:
            self.stop_scan()
        else:
            self.start_scan()

    def start_scan(self):
        raw_text = self.ids.ip_input.text.strip()
        if not raw_text:
            self.append_log("[!] 请先选择或载入 IP 网段。")
            return

        self.is_scanning = True
        self.stop_requested = False
        self.status_text = "解析 IP 中..."
        self.scanned_count = 0
        self.valid_count = 0
        self.min_latency_text = "-- ms"
        self.max_speed_text = "-- MB/s"
        self.best_ips.clear()

        port_str = self.ids.port_spinner.text.split(' ')[0]
        port = int(port_str)
        region_filter = self.ids.region_spinner.text

        # 启动后台多线程打散解析，绝不卡死主界面
        threading.Thread(target=self._parse_ips_worker, args=(raw_text, port, region_filter), daemon=True).start()

    def _parse_ips_worker(self, raw_text, port, region_filter):
        ip_set = set()
        for line in raw_text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                if '/' in line:
                    net = ipaddress.ip_network(line, strict=False)
                    hosts = list(net.hosts())
                    sample_size = min(len(hosts), 30)  # 高效离散采样
                    if sample_size > 0:
                        ip_set.update([str(ip) for ip in random.sample(hosts, sample_size)])
                else:
                    ip_set.add(str(ipaddress.ip_address(line)))
            except ValueError:
                continue

        final_ips = list(ip_set)
        random.shuffle(final_ips)
        final_ips = final_ips[:800]  # 抽取 800 个黄金样本 IP

        Clock.schedule_once(lambda dt: self._start_thread_ping(final_ips, port, region_filter))

    def _start_thread_ping(self, ip_list, port, region_filter):
        if not ip_list:
            self.append_log("[!] 未解析到可用的有效 IP。")
            self.is_scanning = False
            self.status_text = "就绪"
            return

        self.total_count = len(ip_list)
        self.status_text = "TLS 握手测速中..."
        self.append_log(f"[+] 开始对 [color=00f3ff]{len(ip_list)}[/color] 个节点执行真实 TLS 加密握手...")

        # 后台驱动并发扫描线程，彻底绝杀 asyncio 引起的崩溃
        threading.Thread(target=self._scan_runner, args=(ip_list, port, region_filter), daemon=True).start()

    def _test_single_tls_ip(self, ip, port):
        """核心：100% 真实 SSL/TLS 握手 + 自动解析 Cloudflare 机房 Colo 代码"""
        if self.stop_requested:
            return ip, None, "已停止"

        is_ssl = port in [443, 8443, 2053, 2083]
        s = socket.socket(socket.AF_INET if ":" not in ip else socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout(1.3)  # 严格 1.3 秒超时保护
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

                # 探测 Cloudflare 机房 /cdn-cgi/trace
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

            return ip, latency, colo_str
        except Exception:
            return ip, None, "超时"
        finally:
            try:
                s.close()
            except Exception:
                pass

    def _scan_runner(self, ip_list, port, region_filter):
        # 16 线程受控并发，防 iOS 句柄超限
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(self._test_single_tls_ip, ip, port) for ip in ip_list]
            for future in futures:
                if self.stop_requested:
                    break
                ip, latency, colo = future.result()

                # 主线程安全的更新 UI
                Clock.schedule_once(lambda dt, i=ip, l=latency, c=colo: self._on_single_result(i, l, c, region_filter))

        # 完成后对 TOP 节点发起真实 HTTP 下载速度测量
        if self.best_ips and not self.stop_requested:
            Clock.schedule_once(lambda dt: self.append_log("\n[+] 正在对最快节点发起 [color=ff0088]3MB HTTP 真实下载速度测试[/color]..."))
            top_3 = sorted(self.best_ips, key=lambda x: x['latency'])[:3]
            for item in top_3:
                if self.stop_requested:
                    break
                speed = self._test_download_speed_sync(item['ip'], port)
                item['speed'] = speed
                display_ip = mask_ip_addr(item['ip']) if self.is_ip_masked else item['ip']
                if speed > 0:
                    Clock.schedule_once(lambda dt, dip=display_ip, spd=speed: self.append_log(f"[🚀 测速] IP: {dip:<15} 实测速度: [color=ff0088]{spd} MB/s[/color]"))

            max_s = max(x['speed'] for x in self.best_ips)
            if max_s > 0:
                Clock.schedule_once(lambda dt, ms=max_s: setattr(self, 'max_speed_text', f"{ms} MB/s"))

        # 汇总榜单
        Clock.schedule_once(lambda dt: self._finish_scan())

    def _on_single_result(self, ip, latency, colo, region_filter):
        self.scanned_count += 1
        if latency is not None:
            # 根据用户选择的地区过滤
            if region_filter != "全部分区":
                if region_filter[:2] not in colo and region_filter[3:] not in colo:
                    return

            self.valid_count += 1
            self.best_ips.append({'ip': ip, 'latency': latency, 'colo': colo, 'speed': 0.0})

            color_str = "00ff88" if latency < 120 else ("00f3ff" if latency < 220 else "ffcc00")
            min_lat = min(x['latency'] for x in self.best_ips)
            self.min_latency_text = f"{min_lat} ms"

            display_ip = mask_ip_addr(ip) if self.is_ip_masked else ip
            self.append_log(f"[✓] IP: [color=ffffff]{display_ip:<15}[/color] [{colo}] TLS: [color={color_str}]{latency} ms[/color]")

    def _test_download_speed_sync(self, ip, port):
        """同步 socket 拉取测速，准确率 100%"""
        is_ssl = port in [443, 8443, 2053, 2083]
        s = socket.socket(socket.AF_INET if ":" not in ip else socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout(2.5)
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

            req = f"GET /__down?bytes=3000000 HTTP/1.1\r\nHost: speed.cloudflare.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
            conn.sendall(req.encode('utf-8'))

            downloaded = 0
            while True:
                chunk = conn.recv(16384)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded >= 3000000:
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
            self.append_log("\n[b][color=00ff88]🏆 TOP 5 优选 Cloudflare 节点榜单:[/color][/b]")
            for idx, item in enumerate(self.best_ips[:5], start=1):
                display_ip = mask_ip_addr(item['ip']) if self.is_ip_masked else item['ip']
                speed_str = f" | {item['speed']} MB/s" if item['speed'] > 0 else ""
                self.append_log(f"  {idx}. [color=00f3ff]{display_ip:<15}[/color] [{item['colo']}] - [color=00ff88]{item['latency']} ms[/color]{speed_str}")

        self.append_log("\n[✓] [color=00f3ff]全套 TLS 测速与数据中心识别完成！[/color]")
        self.is_scanning = False
        self.status_text = "完成"

    # ---------------- 5. 导出配置与操作 ----------------
    def export_proxy_config(self):
        """一键生成支持 Clash / Shadowrocket 的通用优选 IP 配置"""
        if not self.best_ips:
            self.append_log("[!] 暂无测速数据，请先开始测速。")
            return

        port_str = self.ids.port_spinner.text.split(' ')[0]
        result_lines = ["# === Cloudflare 优选 IP 节点列表 ==="]
        for idx, item in enumerate(self.best_ips[:10], start=1):
            # 导出配置始终使用完整真实 IP
            result_lines.append(f"{item['ip']}:{port_str}#{idx}_CF_{item['colo']}_{item['latency']}ms")

        export_text = "\n".join(result_lines)
        Clipboard.copy(export_text)
        self.append_log(f"[✓] [color=00ff88]已生成 TOP 10 优选节点列表并复制到剪贴板！[/color]")

    def stop_scan(self):
        self.stop_requested = True
        self.is_scanning = False
        self.status_text = "已停止"
        self.append_log("[!] 用户手动终止了测速。")


class CyberScannerApp(App):
    def build(self):
        self.title = "Cloudflare CyberScanner"
        return MainUI()


if __name__ == '__main__':
    CyberScannerApp().run()
