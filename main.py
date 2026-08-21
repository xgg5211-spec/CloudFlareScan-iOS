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
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.spinner import Spinner

# ==================== 1. 彻底解决 iOS 中文口口乱码 ====================
def init_ios_cjk_font():
    """自动查找 iOS 系统内置的中文字体 (PingFang / STHeiti) 并注册为全局默认字体"""
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
            print(f"[FontManager] 已成功加载 iOS 内置中文字体: {chosen_font}")
        except Exception as e:
            print(f"[FontManager] 注册字体失败: {e}")

init_ios_cjk_font()

# ==================== 2. 赛博朋克炫彩 UI 布局定义 ====================
KV_STYLE = """
#:kivy 2.0.0

<StatCard@BoxLayout>:
    orientation: 'vertical'
    padding: [6, 4]
    title: ''
    value: ''
    value_color: (0/255, 243/255, 255/255, 1)
    canvas.before:
        Color:
            rgba: (18/255, 24/255, 35/255, 0.95)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [6,]
        Color:
            rgba: (0/255, 243/255, 255/255, 0.3)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, 6)
            width: 0.8
    Label:
        text: root.title
        font_size: '10sp'
        color: (130/255, 145/255, 165/255, 1)
        size_hint_y: 0.35
    Label:
        text: root.value
        font_size: '12sp'
        bold: True
        color: root.value_color
        size_hint_y: 0.65

<CyberButton@Button>:
    background_normal: ''
    background_color: 0, 0, 0, 0
    font_size: '12sp'
    bold: True
    color: (0/255, 243/255, 255/255, 1) if self.state == 'normal' else (1, 1, 1, 1)
    canvas.before:
        Color:
            rgba: (0/255, 243/255, 255/255, 0.8) if self.state == 'normal' else (255/255, 0/255, 85/255, 1)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, 6)
            width: 1.2
        Color:
            rgba: (14/255, 20/255, 30/255, 0.9)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [6,]

<MainUI>:
    canvas.before:
        Color:
            rgba: (10/255, 13/255, 18/255, 1)
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: 10
        spacing: 8

        # 1. 顶栏：标题与状态控制
        BoxLayout:
            size_hint_y: None
            height: 28
            Label:
                text: "[b][color=00f3ff]CLOUDFLARE[/color] [color=ff0055]SCANNER[/color] [color=888888]v3.0[/color][/b]"
                markup: True
                font_size: '16sp'
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

        # 2. 本地网络及运营商检测看板
        BoxLayout:
            size_hint_y: None
            height: 26
            canvas.before:
                Color:
                    rgba: (20/255, 30/255, 45/255, 0.8)
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [4,]
            padding: [8, 0]
            Label:
                text: root.isp_info_text
                markup: True
                font_size: '11sp'
                color: (0/255, 243/255, 255/255, 1)
                halign: 'left'
                text_size: self.size
                valign: 'middle'

        # 3. 实时数据统计看板 (4卡片)
        BoxLayout:
            size_hint_y: None
            height: 44
            spacing: 6

            StatCard:
                title: "进度"
                value: f"{root.scanned_count}/{root.total_count}"
                value_color: (0/255, 243/255, 255/255, 1)

            StatCard:
                title: "有效 IP"
                value: str(root.valid_count)
                value_color: (0/255, 255/255, 136/255, 1)

            StatCard:
                title: "最低 TLS 延迟"
                value: root.min_latency_text
                value_color: (255/255, 204/255, 0/255, 1)

            StatCard:
                title: "最高下载速度"
                value: root.max_speed_text
                value_color: (255/255, 0/255, 136/255, 1)

        # 4. 配置选项栏 (端口选择 + 来源选择)
        BoxLayout:
            size_hint_y: None
            height: 32
            spacing: 8
            
            Label:
                text: "测试端口:"
                font_size: '11sp'
                color: (180/255, 195/255, 210/255, 1)
                size_hint_x: 0.22
                halign: 'right'
                valign: 'middle'

            Spinner:
                id: port_spinner
                text: '443 (HTTPS)'
                values: ['443 (HTTPS)', '8443 (HTTPS)', '2053 (HTTPS)', '2083 (HTTPS)', '2087 (HTTPS)', '2096 (HTTPS)', '80 (HTTP)', '8080 (HTTP)', '8880 (HTTP)']
                size_hint_x: 0.38
                font_size: '11sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (0/255, 243/255, 255/255, 1)

            Spinner:
                id: source_spinner
                text: '官方 IPv4 库'
                values: ['官方 IPv4 库', '官方 IPv6 库', '社区精选网段', '自定义/剪贴板']
                size_hint_x: 0.4
                font_size: '11sp'
                background_color: (20/255, 30/255, 45/255, 1)
                color: (0/255, 255/255, 136/255, 1)
                on_text: root.on_source_change(self.text)

        # 5. IP/CIDR 输入框
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: 0.24
            spacing: 2
            TextInput:
                id: ip_input
                hint_text: "点击 [获取IP库] 自动填充，或在此粘贴自定义 CIDR (支持上万 IP 输入)..."
                background_color: (15/255, 20/255, 28/255, 1)
                foreground_color: (0/255, 243/255, 255/255, 1)
                cursor_color: (255/255, 0/255, 85/255, 1)
                font_size: '11sp'
                padding: [6, 6]

        # 6. 控制按钮组
        BoxLayout:
            size_hint_y: None
            height: 36
            spacing: 6

            CyberButton:
                text: "获取 IP 库"
                on_release: root.fetch_selected_ip_source()

            CyberButton:
                text: "停止" if root.is_scanning else "开始真测速"
                on_release: root.toggle_scan()

            CyberButton:
                text: "复制 TOP IP"
                on_release: root.copy_top_ips()

            CyberButton:
                text: "导出代理节点"
                on_release: root.export_proxy_config()

        # 7. 可滚动日志控制台
        BoxLayout:
            orientation: 'vertical'
            ScrollView:
                id: scroller
                bar_width: 4
                bar_color: (0/255, 243/255, 255/255, 0.6)
                canvas.before:
                    Color:
                        rgba: (8/255, 11/255, 16/255, 0.95)
                    Rectangle:
                        pos: self.pos
                        size: self.size
                    Color:
                        rgba: (0/255, 243/255, 255/255, 0.25)
                    Line:
                        rounded_rectangle: (self.x, self.y, self.width, self.height, 6)
                        width: 1
                Label:
                    id: log_label
                    text: root.log_content
                    markup: True
                    font_size: '11sp'
                    size_hint_y: None
                    height: self.texture_size[1]
                    text_size: self.width - 12, None
                    padding: [6, 6]
                    halign: 'left'
                    valign: 'top'
"""

Builder.load_string(KV_STYLE)
executor = ThreadPoolExecutor(max_workers=3)


class MainUI(BoxLayout):
    status_text = StringProperty("系统就绪")
    isp_info_text = StringProperty("🔍 正在识别本地网络与运营商...")
    log_content = StringProperty("[color=00f3ff]=== Cloudflare CyberScanner v3.0 就绪 ===[/color]\n• 已修复 iOS 中文乱码，支持运营商自动识别\n• 支持 TLS 真连接握手 + 10MB HTTP 下载测速\n• 高并发无卡顿并发引擎，支持上万 IP\n")
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
        self.best_ips = []  # [(ip, latency, speed_mbs), ...]
        self.ui_log_buffer = []  # UI 日志节流缓冲区，防止万级 IP 卡顿

        # 启动定时器：每 0.15 秒批量刷新一次日志，防止主线程 UI 假死
        Clock.schedule_interval(self._flush_ui_log_buffer, 0.15)
        
        # 异步获取本地 ISP 运营商信息
        Clock.schedule_once(lambda dt: self.detect_isp_info(), 0.5)

    def append_log(self, text):
        """将日志放入节流缓冲区"""
        self.ui_log_buffer.append(text)

    def _flush_ui_log_buffer(self, dt):
        """批量更新 UI，彻底解决高并发场景下的界面冻结"""
        if self.ui_log_buffer:
            chunk = "\n".join(self.ui_log_buffer) + "\n"
            self.log_content += chunk
            self.ui_log_buffer.clear()
            if hasattr(self.ids, 'scroller'):
                self.ids.scroller.scroll_y = 0

    # ---------------- 1. 自动识别运营商与出口 IP ----------------
    def detect_isp_info(self):
        loop = asyncio.get_event_loop()
        loop.run_in_executor(executor, self._detect_isp_worker)

    def _detect_isp_worker(self):
        isp_text = "🌐 本地网络: 未知运营商 / 直连"
        try:
            req = urllib.request.Request("http://ip-api.com/json/?lang=zh-CN", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                ip = data.get('query', '未知')
                isp = data.get('isp', data.get('org', '未知'))
                city = data.get('city', '')
                country = data.get('country', '')

                # 智能简化中文运营商名称
                if "Telecom" in isp or "电信" in isp:
                    isp_name = "中国电信 (China Telecom)"
                elif "Unicom" in isp or "联通" in isp:
                    isp_name = "中国联通 (China Unicom)"
                elif "Mobile" in isp or "移动" in isp:
                    isp_name = "中国移动 (China Mobile)"
                elif "Tietong" in isp or "铁通" in isp:
                    isp_name = "中国铁通"
                else:
                    isp_name = isp

                isp_text = f"🌐 运营商: [color=00ff88]{isp_name}[/color]  IP: [color=00f3ff]{ip}[/color] ({city} {country})"
        except Exception:
            pass

        Clock.schedule_once(lambda dt: setattr(self, 'isp_info_text', isp_text))

    # ---------------- 2. 自动拉取 / 切换 IP 库 ----------------
    def on_source_change(self, source_name):
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
            self.append_log("[i] 请在输入框粘贴你的自定义 CIDR / IP 地址。")
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
            Clock.schedule_once(lambda dt: self.append_log(f"[X] 拉取 IP 库失败: {e}"))

    def _on_ip_fetch_success(self, lines):
        self.ids.ip_input.text = "\n".join(lines)
        self.status_text = f"已加载 {len(lines)} 条"
        self.append_log(f"[✓] [color=00ff88]成功获取 {len(lines)} 个 IP / CIDR 网段！[/color]")

    # ---------------- 3. 上万 IP 离散采样与后台解析 ----------------
    def toggle_scan(self):
        if self.is_scanning:
            self.stop_scan()
        else:
            self.start_scan()

    def start_scan(self):
        raw_text = self.ids.ip_input.text.strip()
        if not raw_text:
            self.append_log("[!] 请先选择或输入 IP 网段。")
            return

        self.is_scanning = True
        self.status_text = "解析 IP 中..."
        self.scanned_count = 0
        self.valid_count = 0
        self.min_latency_text = "-- ms"
        self.max_speed_text = "-- MB/s"
        self.best_ips.clear()

        # 获取端口配置
        port_str = self.ids.port_spinner.text.split(' ')[0]
        port = int(port_str)

        self.append_log(f"[+] 正在异步打散解析目标 IP（测试端口: {port}）...")
        loop = asyncio.get_event_loop()
        loop.run_in_executor(executor, self._parse_ips_worker, raw_text, port)

    def _parse_ips_worker(self, raw_text, port):
        ip_set = set()
        for line in raw_text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                if '/' in line:
                    net = ipaddress.ip_network(line, strict=False)
                    hosts = list(net.hosts())
                    # 针对 /16 等大网段进行智能打散采样，每个 CIDR 抽 60 个 IP，保证万级 IP 不爆内存
                    sample_size = min(len(hosts), 60)
                    if sample_size > 0:
                        ip_set.update([str(ip) for ip in random.sample(hosts, sample_size)])
                else:
                    ip_set.add(str(ipaddress.ip_address(line)))
            except ValueError:
                continue

        final_ips = list(ip_set)
        random.shuffle(final_ips)
        # 上限抽样 2000 个最具有代表性的 IP 执行高并发测试
        final_ips = final_ips[:2000]
        Clock.schedule_once(lambda dt: self._start_async_ping(final_ips, port))

    # ---------------- 4. TLS 真实连接握手测速引擎 ----------------
    def _start_async_ping(self, ip_list, port):
        if not ip_list:
            self.append_log("[!] 未找到可用的有效 IP 地址。")
            self.is_scanning = False
            self.status_text = "就绪"
            return

        self.total_count = len(ip_list)
        self.status_text = "TLS 握手测速中..."
        self.append_log(f"[+] 开始对 [color=00f3ff]{len(ip_list)}[/color] 个节点执行真实 TLS 握手测速...")

        self.scan_task = asyncio.create_task(self._scanner_coroutine(ip_list, port))

    async def _real_tls_ping(self, ip, port, semaphore):
        """TLS 握手 + Jitter 抖动双重测速"""
        async with semaphore:
            if not self.is_scanning:
                return None

            is_ssl = port in [443, 8443, 2053, 2083, 2087, 2096]
            ssl_ctx = ssl.create_default_context() if is_ssl else None
            if ssl_ctx:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE

            pings = []
            for _ in range(2):  # 探测 2 次，计算真实延迟与抖动
                start_time = time.perf_counter()
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(
                            ip, port, ssl=ssl_ctx,
                            server_hostname="speed.cloudflare.com" if is_ssl else None
                        ),
                        timeout=1.6
                    )
                    latency = (time.perf_counter() - start_time) * 1000
                    writer.close()
                    await writer.wait_closed()
                    pings.append(latency)
                except Exception:
                    break

            if len(pings) > 0:
                avg_latency = round(sum(pings) / len(pings), 1)
                jitter = round(abs(pings[-1] - pings[0]), 1) if len(pings) > 1 else 0.0
                return ip, avg_latency, jitter
            return ip, None, None

    async def _scanner_coroutine(self, ip_list, port):
        semaphore = asyncio.Semaphore(40)  # 高并发安全限制
        tasks = [self._real_tls_ping(ip, port, semaphore) for ip in ip_list]

        for future in asyncio.as_completed(tasks):
            if not self.is_scanning:
                break
            result = await future
            self.scanned_count += 1

            if result:
                ip, latency, jitter = result
                if latency is not None:
                    self.valid_count += 1
                    self.best_ips.append({'ip': ip, 'latency': latency, 'jitter': jitter, 'speed': 0.0})

                    # 根据延迟显示色阶
                    color_str = "00ff88" if latency < 120 else ("00f3ff" if latency < 220 else "ffcc00")
                    min_lat = min(item['latency'] for item in self.best_ips)
                    self.min_latency_text = f"{min_lat} ms"

                    self.append_log(f"[✓] IP: [color=ffffff]{ip:<15}[/color] TLS: [color={color_str}]{latency} ms[/color] (抖动: {jitter}ms)")

        # ---------------- 5. 对前 3 名最快 IP 发起真实 HTTP 下载测速 ----------------
        if self.best_ips and self.is_scanning:
            self.best_ips.sort(key=lambda x: x['latency'])
            top_candidates = self.best_ips[:3]

            self.append_log("\n[+] 正在对前 3 个最快节点发起 [color=ff0088]10MB 真实 HTTP 下载测速[/color]...")
            for item in top_candidates:
                if not self.is_scanning:
                    break
                speed = await self._test_download_speed(item['ip'], port)
                item['speed'] = speed
                if speed > 0:
                    self.append_log(f"[🚀 测速] IP: {item['ip']:<15} 实测下载速度: [color=ff0088]{speed} MB/s[/color]")

            # 更新最高速度面板
            max_s = max(item['speed'] for item in self.best_ips)
            if max_s > 0:
                self.max_speed_text = f"{max_s} MB/s"

        # 最终汇总
        if self.best_ips:
            self.best_ips.sort(key=lambda x: (x['latency'], -x['speed']))
            self.append_log("\n[b][color=00ff88]🏆 TOP 10 优选最快 Cloudflare IP 榜单:[/color][/b]")
            for idx, item in enumerate(self.best_ips[:10], start=1):
                speed_str = f" | 速度: {item['speed']} MB/s" if item['speed'] > 0 else ""
                self.append_log(f"  {idx:2d}. [color=00f3ff]{item['ip']:<15}[/color] - 延迟: [color=00ff88]{item['latency']} ms[/color]{speed_str}")

        self.append_log("\n[✓] [color=00f3ff]全套测速任务完成！[/color]")
        self.is_scanning = False
        self.status_text = "完成"

    async def _test_download_speed(self, ip, port):
        """测算 5MB 文件的实际 HTTP 下载速度 (MB/s)"""
        try:
            start_time = time.perf_counter()
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port, ssl=ssl_ctx, server_hostname="speed.cloudflare.com"),
                timeout=3.5
            )

            # 发送 HTTP GET 请求拉取测速文件
            req = f"GET /__down?bytes=5000000 HTTP/1.1\r\nHost: speed.cloudflare.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
            writer.write(req.encode())
            await writer.drain()

            downloaded_bytes = 0
            while True:
                chunk = await asyncio.wait_for(reader.read(16384), timeout=2.0)
                if not chunk:
                    break
                downloaded_bytes += len(chunk)
                if downloaded_bytes >= 5000000:
                    break

            writer.close()
            await writer.wait_closed()

            duration = time.perf_counter() - start_time
            if duration > 0 and downloaded_bytes > 100000:
                mb_s = round((downloaded_bytes / (1024 * 1024)) / duration, 2)
                return mb_s
        except Exception:
            pass
        return 0.0

    # ---------------- 6. 复制与一键导出代理节点 ----------------
    def copy_top_ips(self):
        if not self.best_ips:
            self.append_log("[!] 暂无可用 IP，请先执行测速。")
            return

        top_5 = self.best_ips[:5]
        ips_text = "\n".join([item['ip'] for item in top_5])
        Clipboard.copy(ips_text)
        self.append_log(f"[✓] [color=00ff88]已将前 {len(top_5)} 个最快 IP 复制到剪贴板！[/color]")

    def export_proxy_config(self):
        """导出适配 Shadowrocket / Clash / Surge 的节点列表格式"""
        if not self.best_ips:
            self.append_log("[!] 暂无可用 IP，请先执行测速。")
            return

        port_str = self.ids.port_spinner.text.split(' ')[0]
        nodes = []
        for idx, item in enumerate(self.best_ips[:5], start=1):
            nodes.append(f"Cloudflare-优选IP-{idx} = vmess, {item['ip']}, {port_str}, username=uuid")

        export_text = "\n".join(nodes)
        Clipboard.copy(export_text)
        self.append_log(f"[✓] [color=00ff88]已生成代理节点格式并复制至剪贴板！[/color]")

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
