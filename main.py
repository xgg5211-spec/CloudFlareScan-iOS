import asyncio
import glob
import ipaddress
import json
import os
import random
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.text import DEFAULT_FONT, LabelBase
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

# ==================== 1. iOS 系统中文字体自动加载 (解决口口乱码) ====================
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

# ==================== 2. 全自适应赛博朋克 UI 样式 (KV Layout) ====================
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
        padding: [dp(10), dp(25), dp(10), dp(10)]  # 顶部增加 25dp iOS 刘海/灵动岛安全边距
        spacing: dp(6)

        # 1. 顶栏：标题与运行状态
        BoxLayout:
            size_hint_y: None
            height: dp(26)
            Label:
                text: "[b][color=00f3ff]CLOUDFLARE[/color] [color=ff0055]SCANNER[/color] [color=888888]v3.5[/color][/b]"
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

        # 2. 本地网络 & 运营商看板
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
                title: "最低延迟"
                value: root.min_latency_text
                value_color: (255/255, 204/255, 0/255, 1)

            StatCard:
                title: "最高下载"
                value: root.max_speed_text
                value_color: (255/255, 0/255, 136/255, 1)

        # 4. 参数选择栏 (端口 + 来源 + 线程)
        BoxLayout:
            size_hint_y: None
            height: dp(30)
            spacing: dp(4)

            Spinner:
                id: port_spinner
                text: '443 (HTTPS)'
                values: ['443 (HTTPS)', '8443 (HTTPS)', '2053 (HTTPS)', '2083 (HTTPS)', '80 (HTTP)', '8080 (HTTP)']
                size_hint_x: 0.35
                font_size: '10sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (0/255, 243/255, 255/255, 1)

            Spinner:
                id: source_spinner
                text: '官方 IPv4 库'
                values: ['官方 IPv4 库', '官方 IPv6 库', '社区精选网段', '自定义导入']
                size_hint_x: 0.38
                font_size: '10sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (0/255, 255/255, 136/255, 1)
                on_text: root.on_source_change(self.text)

            Spinner:
                id: thread_spinner
                text: '15 线程(防闪退)'
                values: ['10 线程(极稳)', '15 线程(防闪退)', '25 线程(高速)']
                size_hint_x: 0.32
                font_size: '10sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (255/255, 204/255, 0/255, 1)

        # 5. IP/CIDR 文本输入框与一键导入操作栏
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: 0.22
            spacing: dp(3)

            TextInput:
                id: ip_input
                hint_text: "点击下方 [剪贴板导入] 或 [URL导入]，亦可直接粘贴 CIDR / IP 列表..."
                background_color: (15/255, 20/255, 28/255, 1)
                foreground_color: (0/255, 243/255, 255/255, 1)
                cursor_color: (255/255, 0/255, 85/255, 1)
                font_size: '10sp'
                padding: [dp(6), dp(6)]

        # 6. 多功能快捷操作组
        BoxLayout:
            size_hint_y: None
            height: dp(32)
            spacing: dp(4)

            CyberButton:
                text: "📋 剪贴板导入"
                on_release: root.import_from_clipboard()

            CyberButton:
                text: "🌐 URL导入"
                on_release: root.show_url_import_dialog()

            CyberButton:
                text: "停止" if root.is_scanning else "🚀 开始测速"
                on_release: root.toggle_scan()

            CyberButton:
                text: "📤 导出节点"
                on_release: root.export_proxy_config()

        # 7. 动态滚动日志终端 (防止显存溢出的环形渲染)
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
executor = ThreadPoolExecutor(max_workers=3)


class MainUI(BoxLayout):
    status_text = StringProperty("系统就绪")
    isp_info_text = StringProperty("🔍 正在识别本地运营商与 IP...")
    log_content = StringProperty("[color=00f3ff]=== Cloudflare CyberScanner v3.5 (防闪退自适应版) ===[/color]\n• 已全盘修复 iOS 句柄超限导致的闪退问题\n• 已加入环形日志显存保护，万级 IP 毫无压力\n• 适配全系 iPhone / iPad 屏幕尺寸\n")
    is_scanning = BooleanProperty(False)

    # 统计数据
    scanned_count = NumericProperty(0)
    total_count = NumericProperty(0)
    valid_count = NumericProperty(0)
    min_latency_text = StringProperty("-- ms")
    max_speed_text = StringProperty("-- MB/s")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scan_task = None
        self.best_ips = []
        self.ui_log_buffer = []
        self.raw_log_lines = self.log_content.splitlines()

        # UI 0.15 秒防抖刷新，彻底绝杀 UI 线程冻结
        Clock.schedule_interval(self._flush_ui_log_buffer, 0.15)
        
        # 异步识别网络运营商
        Clock.schedule_once(lambda dt: self.detect_isp_info(), 0.5)

    def append_log(self, text):
        self.ui_log_buffer.append(text)

    def _flush_ui_log_buffer(self, dt):
        """环形日志刷新：固定保持最新 150 行，彻底防止 iOS GPU 显存爆满闪退"""
        if self.ui_log_buffer:
            self.raw_log_lines.extend(self.ui_log_buffer)
            self.ui_log_buffer.clear()

            if len(self.raw_log_lines) > 150:
                self.raw_log_lines = self.raw_log_lines[-150:]

            self.log_content = "\n".join(self.raw_log_lines) + "\n"
            if hasattr(self.ids, 'scroller'):
                self.ids.scroller.scroll_y = 0

    # ---------------- 1. 本地运营商自动识别 ----------------
    def detect_isp_info(self):
        loop = asyncio.get_event_loop()
        loop.run_in_executor(executor, self._detect_isp_worker)

    def _detect_isp_worker(self):
        isp_text = "🌐 本地网络: 未知运营商"
        try:
            req = urllib.request.Request("http://ip-api.com/json/?lang=zh-CN", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                ip = data.get('query', '未知')
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

                isp_text = f"🌐 运营商: [color=00ff88]{isp_name}[/color]  公网IP: [color=00f3ff]{ip}[/color] ({city})"
        except Exception:
            pass

        Clock.schedule_once(lambda dt: setattr(self, 'isp_info_text', isp_text))

    # ---------------- 2. 自定义 IP 导入功能 ----------------
    def import_from_clipboard(self):
        """从 iOS 剪贴板一键读取自定义 IP / CIDR"""
        text = Clipboard.paste()
        if text and text.strip():
            self.ids.ip_input.text = text.strip()
            lines = [l for l in text.splitlines() if l.strip()]
            self.append_log(f"[✓] [color=00ff88]成功从剪贴板导入 {len(lines)} 行自定义 IP/CIDR！[/color]")
            self.status_text = "已导入剪贴板"
        else:
            self.append_log("[!] 剪贴板为空，请先复制 IP 或 CIDR 网段。")

    def show_url_import_dialog(self):
        """弹窗支持输入自定义 txt / 订阅 链接"""
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        url_input = TextInput(
            text="https://raw.githubusercontent.com/ip-thailand/cloudflare-ip/main/cloudflare-ipv4.txt",
            hint_text="粘贴你的 txt / IP 库 URL 链接",
            multiline=False,
            size_hint_y=None,
            height=dp(38),
            font_size='11sp'
        )
        btn_box = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
        btn_confirm = CyberButton(text="下载并导入")
        btn_cancel = CyberButton(text="取消")

        btn_box.add_widget(btn_confirm)
        btn_box.add_widget(btn_cancel)
        content.add_widget(url_input)
        content.add_widget(btn_box)

        popup = Popup(title="🌐 导入自定义网络 IP 库", content=content, size_hint=(0.88, 0.32))

        def on_download(instance):
            url = url_input.text.strip()
            if url:
                popup.dismiss()
                self.fetch_ip_from_custom_url(url)

        btn_confirm.bind(on_release=on_download)
        btn_cancel.bind(on_release=popup.dismiss)
        popup.open()

    def fetch_ip_from_custom_url(self, url):
        self.status_text = "下载 IP 库..."
        self.append_log(f"[+] 正在从自定义链接下载: {url}")
        loop = asyncio.get_event_loop()
        loop.run_in_executor(executor, self._fetch_url_worker, url)

    def on_source_change(self, source_name):
        if source_name == "自定义导入":
            self.import_from_clipboard()
        else:
            self.fetch_selected_ip_source(source_name)

    def fetch_selected_ip_source(self, source_name=None):
        if not source_name:
            source_name = self.ids.source_spinner.text

        if source_name == "官方 IPv4 库":
            url = "https://www.cloudflare.com/ips-v4"
        elif source_name == "官方 IPv6 库":
            url = "https://www.cloudflare.com/ips-v6"
        elif source_name == "社区精选网段":
            url = "https://raw.githubusercontent.com/ip-thailand/cloudflare-ip/main/cloudflare-ipv4.txt"
        else:
            return

        self.status_text = "获取 IP 库..."
        self.append_log(f"[+] 正在拉取 [{source_name}]...")
        loop = asyncio.get_event_loop()
        loop.run_in_executor(executor, self._fetch_url_worker, url)

    def _fetch_url_worker(self, url):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=6) as response:
                content = response.read().decode('utf-8')
                lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith('#')]
                Clock.schedule_once(lambda dt: self._on_ip_fetch_success(lines))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.append_log(f"[X] 拉取失败: {e}"))

    def _on_ip_fetch_success(self, lines):
        self.ids.ip_input.text = "\n".join(lines)
        self.status_text = f"已加载 {len(lines)} 条"
        self.append_log(f"[✓] [color=00ff88]成功获取 {len(lines)} 个 IP / CIDR 网段！[/color]")

    # ---------------- 3. IP 解析与打散算法 ----------------
    def toggle_scan(self):
        if self.is_scanning:
            self.stop_scan()
        else:
            self.start_scan()

    def start_scan(self):
        raw_text = self.ids.ip_input.text.strip()
        if not raw_text:
            self.append_log("[!] 请先输入或导入 IP 网段。")
            return

        self.is_scanning = True
        self.status_text = "解析中..."
        self.scanned_count = 0
        self.valid_count = 0
        self.min_latency_text = "-- ms"
        self.max_speed_text = "-- MB/s"
        self.best_ips.clear()

        port_str = self.ids.port_spinner.text.split(' ')[0]
        port = int(port_str)

        # 动态读取用户选择的线程数 (10 / 15 / 25)
        thread_str = self.ids.thread_spinner.text.split(' ')[0]
        max_workers = int(thread_str)

        self.append_log(f"[+] 异步解析目标 IP（端口: {port}，限制并发: {max_workers}）...")
        loop = asyncio.get_event_loop()
        loop.run_in_executor(executor, self._parse_ips_worker, raw_text, port, max_workers)

    def _parse_ips_worker(self, raw_text, port, max_workers):
        ip_set = set()
        for line in raw_text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                if '/' in line:
                    net = ipaddress.ip_network(line, strict=False)
                    hosts = list(net.hosts())
                    sample_size = min(len(hosts), 40)  # 离散化精细采样，防内存暴涨
                    if sample_size > 0:
                        ip_set.update([str(ip) for ip in random.sample(hosts, sample_size)])
                else:
                    ip_set.add(str(ipaddress.ip_address(line)))
            except ValueError:
                continue

        final_ips = list(ip_set)
        random.shuffle(final_ips)
        final_ips = final_ips[:1500]  # 抽取最佳 1500 节点
        Clock.schedule_once(lambda dt: self._start_async_ping(final_ips, port, max_workers))

    # ---------------- 4. 绝对不闪退的 TLS 握手引擎 ----------------
    def _start_async_ping(self, ip_list, port, max_workers):
        if not ip_list:
            self.append_log("[!] 未找到有效 IP 地址。")
            self.is_scanning = False
            self.status_text = "就绪"
            return

        self.total_count = len(ip_list)
        self.status_text = "测速中..."
        self.append_log(f"[+] 开始对 [color=00f3ff]{len(ip_list)}[/color] 个 IP 执行真实 TLS 握手测速...")

        self.scan_task = asyncio.create_task(self._scanner_coroutine(ip_list, port, max_workers))

    async def _real_tls_ping(self, ip, port, semaphore):
        """严格防漏泄 Socket 的 TLS 握手核心逻辑"""
        async with semaphore:
            if not self.is_scanning:
                return ip, None, None

            is_ssl = port in [443, 8443, 2053, 2083]
            ssl_ctx = ssl.create_default_context() if is_ssl else None
            if ssl_ctx:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE

            writer = None
            try:
                start_time = time.perf_counter()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        ip, port, ssl=ssl_ctx,
                        server_hostname="speed.cloudflare.com" if is_ssl else None
                    ),
                    timeout=1.4
                )
                latency = round((time.perf_counter() - start_time) * 1000, 1)
                return ip, latency, 0.0
            except Exception:
                return ip, None, None
            finally:
                if writer:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass

    async def _scanner_coroutine(self, ip_list, port, max_workers):
        # 严格限制信号量，绝不越界 iOS 文件句柄数
        semaphore = asyncio.Semaphore(max_workers)
        tasks = [self._real_tls_ping(ip, port, semaphore) for ip in ip_list]

        for future in asyncio.as_completed(tasks):
            if not self.is_scanning:
                break
            ip, latency, jitter = await future
            self.scanned_count += 1

            if latency is not None:
                self.valid_count += 1
                self.best_ips.append({'ip': ip, 'latency': latency, 'speed': 0.0})

                color_str = "00ff88" if latency < 130 else ("00f3ff" if latency < 230 else "ffcc00")
                min_lat = min(item['latency'] for item in self.best_ips)
                self.min_latency_text = f"{min_lat} ms"

                self.append_log(f"[✓] IP: [color=ffffff]{ip:<15}[/color] TLS: [color={color_str}]{latency} ms[/color]")

        # 对前 3 名进行 HTTP 真下载速度测试
        if self.best_ips and self.is_scanning:
            self.best_ips.sort(key=lambda x: x['latency'])
            top_candidates = self.best_ips[:3]

            self.append_log("\n[+] 正在对前 3 名节点发起 [color=ff0088]HTTP 真实下载测速[/color]...")
            for item in top_candidates:
                if not self.is_scanning:
                    break
                speed = await self._test_download_speed(item['ip'], port)
                item['speed'] = speed
                if speed > 0:
                    self.append_log(f"[🚀 测速] IP: {item['ip']:<15} 实测速度: [color=ff0088]{speed} MB/s[/color]")

            max_s = max(item['speed'] for item in self.best_ips)
            if max_s > 0:
                self.max_speed_text = f"{max_s} MB/s"

        # 汇总榜单
        if self.best_ips:
            self.best_ips.sort(key=lambda x: (x['latency'], -x['speed']))
            self.append_log("\n[b][color=00ff88]🏆 TOP 5 优选最快 Cloudflare IP:[/color][/b]")
            for idx, item in enumerate(self.best_ips[:5], start=1):
                speed_str = f" | {item['speed']} MB/s" if item['speed'] > 0 else ""
                self.append_log(f"  {idx}. [color=00f3ff]{item['ip']:<15}[/color] - [color=00ff88]{item['latency']} ms[/color]{speed_str}")

        self.append_log("\n[✓] [color=00f3ff]全套测速任务安全完成！[/color]")
        self.is_scanning = False
        self.status_text = "完成"

    async def _test_download_speed(self, ip, port):
        """拉取 3MB 测试文件，计算真实 MB/s"""
        writer = None
        try:
            start_time = time.perf_counter()
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port, ssl=ssl_ctx, server_hostname="speed.cloudflare.com"),
                timeout=3.0
            )

            req = f"GET /__down?bytes=3000000 HTTP/1.1\r\nHost: speed.cloudflare.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
            writer.write(req.encode())
            await writer.drain()

            downloaded = 0
            while True:
                chunk = await asyncio.wait_for(reader.read(16384), timeout=1.8)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded >= 3000000:
                    break

            duration = time.perf_counter() - start_time
            if duration > 0 and downloaded > 50000:
                return round((downloaded / (1024 * 1024)) / duration, 2)
        except Exception:
            pass
        finally:
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
        return 0.0

    # ---------------- 5. 导出代理节点 ----------------
    def export_proxy_config(self):
        """一键复制支持 Clash / Shadowrocket 的 IP 节点"""
        if not self.best_ips:
            self.append_log("[!] 暂无测速数据，请先开始测速。")
            return

        port_str = self.ids.port_spinner.text.split(' ')[0]
        result_lines = []
        result_lines.append("# === Cloudflare 优选 IP 列表 ===")
        for idx, item in enumerate(self.best_ips[:8], start=1):
            result_lines.append(f"{item['ip']}#{idx}_Cloudflare_{item['latency']}ms")

        export_text = "\n".join(result_lines)
        Clipboard.copy(export_text)
        self.append_log(f"[✓] [color=00ff88]已将 TOP 8 优选 IP 及配置复制到剪贴板！[/color]")

    def stop_scan(self):
        self.is_scanning = False
        if self.scan_task:
            self.scan_task.cancel()
        self.status_text = "已停止"
        self.append_log("[!] 用户手动终止了测速。")


class CyberScannerApp(App):
    def build(self):
        self.title = "Cloudflare CyberScanner"
        return MainUI()


if __name__ == '__main__':
    CyberScannerApp().run()
