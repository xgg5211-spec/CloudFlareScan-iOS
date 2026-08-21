import asyncio
import ipaddress
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout

# 赛博朋克炫彩 UI (KV 布局语言)
KV_STYLE = """
#:kivy 2.0.0

<CyberButton@Button>:
    background_normal: ''
    background_color: 0, 0, 0, 0
    font_size: '14sp'
    bold: True
    color: (0/255, 243/255, 255/255, 1) if self.state == 'normal' else (1, 1, 1, 1)
    canvas.before:
        Color:
            rgba: (0/255, 243/255, 255/255, 0.8) if self.state == 'normal' else (255/255, 0/255, 85/255, 1)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, 8)
            width: 1.2
        Color:
            rgba: (13/255, 20/255, 30/255, 0.85)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [8,]

<MainUI>:
    canvas.before:
        Color:
            rgba: (13/255, 14/255, 21/255, 1) # 极夜黑深色背景
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: 15
        spacing: 12

        # 1. 顶栏：炫彩标题与状态控制
        BoxLayout:
            size_hint_y: None
            height: 40
            Label:
                text: "[b][color=00f3ff]CLOUDFLARE[/color] [color=ff0055]SCANNER[/color][/b]"
                markup: True
                font_size: '20sp'
                halign: 'left'
                text_size: self.size

            Label:
                text: root.status_text
                color: (0, 1, 0.6, 1)
                font_size: '12sp'
                halign: 'right'
                text_size: self.size

        # 2. 自定义 IP 输入框（带霓虹暗框）
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: 0.3
            spacing: 5
            Label:
                text: "[color=888888]自定义 IP / CIDR 网段 (多条用换行隔开):[/color]"
                markup: True
                font_size: '12sp'
                size_hint_y: None
                height: 20
                halign: 'left'
                text_size: self.size

            TextInput:
                id: ip_input
                hint_text: "104.16.0.0/16\\n172.67.0.1"
                background_color: (20/255, 25/255, 35/255, 1)
                foreground_color: (0/255, 243/255, 255/255, 1)
                cursor_color: (255/255, 0/255, 85/255, 1)
                padding: [10, 10]

        # 3. 核心功能控制按钮组
        BoxLayout:
            size_hint_y: None
            height: 42
            spacing: 10

            CyberButton:
                text: "SYNC CLOUD IP"
                on_release: root.on_sync_cloud_ips()

            CyberButton:
                text: "STOP" if root.is_scanning else "START SCAN"
                on_release: root.toggle_scan()

        # 4. 扫描结果展示区域
        BoxLayout:
            orientation: 'vertical'
            canvas.before:
                Color:
                    rgba: (0/255, 243/255, 255/255, 0.2)
                Line:
                    rounded_rectangle: (self.x, self.y, self.width, self.height, 6)
                    width: 1

            TextInput:
                id: result_log
                text: root.log_content
                readonly: True
                background_color: (10/255, 12/255, 18/255, 1)
                foreground_color: (0, 1, 0.8, 1)
                font_size: '12sp'
                padding: [10, 10]
"""

Builder.load_string(KV_STYLE)

# 用于 CPU 耗时任务（如解析万级 IP 段）的后台线程池
executor = ThreadPoolExecutor(max_workers=2)


class MainUI(BoxLayout):
    status_text = StringProperty("系统就绪")
    log_content = StringProperty("=== 赛博扫描器已准备就绪 ===\n点击 [SYNC CLOUD IP] 获取官方 IP 库\n点击 [START SCAN] 开始 TLS 真连接测速\n")
    is_scanning = BooleanProperty(False)
    total_scanned = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scan_task = None
        self.ip_queue = []

    # ---------------- 1. 自动对接云端 IP 库 ----------------
    def on_sync_cloud_ips(self):
        if self.is_scanning:
            return
        self.status_text = "正在同步云端 IP..."
        self.append_log("[+] 开始从 Cloudflare 官方同步最新 IPv4 库...")
        
        # 使用线程异步请求，防止阻塞主界面
        loop = asyncio.get_event_loop()
        loop.run_in_executor(executor, self._fetch_remote_ips_thread)

    def _fetch_remote_ips_thread(self):
        url = "https://www.cloudflare.com/ips-v4"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=6) as response:
                content = response.read().decode('utf-8')
                cidrs = [line.strip() for line in content.splitlines() if line.strip()]
                Clock.schedule_once(lambda dt: self._on_sync_success(cidrs))
        except Exception as e:
            Clock.schedule_once(lambda dt: self._on_sync_failed(str(e)))

    def _on_sync_success(self, cidrs):
        self.ids.ip_input.text = "\n".join(cidrs)
        self.status_text = f"已获取 {len(cidrs)} 个网段"
        self.append_log(f"[✓] 云端 IP 库同步成功！已自动填入输入框。")

    def _on_sync_failed(self, err_msg):
        self.status_text = "同步失败"
        self.append_log(f"[X] 同步云端 IP 失败: {err_msg}")

    # ---------------- 2. 异步解析输入框中的自定义 IP（防卡顿） ----------------
    def toggle_scan(self):
        if self.is_scanning:
            self.stop_scan()
        else:
            self.start_scan()

    def start_scan(self):
        raw_text = self.ids.ip_input.text.strip()
        if not raw_text:
            self.append_log("[!] 请先输入 IP 段或点击 SYNC 同步云端 IP 库。")
            return

        self.is_scanning = True
        self.status_text = "解析 IP 中..."
        self.append_log("[+] 后台异步解析 IP 地址中，请稍候...")
        
        # 将耗时的 CIDR 展开逻辑放入线程池，UI 保持流畅
        loop = asyncio.get_event_loop()
        loop.run_in_executor(executor, self._parse_ips_worker, raw_text)

    def _parse_ips_worker(self, raw_text):
        ip_set = set()
        for line in raw_text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                if '/' in line:
                    net = ipaddress.ip_network(line, strict=False)
                    # 采样抽取 IP，避免 CIDR 展开爆内存
                    for idx, ip in enumerate(net.hosts()):
                        if idx % 8 == 0:  # 每 8 个 IP 抽取 1 个
                            ip_set.add(str(ip))
                        if len(ip_set) >= 3000: # 最大限制 3000 个
                            break
                else:
                    ip_set.add(str(ipaddress.ip_address(line)))
            except ValueError:
                continue
        
        parsed_list = list(ip_set)
        Clock.schedule_once(lambda dt: self._start_async_ping(parsed_list))

    # ---------------- 3. TLS 真实握手测速（真连接测速） ----------------
    def _start_async_ping(self, ip_list):
        if not ip_list:
            self.append_log("[!] 未解析到有效 IP 地址。")
            self.is_scanning = False
            self.status_text = "就绪"
            return

        self.ip_queue = ip_list
        self.status_text = f"测速中 (0/{len(ip_list)})"
        self.append_log(f"[+] 解析出 {len(ip_list)} 个目标 IP，开始 TLS 握手测速...")

        # 开启并发异步扫描
        self.scan_task = asyncio.create_task(self._scanner_coroutine(ip_list))

    async def _real_tls_ping(self, ip, semaphore, port=443):
        """原生 TLS 握手延迟测试"""
        async with semaphore:
            if not self.is_scanning:
                return None
            
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

            start_time = time.perf_counter()
            try:
                # 发起完整 TLS 加密握手
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port, ssl=ssl_ctx, server_hostname="speed.cloudflare.com"),
                    timeout=2.0
                )
                latency = (time.perf_counter() - start_time) * 1000
                writer.close()
                await writer.wait_closed()
                return ip, round(latency, 2)
            except Exception:
                return ip, None

    async def _scanner_coroutine(self, ip_list):
        semaphore = asyncio.Semaphore(30) # 限制 30 并发，完美适配 iOS Socket 限制
        completed = 0
        total = len(ip_list)

        tasks = [self._real_tls_ping(ip, semaphore) for ip in ip_list]
        
        for future in asyncio.as_completed(tasks):
            if not self.is_scanning:
                break
            result = await future
            completed += 1
            
            if completed % 10 == 0 or completed == total:
                self.status_text = f"测速中 ({completed}/{total})"

            if result:
                ip, latency = result
                if latency is not None:
                    self.append_log(f"[成功] IP: {ip:<15}  TLS 延迟: {latency} ms")

        self.append_log("[✓] 扫描任务已完成！")
        self.is_scanning = False
        self.status_text = "完成"

    def stop_scan(self):
        self.is_scanning = False
        if self.scan_task:
            self.scan_task.cancel()
        self.status_text = "已停止"
        self.append_log("[!] 用户手动终止了扫描。")

    def append_log(self, text):
        self.log_content += text + "\n"


class CyberScannerApp(App):
    def build(self):
        self.title = "CloudFlare CyberScanner"
        return MainUI()


if __name__ == '__main__':
    CyberScannerApp().run()
