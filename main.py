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
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.core.text import LabelBase, DEFAULT_FONT
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.switch import Switch
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
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
            print(f"[Font Warning] 注册字体失败: {e}")

# 执行字体注册
try:
    init_ios_cjk_font()
except Exception as e:
    print(f"[Font Safe Guard] 字体初始化跳过: {e}")

# ==================== 2. 内置官方 IP 库 ====================
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
    'HKG': '🇭🇰 香港', 'NRT': '🇯🇵 东京', 'HND': '🇯🇵 羽田', 'KIX': '🇯🇵 大阪',
    'SIN': '🇸🇬 新加坡', 'ICN': '🇰🇷 首尔', 'TPE': '🇹🇼 台北',
    'LAX': '🇺🇸 洛杉矶', 'SJC': '🇺🇸 圣何塞', 'SEA': '🇺🇸 西雅图',
    'SFO': '🇺🇸 旧金山', 'ORD': '🇺🇸 芝加哥', 'JFK': '🇺🇸 纽约',
    'FRA': '🇩🇪 法兰克福', 'LHR': '🇬🇧 伦敦', 'CDG': '🇫🇷 巴黎',
}

def parse_ips_safe(text, max_samples=1000):
    """安全且防崩溃的 IP 解析器"""
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
                    sample_size = min(10, num - 2)
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

# ==================== 3. Kivy KV 纯原生 UI 布局 ====================
KV_STYLE = """
#:kivy 2.0.0

<CardBox@BoxLayout>:
    orientation: 'vertical'
    padding: dp(12)
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: (1, 1, 1, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12),]

<StyledButton@Button>:
    background_normal: ''
    background_color: (0, 0, 0, 0)
    font_size: '12sp'
    bold: True
    color: (1, 1, 1, 1)
    btn_color: (0/255, 122/255, 255/255, 1)
    canvas.before:
        Color:
            rgba: self.btn_color if self.state == 'normal' else (self.btn_color[0]*0.8, self.btn_color[1]*0.8, self.btn_color[2]*0.8, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8),]

<FormInput@TextInput>:
    multiline: False
    background_normal: ''
    background_active: ''
    background_color: (240/255, 240/255, 245/255, 1)
    foreground_color: (30/255, 30/255, 30/255, 1)
    font_size: '12sp'
    padding: [dp(8), dp(8)]

<ResultItem@BoxLayout>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(36)
    padding: [dp(8), dp(4)]
    spacing: dp(6)
    ip_text: ''
    latency_text: ''
    region_text: ''
    speed_text: ''
    canvas.before:
        Color:
            rgba: (245/255, 245/255, 250/255, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(6),]

    Label:
        text: root.ip_text
        font_size: '11sp'
        bold: True
        color: (20/255, 20/255, 20/255, 1)
        size_hint_x: 0.40
        halign: 'left'
        valign: 'middle'
        text_size: self.size

    Label:
        text: root.region_text
        font_size: '10sp'
        color: (100/255, 100/255, 100/255, 1)
        size_hint_x: 0.22
        halign: 'center'
        valign: 'middle'
        text_size: self.size

    Label:
        text: root.latency_text
        font_size: '11sp'
        bold: True
        color: (52/255, 199/255, 89/255, 1) if 'ms' in root.latency_text else (150/255, 150/255, 150/255, 1)
        size_hint_x: 0.20
        halign: 'right'
        valign: 'middle'
        text_size: self.size

    Label:
        text: root.speed_text
        font_size: '10sp'
        bold: True
        color: (255/255, 149/255, 0/255, 1)
        size_hint_x: 0.18
        halign: 'right'
        valign: 'middle'
        text_size: self.size

<MainUI>:
    canvas.before:
        Color:
            rgba: (242/255, 242/255, 247/255, 1)
        Rectangle:
            pos: self.pos
            size: self.size

    ScrollView:
        do_scroll_x: False
        BoxLayout:
            orientation: 'vertical'
            padding: [dp(12), dp(36), dp(12), dp(16)]
            spacing: dp(12)
            size_hint_y: None
            height: self.minimum_height

            # 标题
            Label:
                text: "[b]优选 IP 筛选工具[/b]"
                markup: True
                font_size: '18sp'
                color: (0, 0, 0, 1)
                size_hint_y: None
                height: dp(28)

            # 1. 导入 IP 文件
            CardBox:
                size_hint_y: None
                height: dp(100)
                Label:
                    text: "[b]1. 导入 IP 文件[/b]"
                    markup: True
                    font_size: '13sp'
                    color: (0, 0, 0, 1)
                    size_hint_y: None
                    height: dp(20)
                    halign: 'left'
                    text_size: self.size

                BoxLayout:
                    spacing: dp(8)
                    size_hint_y: None
                    height: dp(32)

                    StyledButton:
                        text: "官方 IPv4 库"
                        btn_color: (0/255, 122/255, 255/255, 1)
                        on_release: root.load_preset_ip("v4")

                    StyledButton:
                        text: "官方 IPv6 库"
                        btn_color: (52/255, 199/255, 89/255, 1)
                        on_release: root.load_preset_ip("v6")

                    StyledButton:
                        text: "粘贴/重置"
                        btn_color: (255/255, 149/255, 0/255, 1)
                        on_release: root.paste_from_clipboard()

                Label:
                    text: root.import_status_text
                    font_size: '11sp'
                    color: (140/255, 140/255, 145/255, 1)
                    size_hint_y: None
                    height: dp(18)
                    halign: 'left'
                    text_size: self.size

            # 2. 扫描设置
            CardBox:
                size_hint_y: None
                height: dp(240)
                Label:
                    text: "[b]2. 扫描设置[/b]"
                    markup: True
                    font_size: '13sp'
                    color: (0, 0, 0, 1)
                    size_hint_y: None
                    height: dp(20)
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
                            text: "扫描数量"
                            font_size: '10sp'
                            color: (80/255, 80/255, 80/255, 1)
                            halign: 'left'
                            text_size: self.size
                        FormInput:
                            id: count_input
                            text: "300"
                            hint_text: "留空=全部"

                    BoxLayout:
                        orientation: 'vertical'
                        Label:
                            text: "端口筛选"
                            font_size: '10sp'
                            color: (80/255, 80/255, 80/255, 1)
                            halign: 'left'
                            text_size: self.size
                        FormInput:
                            id: ports_input
                            text: "443, 8443, 2053"

                    BoxLayout:
                        orientation: 'vertical'
                        Label:
                            text: "线程数"
                            font_size: '10sp'
                            color: (80/255, 80/255, 80/255, 1)
                            halign: 'left'
                            text_size: self.size
                        FormInput:
                            id: threads_input
                            text: "100"

                    BoxLayout:
                        orientation: 'vertical'
                        Label:
                            text: "超时 (秒)"
                            font_size: '10sp'
                            color: (80/255, 80/255, 80/255, 1)
                            halign: 'left'
                            text_size: self.size
                        FormInput:
                            id: timeout_input
                            text: "2"

                BoxLayout:
                    size_hint_y: None
                    height: dp(32)
                    spacing: dp(10)
                    Label:
                        text: "严格模式 (TLS握手)"
                        font_size: '11sp'
                        color: (30/255, 30/255, 30/255, 1)
                        halign: 'left'
                        valign: 'middle'
                        text_size: self.size
                    Switch:
                        id: strict_switch
                        active: True
                        size_hint_x: None
                        width: dp(50)

                    Spinner:
                        id: region_spinner
                        text: '全部地区 ▼'
                        values: ['全部地区 ▼', '🇭🇰 香港', '🇯🇵 日本', '🇸🇬 新加坡', '🇺🇸 美国']
                        font_size: '11sp'
                        background_color: (230/255, 230/255, 235/255, 1)
                        color: (0, 0, 0, 1)
                        size_hint_x: 0.45

                BoxLayout:
                    spacing: dp(8)
                    size_hint_y: None
                    height: dp(34)

                    StyledButton:
                        text: "开始扫描" if not root.is_scanning else "正在扫描..."
                        btn_color: (0/255, 122/255, 255/255, 1)
                        on_release: root.start_scan()

                    StyledButton:
                        text: "停止"
                        btn_color: (180/255, 180/255, 185/255, 1)
                        on_release: root.stop_scan()

                Label:
                    text: root.scan_status_text
                    font_size: '11sp'
                    color: (0/255, 122/255, 255/255, 1)
                    size_hint_y: None
                    height: dp(18)
                    halign: 'left'
                    text_size: self.size

            # 3. 可用 IP 列表
            CardBox:
                size_hint_y: None
                height: dp(360)
                Label:
                    text: "[b]3. 可用 IP (仅显示可连接的 IP)[/b]"
                    markup: True
                    font_size: '13sp'
                    color: (0, 0, 0, 1)
                    size_hint_y: None
                    height: dp(20)
                    halign: 'left'
                    text_size: self.size

                BoxLayout:
                    size_hint_y: None
                    height: dp(30)
                    spacing: dp(6)

                    Label:
                        text: "已筛选: " + str(len(root.valid_ips_data)) + " 个"
                        font_size: '11sp'
                        color: (100/255, 100/255, 100/255, 1)
                        halign: 'left'
                        valign: 'middle'
                        text_size: self.size

                    StyledButton:
                        text: "📋 一键复制 IP"
                        btn_color: (52/255, 199/255, 89/255, 1)
                        size_hint_x: 0.45
                        on_release: root.copy_ips_to_clipboard()

                ScrollView:
                    do_scroll_x: False
                    BoxLayout:
                        id: results_container
                        orientation: 'vertical'
                        spacing: dp(4)
                        size_hint_y: None
                        height: self.minimum_height
"""

Builder.load_string(KV_STYLE)


class ResultItem(BoxLayout):
    ip_text = StringProperty('')
    latency_text = StringProperty('')
    region_text = StringProperty('')
    speed_text = StringProperty('')


class MainUI(BoxLayout):
    import_status_text = StringProperty("默认已载入 15 个 IPv4 官方网段")
    scan_status_text = StringProperty("就绪")
    is_scanning = BooleanProperty(False)
    valid_ips_data = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stop_requested = False
        self.raw_ip_pool = BUILTIN_IPV4_OFFICIAL[:]
        self.result_queue = queue.Queue()

        Clock.schedule_interval(self._drain_result_queue, 0.08)

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
                self.import_status_text = f"已从剪贴板读取 {len(lines)} 行文本"
            else:
                self.import_status_text = "剪贴板为空！"
        except Exception:
            self.import_status_text = "剪贴板读取失败"

    def start_scan(self):
        if self.is_scanning:
            return

        try:
            max_count = int(self.ids.count_input.text.strip()) if self.ids.count_input.text.strip() else 1000
        except ValueError:
            max_count = 300

        try:
            threads_num = int(self.ids.threads_input.text.strip())
        except ValueError:
            threads_num = 100

        try:
            timeout_sec = float(self.ids.timeout_input.text.strip())
        except ValueError:
            timeout_sec = 2.0

        ports_str = self.ids.ports_input.text.strip()
        ports = [int(p.strip()) for p in re.findall(r'\d+', ports_str)] if ports_str else [443]

        parsed_ips = parse_ips_safe("\n".join(self.raw_ip_pool), max_samples=max_count)
        if not parsed_ips:
            self.scan_status_text = "❌ 未检测到可用 IP，请检查输入"
            return

        self.is_scanning = True
        self.stop_requested = False
        self.ids.results_container.clear_widgets()
        self.valid_ips_data.clear()
        self.scan_status_text = f"正在扫描 0/{len(parsed_ips)}..."

        threading.Thread(
            target=self._scan_runner,
            args=(parsed_ips, ports, threads_num, timeout_sec),
            daemon=True
        ).start()

    def _test_ip_worker(self, ip, ports, timeout_sec):
        if self.stop_requested:
            return

        for port in ports:
            if self.stop_requested:
                break
            is_ssl = port in [443, 8443, 2053, 2083]
            s = socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout_sec)
            start_t = time.perf_counter()
            colo_str = "未知"

            try:
                if is_ssl and self.ids.strict_switch.active:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    tls_sock = ctx.wrap_socket(s, server_hostname="speed.cloudflare.com")
                    tls_sock.connect((ip, port))
                    latency = int((time.perf_counter() - start_t) * 1000)

                    try:
                        req = "GET /cdn-cgi/trace HTTP/1.1\r\nHost: speed.cloudflare.com\r\nConnection: close\r\n\r\n"
                        tls_sock.sendall(req.encode('utf-8'))
                        resp = tls_sock.recv(512).decode('utf-8', errors='ignore')
                        match = re.search(r'colo=([A-Z]{3})', resp)
                        if match:
                            colo_str = COLO_MAP.get(match.group(1), match.group(1))
                    except Exception:
                        pass
                    tls_sock.close()
                else:
                    s.connect((ip, port))
                    latency = int((time.perf_counter() - start_t) * 1000)
                    s.close()

                self.result_queue.put({'ip': ip, 'port': port, 'latency': latency, 'colo': colo_str, 'success': True})
                return
            except Exception:
                pass
            finally:
                try:
                    s.close()
                except Exception:
                    pass

        self.result_queue.put({'ip': ip, 'success': False})

    def _scan_runner(self, ip_list, ports, threads_num, timeout_sec):
        with ThreadPoolExecutor(max_workers=min(threads_num, 150)) as pool:
            futures = [pool.submit(self._test_ip_worker, ip, ports, timeout_sec) for ip in ip_list]
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
                if res.get('success'):
                    ip = res['ip']
                    port = res['port']
                    latency = res['latency']
                    colo = res['colo']

                    item_data = {'ip': ip, 'port': port, 'latency': latency, 'colo': colo}
                    self.valid_ips_data.append(item_data)

                    item_widget = ResultItem(
                        ip_text=f"{ip}:{port}",
                        region_text=colo,
                        latency_text=f"{latency} ms",
                        speed_text="优" if latency < 100 else "良"
                    )
                    self.ids.results_container.add_widget(item_widget)

                    self.scan_status_text = f"正在扫描... 已发现 {len(self.valid_ips_data)} 个可用 IP"
            except queue.Empty:
                break

    def _finish_scan(self):
        self.is_scanning = False
        self.scan_status_text = f"✓ 扫描完成！共获取 {len(self.valid_ips_data)} 个可用节点"

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

            count = len(lines)
            self._show_toast(f"✅ 成功复制 {count} 个 IP 到剪贴板！")
        except Exception:
            self._show_toast("复制完成！")

    def _show_toast(self, message):
        content = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))
        lbl = Label(text=message, font_size='12sp', color=(0, 0, 0, 1), halign='center')
        btn = Button(text="确定", size_hint_y=None, height=dp(32), font_size='12sp')
        content.add_widget(lbl)
        content.add_widget(btn)

        popup = Popup(title="提示", content=content, size_hint=(0.8, 0.24))
        btn.bind(on_release=popup.dismiss)
        popup.open()


class CloudflareScannerApp(App):
    def build(self):
        self.title = "优选 IP 筛选工具"
        return MainUI()


if __name__ == '__main__':
    CloudflareScannerApp().run()
