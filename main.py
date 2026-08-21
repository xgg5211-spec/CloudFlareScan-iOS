import asyncio
import ipaddress
import random
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout

# 赛博朋克深色炫彩 UI (KV 声明)
KV_STYLE = """
#:kivy 2.0.0

<StatCard@BoxLayout>:
    orientation: 'vertical'
    padding: [8, 4]
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
        size_hint_y: 0.4
    Label:
        text: root.value
        font_size: '13sp'
        bold: True
        color: root.value_color
        size_hint_y: 0.6

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
        padding: 12
        spacing: 10

        # 1. 顶栏：标题与状态控制
        BoxLayout:
            size_hint_y: None
            height: 32
            Label:
                text: "[b][color=00f3ff]CLOUDFLARE[/color] [color=ff0055]SCANNER[/color][/b]"
                markup: True
                font_size: '18sp'
                halign: 'left'
                text_size: self.size
                valign: 'middle'

            Label:
                text: root.status_text
                color: (0/255, 255/255, 136/255, 1)
                font_size: '12sp'
                halign: 'right'
                text_size: self.size
                valign: 'middle'

        # 2. 实时数据统计看板
        BoxLayout:
            size_hint_y: None
            height: 48
            spacing: 8

            StatCard:
                title: "扫描进度"
                value: f"{root.scanned_count}/{root.total_count}"
                value_color: (0/255, 243/255, 255/255, 1)

            StatCard:
                title: "可用 IP 数"
                value: str(root.valid_count)
                value_color: (0/255, 255/255, 136/255, 1)

            StatCard:
                title: "最低延迟"
                value: root.min_latency_text
                value_color: (255/255, 204/255, 0/255, 1)

        # 3. IP / CIDR 多行输入框
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: 0.26
            spacing: 4
            Label:
                text: "[color=8899aa]自定义 CIDR 网段 / IP (多条换行):[/color]"
                markup: True
                font_size: '11sp'
                size_hint_y: None
                height: 18
                halign: 'left'
                text_size: self.size

            TextInput:
                id: ip_input
                hint_text: "点击 [云端同步] 获取官方 IP 库\\n或直接输入:\\n104.16.0.0/16\\n172.67.0.1"
                background_color: (16/255, 21/255, 30/255, 1)
                foreground_color: (0/255, 243/255, 255/255, 1)
                cursor_color: (255/255, 0/255, 85/255, 1)
                font_size: '12sp'
                padding: [8, 8]

        # 4. 控制操作按钮组
        BoxLayout:
            size_hint_y: None
            height: 38
            spacing: 8

            CyberButton:
                text: "云端同步"
                on_release: root.on_sync_cloud_ips()

            CyberButton:
                text: "停止" if root.is_scanning else "开始测速"
                on_release: root.toggle_scan()

            CyberButton:
                text: "复制 TOP IP"
                on_release: root.copy_top_ips()

        # 5. 可滚动彩色日志区域
        BoxLayout:
            orientation: 'vertical'
            ScrollView:
                id: scroller
                bar_width: 5
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
                    text_size: self.width - 16, None
                    padding: [8, 8]
                    halign: 'left'
                    valign: 'top'
"""

Builder.load_string(KV_STYLE)
executor = ThreadPoolExecutor(max_workers=2)


class MainUI(BoxLayout):
    status_text = StringProperty("系统就绪")
    log_content = StringProperty("[color=00f3ff]=== 赛博扫描器已准备就绪 ===[/color]\n点击 [color=ff0055][云端同步][/color] 获取官方最新 IP 库\n点击 [color=00ff88][开始测速][/color] 执行真实的 TLS 握手延迟评估\n")
    is_scanning = BooleanProperty(False)
    
    # 统计数据属性
    scanned_count = NumericProperty(0)
    total_count = NumericProperty(0)
    valid_count = NumericProperty(0)
    min_latency_text = StringProperty("-- ms")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scan_task = None
        self.best_ips = []  # 存储 (ip, latency) 结果列表

    def append_log(self, text):
        """追加日志并自动平滑滚动到底部"""
        self.log_content += text + "\n"
        Clock.schedule_once(lambda dt: self._scroll_to_bottom())

    def _scroll_to_bottom(self):
        if hasattr(self.ids, 'scroller'):
            self.ids.scroller.scroll_y = 0

    # ---------------- 1. 同步云端官方 IP 库 ----------------
    def on_sync_cloud_ips(self):
        if self.is_scanning:
            return
        self.status_text = "同步云端 IP..."
        self.append_log("[+] 正在从 Cloudflare 官方拉取最新 CIDR 网段...")
        
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
        self.status_text = f"已获得 {len(cidrs)} 个网段"
        self.append_log("[✓] [color=00ff88]云端 IP 库同步成功！已自动填充。[/color]")

    def _on_sync_failed(self, err_msg):
        self.status_text = "同步失败"
        self.append_log(f"[X] [color=ff0055]同步失败: {err_msg}[/color]")

    # ---------------- 2. 智能离散抽样 IP 解析 ----------------
    def toggle_scan(self):
        if self.is_scanning:
            self.stop_scan()
        else:
            self.start_scan()

    def start_scan(self):
        raw_text = self.ids.ip_input.text.strip()
        if not raw_text:
            self.append_log("[!] 请先输入 IP/网段 或点击 [云端同步]。")
            return

        self.is_scanning = True
        self.status_text = "解析 IP 中..."
        self.scanned_count = 0
        self.valid_count = 0
        self.min_latency_text = "-- ms"
        self.best_ips.clear()
        
        self.append_log("[+] 后台打散抽样解析 IP 中，请稍候...")
        loop = asyncio.get_event_loop()
        loop.run_in_executor(executor, self._parse_ips_worker, raw_text)

    def _parse_ips_worker(self, raw_text):
        ip_list = []
        for line in raw_text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                if '/' in line:
                    net = ipaddress.ip_network(line, strict=False)
                    hosts = list(net.hosts())
                    # 抽取 10% 或上限 100 个 IP，保证覆盖面
                    sample_size = min(len(hosts), 80)
                    if sample_size > 0:
                        ip_list.extend([str(ip) for ip in random.sample(hosts, sample_size)])
                else:
                    ip_list.append(str(ipaddress.ip_address(line)))
            except ValueError:
                continue

        # 随机打散，避免连续探测同一网段
        random.shuffle(ip_list)
        # 上限截取 1500 个 IP，兼顾速度与全面性
        final_ips = ip_list[:1500]
        Clock.schedule_once(lambda dt: self._start_async_ping(final_ips))

    # ---------------- 3. TLS 真实握手并发测速 ----------------
    def _start_async_ping(self, ip_list):
        if not ip_list:
            self.append_log("[!] 未找到有效 IP 地址。")
            self.is_scanning = False
            self.status_text = "就绪"
            return

        self.total_count = len(ip_list)
        self.status_text = f"测速中..."
        self.append_log(f"[+] 解析完成，已抽取 [color=00f3ff]{len(ip_list)}[/color] 个随机节点，发起 TLS 握手测速...")

        self.scan_task = asyncio.create_task(self._scanner_coroutine(ip_list))

    async def _real_tls_ping(self, ip, semaphore, port=443):
        """原生 TLS 握手测速"""
        async with semaphore:
            if not self.is_scanning:
                return None

            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

            start_time = time.perf_counter()
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port, ssl=ssl_ctx, server_hostname="speed.cloudflare.com"),
                    timeout=1.8
                )
                latency = round((time.perf_counter() - start_time) * 1000, 1)
                writer.close()
                await writer.wait_closed()
                return ip, latency
            except Exception:
                return ip, None

    async def _scanner_coroutine(self, ip_list):
        semaphore = asyncio.Semaphore(35)  # iOS 并发 Socket 安全阈值
        tasks = [self._real_tls_ping(ip, semaphore) for ip in ip_list]

        for future in asyncio.as_completed(tasks):
            if not self.is_scanning:
                break
            result = await future
            self.scanned_count += 1

            if result:
                ip, latency = result
                if latency is not None:
                    self.valid_count += 1
                    self.best_ips.append((ip, latency))

                    # 格式化不同延迟的颜色显示
                    if latency < 100:
                        color_str = "00ff88"  # 极速荧光绿
                    elif latency < 200:
                        color_str = "00f3ff"  # 青色
                    elif latency < 350:
                        color_str = "ffcc00"  # 黄色
                    else:
                        color_str = "ff5555"  # 红色

                    # 更新最低延迟记录
                    min_lat = min(item[1] for item in self.best_ips)
                    self.min_latency_text = f"{min_lat} ms"

                    self.append_log(f"[✓] IP: [color=ffffff]{ip:<15}[/color] TLS 延迟: [color={color_str}]{latency} ms[/color]")

        # ---------------- 4. 自动排序与总结 ----------------
        if self.best_ips:
            self.best_ips.sort(key=lambda x: x[1])
            self.append_log("\n[b][color=00ff88]🏆 TOP 10 优选最快 IP 榜单:[/color][/b]")
            for idx, (ip, lat) in enumerate(self.best_ips[:10], start=1):
                self.append_log(f"  {idx:2d}. [color=00f3ff]{ip:<15}[/color] - [color=00ff88]{lat} ms[/color]")

        self.append_log("\n[✓] [color=00f3ff]扫描流程全部结束！[/color]")
        self.is_scanning = False
        self.status_text = "已完成"

    def copy_top_ips(self):
        """将最快的 5 个 IP 一键复制到系统剪贴板"""
        if not self.best_ips:
            self.append_log("[!] 暂无可用优选 IP，请先执行测速。")
            return
        
        top_5 = self.best_ips[:5]
        ips_text = "\n".join([ip for ip, lat in top_5])
        Clipboard.copy(ips_text)
        self.append_log(f"[✓] [color=00ff88]已将前 {len(top_5)} 个最快 IP 复制到剪贴板！[/color]")

    def stop_scan(self):
        self.is_scanning = False
        if self.scan_task:
            self.scan_task.cancel()
        self.status_text = "已停止"
        self.append_log("[!] 用户手动停止了测速。")


class CyberScannerApp(App):
    def build(self):
        self.title = "Cloudflare CyberScanner"
        return MainUI()


if __name__ == '__main__':
    CyberScannerApp().run()
