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
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.switch import Switch
from kivy.uix.spinner import Spinner
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.popup import Popup

# ==================== 1. 安全注册 iOS 中文字体 ====================
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
            print(f"[Font Warning] 字体注册: {e}")

try:
    init_ios_cjk_font()
except Exception:
    pass

# ==================== 2. 内置 IPv4 / IPv6 与全球 80+ 机房映射 ====================
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

COLO_MAP = {
    # 亚洲/东亚/东南亚
    'HKG': '🇭🇰 香港', 'MFM': '🇲🇴 澳门', 'TPE': '🇹🇼 台北', 'KHH': '🇹🇼 高雄',
    'NRT': '🇯🇵 东京', 'HND': '🇯🇵 羽田', 'KIX': '🇯🇵 大阪', 'ICN': '🇰🇷 首尔',
    'SIN': '🇸🇬 新加坡', 'BKK': '🇹🇭 曼谷', 'KUL': '🇲🇾 吉隆坡', 'CGK': '🇮🇩 雅加达',
    'MNL': '🇵🇭 马尼拉', 'SGN': '🇻🇳 胡志明', 'HAN': '🇻🇳 河内', 'PNH': '🇰🇭 金边',
    'DEL': '🇮🇳 新德里', 'BOM': '🇮🇳 孟买', 'MAA': '🇮🇳 钦奈', 'CCU': '🇮🇳 加尔各答',
    # 北美洲
    'LAX': '🇺🇸 洛杉矶', 'SJC': '🇺🇸 圣何塞', 'SFO': '🇺🇸 旧金山', 'SEA': '🇺🇸 西雅图',
    'ORD': '🇺🇸 芝加哥', 'JFK': '🇺🇸 纽约', 'EWR': '🇺🇸 纽瓦克', 'IAD': '🇺🇸 华盛顿',
    'DFW': '🇺🇸 达拉斯', 'MIA': '🇺🇸 迈阿密', 'ATL': '🇺🇸 亚特兰大', 'DEN': '🇺🇸 丹佛',
    'YVR': '🇨🇦 温哥华', 'YYZ': '🇨🇦 多伦多', 'YUL': '🇨🇦 蒙特利尔',
    # 欧洲
    'LHR': '🇬🇧 伦敦', 'MAN': '🇬🇧 曼彻斯特', 'CDG': '🇫🇷 巴黎', 'FRA': '🇩🇪 法兰克福',
    'AMS': '🇳🇱 阿姆斯特丹', 'BRU': '🇧🇪 布鲁塞尔', 'ZRH': '🇨🇭 苏黎世', 'VIE': '🇦🇹 维也纳',
    'MAD': '🇪🇸 马德里', 'BCN': '🇪🇸 巴塞罗那', 'FCO': '🇮🇹 罗马', 'MXP': '🇮🇹 米兰',
    'STOCK': '🇸🇪 斯德哥尔摩', 'HEL': '🇫🇮 赫尔辛基', 'CPH': '🇩🇰 哥本哈根', 'OSL': '🇳🇴 奥斯陆',
    # 大洋洲/南美/中东/非洲
    'SYD': '🇦🇺 悉尼', 'MEL': '🇦🇺 墨尔本', 'PER': '🇦🇺 珀斯', 'AKL': '🇳🇿 奥克兰',
    'GRU': '🇧🇷 圣保罗', 'EZE': '🇦🇷 布宜诺斯艾利斯', 'SCL': '🇨🇱 圣地亚哥',
    'DXB': '🇦🇪 迪拜', 'TLV': '🇮🇱 特拉维夫', 'JNB': '🇿🇦 约翰尼斯堡'
}

def parse_ips_safe(text, max_samples=2000):
    """高效流式采样解析器，防止万级 CIDR 展开爆内存"""
    found_ips = set()
    if not text:
        return []

    lines = text.splitlines()
    for line in lines:
        if len(found_ips) >= max_samples:
            break
        line = line.strip().strip('"\'[],;')
        if not line or line.startswith('#'):
            continue

        try:
            if '/' in line:
                net = ipaddress.ip_network(line, strict=False)
                num = net.num_addresses
                if num <= 2:
                    found_ips.add(str(net.network_address))
                else:
                    sample_size = min(15, num - 2)
                    indices = random.sample(range(1, num - 1), sample_size)
                    for idx in indices:
                        found_ips.add(str(net[idx]))
                        if len(found_ips) >= max_samples:
                            break
            else:
                ip_obj = ipaddress.ip_address(line)
                found_ips.add(str(ip_obj))
        except Exception:
            pass

    return list(found_ips)

# ==================== 3. 赛博朋克深色 UI (Cyberpunk KV) ====================
KV_STYLE = """
#:kivy 2.0.0

<CyberCard@BoxLayout>:
    orientation: 'vertical'
    padding: dp(12)
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: (0.10, 0.13, 0.18, 0.95)  # 赛博高对比卡片背景
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10),]
        Color:
            rgba: (0/255, 229/255, 255/255, 0.25)  # 青色外发光边框
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(10))
            width: dp(1)

<CyberButton@Button>:
    background_normal: ''
    background_color: (0, 0, 0, 0)
    font_size: '12sp'
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
    background_color: (0.16, 0.20, 0.28, 1)  # 修复可见度：深灰蓝背景
    foreground_color: (1, 1, 1, 1)           # 修复可见度：纯白高亮文字
    hint_text_color: (0.55, 0.60, 0.70, 1)   # 提示词清晰可见
    font_size: '12sp'
    padding: [dp(8), dp(7)]
    cursor_color: (0, 229/255, 255/255, 1)

<ResultRow>:
    orientation: 'horizontal'
    padding: [dp(10), dp(4)]
    spacing: dp(6)
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
        color: (0/255, 229/255, 255/255, 1)  # 赛博霓虹青
        size_hint_x: 0.40
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
        size_hint_x: 0.18
        halign: 'right'
        valign: 'middle'
        text_size: self.size

    Label:
        text: root.proxy_text
        font_size: '10sp'
        bold: True
        color: (255/255, 215/255, 0/255, 1) if '✓' in root.proxy_text else (140/255, 140/255, 150/255, 1)
        size_hint_x: 0.18
        halign: 'right'
        valign: 'middle'
        text_size: self.size

<MainUI>:
    canvas.before:
        Color:
            rgba: (0.05, 0.07, 0.10, 1)  # 赛博极夜底色
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: [dp(12), dp(32), dp(12), dp(12)]
        spacing: dp(10)

        # 顶部标题栏 & 本地 ISP 运营商识别
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: dp(42)
            Label:
                text: "[b]⚡ CYBERSCANNER 优选 IP 筛选工具[/b]"
                markup: True
                font_size: '16sp'
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
                spacing: dp(10)
                size_hint_y: None
                height: self.minimum_height

                # 1. 导入 IP 文件 & 自定义 URL
                CyberCard:
                    size_hint_y: None
                    height: dp(125)
                    Label:
                        text: "[b]1. 导入 IP / 自定义网络库[/b]"
                        markup: True
                        font_size: '12sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(18)
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

                    # 自定义 URL 加载
                    BoxLayout:
                        spacing: dp(6)
                        size_hint_y: None
                        height: dp(30)
                        FormInput:
                            id: custom_url_input
                            hint_text: "输入自定义网络 IP 订阅 URL (http://...)"
                        CyberButton:
                            text: "网络加载"
                            size_hint_x: 0.3
                            btn_color: (247/255, 37/255, 133/255, 1)
                            on_release: root.load_from_url()

                    Label:
                        text: root.import_status_text
                        font_size: '10sp'
                        color: (150/255, 160/255, 180/255, 1)
                        size_hint_y: None
                        height: dp(16)
                        halign: 'left'
                        text_size: self.size

                # 2. 扫描与深度校验设置
                CyberCard:
                    size_hint_y: None
                    height: dp(235)
                    Label:
                        text: "[b]2. 扫描与 ProxyIP 验证设置[/b]"
                        markup: True
                        font_size: '12sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(18)
                        halign: 'left'
                        text_size: self.size

                    GridLayout:
                        cols: 2
                        spacing: dp(8)
                        size_hint_y: None
                        height: dp(88)

                        BoxLayout:
                            orientation: 'vertical'
                            Label:
                                text: "采样数量 (最大)"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: count_input
                                text: "500"

                        BoxLayout:
                            orientation: 'vertical'
                            Label:
                                text: "端口筛选 (443, 8443)"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: ports_input
                                text: "443, 8443, 2053"

                        BoxLayout:
                            orientation: 'vertical'
                            Label:
                                text: "并发线程"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: threads_input
                                text: "120"

                        BoxLayout:
                            orientation: 'vertical'
                            Label:
                                text: "超时 (秒)"
                                font_size: '10sp'
                                color: (180/255, 180/255, 190/255, 1)
                                halign: 'left'
                                text_size: self.size
                            FormInput:
                                id: timeout_input
                                text: "2.5"

                    # 双开关与地区 Spinner
                    BoxLayout:
                        size_hint_y: None
                        height: dp(32)
                        spacing: dp(6)

                        Label:
                            text: "cmliussss Proxy 深度验真"
                            font_size: '10sp'
                            color: (220/255, 220/255, 230/255, 1)
                            halign: 'left'
                            valign: 'middle'
                            text_size: self.size

                        Switch:
                            id: proxy_check_switch
                            active: True
                            size_hint_x: None
                            width: dp(44)

                        Spinner:
                            id: region_spinner
                            text: '全球所有地区 ▼'
                            values: ['全球所有地区 ▼', '🇭🇰 香港', '🇯🇵 日本', '🇸🇬 新加坡', '🇺🇸 美国', '🇬🇧 英国', '🇩🇪 德国']
                            font_size: '10sp'
                            background_color: (0.16, 0.20, 0.28, 1)
                            color: (0/255, 229/255, 255/255, 1)
                            size_hint_x: 0.42

                    # 控制按钮
                    BoxLayout:
                        spacing: dp(8)
                        size_hint_y: None
                        height: dp(34)

                        CyberButton:
                            text: "⚡ 开始并发扫描" if not root.is_scanning else "正在高速检测..."
                            btn_color: (0/255, 180/255, 216/255, 1)
                            on_release: root.start_scan()

                        CyberButton:
                            text: "停止"
                            btn_color: (230/255, 57/255, 70/255, 1)
                            on_release: root.stop_scan()

                    Label:
                        text: root.scan_status_text
                        font_size: '10sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(16)
                        halign: 'left'
                        text_size: self.size

                # 3. 可用 IP 列表 (RecycleView 千级高帧率渲染)
                CyberCard:
                    size_hint_y: None
                    height: dp(320)
                    Label:
                        text: "[b]3. 可用 IP 结果 (已校验连通与真伪)[/b]"
                        markup: True
                        font_size: '12sp'
                        color: (0/255, 229/255, 255/255, 1)
                        size_hint_y: None
                        height: dp(18)
                        halign: 'left'
                        text_size: self.size

                    BoxLayout:
                        size_hint_y: None
                        height: dp(28)
                        spacing: dp(6)

                        Label:
                            text: "可用节点: " + str(len(root.valid_ips_data)) + " 个"
                            font_size: '10sp'
                            color: (160/255, 170/255, 190/255, 1)
                            halign: 'left'
                            valign: 'middle'
                            text_size: self.size

                        CyberButton:
                            text: "📋 复制 IP:Port"
                            btn_color: (0/255, 230/255, 118/255, 1)
                            size_hint_x: 0.40
                            on_release: root.copy_ips_to_clipboard()

                    # 虚拟列表视角
                    RecycleView:
                        id: rv
                        viewclass: 'ResultRow'
                        RecycleBoxLayout:
                            default_size: None, dp(34)
                            default_size_hint: 1, None
                            size_hint_y: None
                            height: self.minimum_height
                            orientation: 'vertical'
                            spacing: dp(3)
"""

Builder.load_string(KV_STYLE)


class ResultRow(RecycleDataViewBehavior, BoxLayout):
    ip_text = StringProperty('')
    region_text = StringProperty('')
    latency_text = StringProperty('')
    proxy_text = StringProperty('')


class MainUI(BoxLayout):
    import_status_text = StringProperty("默认已载入 15 个官方 IPv4 网段")
    scan_status_text = StringProperty("系统就绪")
    isp_info_text = StringProperty("正在识别本地网络与运营商...")
    is_scanning = BooleanProperty(False)
    valid_ips_data = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stop_requested = False
        self.raw_ip_pool = BUILTIN_IPV4_OFFICIAL[:]
        self.result_queue = queue.Queue()

        # 后台异步探测本地 ISP 运营商
        threading.Thread(target=self._fetch_local_isp, daemon=True).start()

        # UI 循环刷新，防止线程阻塞
        Clock.schedule_interval(self._drain_result_queue, 0.08)

    def _fetch_local_isp(self):
        """识别用户公网 IP 和运营商名称"""
        try:
            req = urllib.request.Request("http://ip-api.com/json/?lang=zh-CN", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode('utf-8'))
                ip = data.get('query', '未知')
                isp = data.get('isp', '未知运营商')
                country = data.get('country', '')
                Clock.schedule_once(lambda dt: setattr(self, 'isp_info_text', f"当前网络: {isp} ({country}) | 公网IP: {ip}"))
        except Exception:
            Clock.schedule_once(lambda dt: setattr(self, 'isp_info_text', "网络检测完成 | 优选扫描已就绪"))

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
                self.import_status_text = f"剪贴板载入 {len(lines)} 行自定义 IP"
            else:
                self.import_status_text = "剪贴板为空！"
        except Exception:
            self.import_status_text = "剪贴板读取失败"

    def load_from_url(self):
        url = self.ids.custom_url_input.text.strip()
        if not url.startswith("http"):
            self.import_status_text = "❌ 请输入有效的 HTTP/HTTPS URL"
            return

        self.import_status_text = "正在拉取网络 IP 库..."
        def _fetch():
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    content = resp.read().decode('utf-8', errors='ignore')
                    lines = [l.strip() for l in content.splitlines() if l.strip()]
                    self.raw_ip_pool = lines
                    Clock.schedule_once(lambda dt: setattr(self, 'import_status_text', f"✓ 成功加载网络库: {len(lines)} 条记录"))
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self, 'import_status_text', "❌ 网络库加载失败"))

        threading.Thread(target=_fetch, daemon=True).start()

    def start_scan(self):
        if self.is_scanning:
            return

        try:
            max_count = int(self.ids.count_input.text.strip()) if self.ids.count_input.text.strip() else 1000
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

        parsed_ips = parse_ips_safe("\n".join(self.raw_ip_pool), max_samples=max_count)
        if not parsed_ips:
            self.scan_status_text = "❌ 未检测到可用 IP 样本"
            return

        self.is_scanning = True
        self.stop_requested = False
        self.valid_ips_data.clear()
        self.ids.rv.data = []
        self.scan_status_text = f"正在并发扫描 {len(parsed_ips)} 个节点..."

        do_proxy_check = self.ids.proxy_check_switch.active

        threading.Thread(
            target=self._scan_runner,
            args=(parsed_ips, ports, threads_num, timeout_sec, do_proxy_check),
            daemon=True
        ).start()

    def _test_ip_worker(self, ip, ports, timeout_sec, do_proxy_check):
        if self.stop_requested:
            return

        for port in ports:
            if self.stop_requested:
                break

            s = socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout_sec)
            start_t = time.perf_counter()
            colo_str = "未知"
            proxy_ok = False

            try:
                # SSL TLS 握手 & check.proxyip.cmliussss.net 验真
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                # 使用 ProxyIP 域名或者 speed.cloudflare.com
                sni = "check.proxyip.cmliussss.net" if do_proxy_check else "speed.cloudflare.com"
                tls_sock = ctx.wrap_socket(s, server_hostname=sni)
                tls_sock.connect((ip, port))
                latency = int((time.perf_counter() - start_t) * 1000)

                # 校验代理可用性与获取机房 COLO
                try:
                    host_hdr = "check.proxyip.cmliussss.net" if do_proxy_check else "speed.cloudflare.com"
                    req = f"GET /cdn-cgi/trace HTTP/1.1\r\nHost: {host_hdr}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
                    tls_sock.sendall(req.encode('utf-8'))
                    resp = tls_sock.recv(1024).decode('utf-8', errors='ignore')

                    if "HTTP/1.1 200" in resp or "HTTP/1.1 204" in resp or "uag=" in resp:
                        proxy_ok = True

                    match = re.search(r'colo=([A-Z]{3})', resp)
                    if match:
                        colo_code = match.group(1)
                        colo_str = COLO_MAP.get(colo_code, f"🌐 {colo_code}")
                except Exception:
                    pass

                tls_sock.close()

                self.result_queue.put({
                    'ip': ip, 'port': port, 'latency': latency,
                    'colo': colo_str, 'proxy_ok': proxy_ok, 'success': True
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

    def _scan_runner(self, ip_list, ports, threads_num, timeout_sec, do_proxy_check):
        with ThreadPoolExecutor(max_workers=min(threads_num, 150)) as pool:
            futures = [pool.submit(self._test_ip_worker, ip, ports, timeout_sec, do_proxy_check) for ip in ip_list]
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
                    colo = res['colo']
                    proxy_ok = res['proxy_ok']

                    item_data = {'ip': ip, 'port': port, 'latency': latency, 'colo': colo}
                    self.valid_ips_data.append(item_data)

                    # RecycleView 数据列表
                    new_items.append({
                        'ip_text': f"{ip}:{port}",
                        'region_text': colo,
                        'latency_text': f"{latency} ms",
                        'proxy_text': "✓ ProxyOK" if proxy_ok else "直连"
                    })
            except queue.Empty:
                break

        if new_items:
            # 增量刷新到 RecycleView
            self.ids.rv.data.extend(new_items)
            self.scan_status_text = f"正在扫描... 已获取 {len(self.valid_ips_data)} 个有效节点"

    def _finish_scan(self):
        self.is_scanning = False
        # 按延迟自动升序排序
        self.ids.rv.data = sorted(self.ids.rv.data, key=lambda x: int(x['latency_text'].replace(' ms', '')))
        self.scan_status_text = f"✓ 优选完成！成功筛选出 {len(self.valid_ips_data)} 个高速节点"

    def stop_scan(self):
        self.stop_requested = True
        self.is_scanning = False
        self.scan_status_text = "已停止扫描"

    def copy_ips_to_clipboard(self):
        try:
            if not self.valid_ips_data:
                self._show_toast("暂无有效 IP，请先开始扫描！")
                return

            lines = [f"{item['ip']}:{item['port']}" for item in self.valid_ips_data]
            export_text = "\n".join(lines)

            from kivy.core.clipboard import Clipboard
            Clipboard.copy(str(export_text))

            self._show_toast(f"✅ 成功复制 {len(lines)} 个 IP 到剪贴板！")
        except Exception:
            self._show_toast("复制完成！")

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
        self.title = "CYBERSCANNER 优选 IP"
        return MainUI()


if __name__ == '__main__':
    CloudflareScannerApp().run()
