import json
import random
import re
import socket
import ssl
import time
import threading
import urllib.request

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, Line
from kivy.metrics import dp

# ---------------------------------------------------------
# 🎨 随机精美主题库（每次启动随机切换酷炫配色）
# ---------------------------------------------------------
THEMES = [
    {
        "name": "极客霓虹",
        "bg": (0.05, 0.06, 0.10, 1),
        "card": (0.09, 0.11, 0.18, 1),
        "main": (0.0, 0.8, 1.0, 1),
        "accent": (0.0, 1.0, 0.6, 1),
        "text": (0.9, 0.95, 1.0, 1)
    },
    {
        "name": "赛博暗黑",
        "bg": (0.03, 0.03, 0.04, 1),
        "card": (0.08, 0.08, 0.10, 1),
        "main": (1.0, 0.4, 0.7, 1),
        "accent": (0.3, 0.9, 1.0, 1),
        "text": (0.9, 0.9, 0.9, 1)
    },
    {
        "name": "琥珀矩阵",
        "bg": (0.06, 0.04, 0.02, 1),
        "card": (0.12, 0.09, 0.05, 1),
        "main": (1.0, 0.6, 0.0, 1),
        "accent": (0.2, 1.0, 0.4, 1),
        "text": (1.0, 0.9, 0.8, 1)
    }
]

CF_COLO = {
    "HKG": "香港", "TPE": "台湾", "KHH": "高雄", "NRT": "东京", 
    "KIX": "大阪", "ICN": "首尔", "SIN": "新加坡", "BKK": "曼谷", 
    "SJC": "圣何塞", "LAX": "洛杉矶", "FRA": "法兰克福", "LHR": "伦敦"
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


class CardBox(BoxLayout):
    """卡片式容器：带圆角和边框阴影感"""
    def __init__(self, bg_color, border_color, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*bg_color)
            self.rect = Rectangle(pos=self.pos, size=self.size)
            Color(*border_color)
            self.line = Line(rectangle=(self.x, self.y, self.width, self.height), width=1)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
        self.line.rectangle = (self.x, self.y, self.width, self.height)


class ProScannerApp(App):
    def build(self):
        self.theme = random.choice(THEMES)
        self.title = f"IP 筛选工具 [{self.theme['name']}]"
        self.valid_ips = []
        self.is_running = False

        # 根布局
        root = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        with root.canvas.before:
            Color(*self.theme['bg'])
            self.bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda o, v: setattr(self.bg_rect, 'pos', v),
                  size=lambda o, v: setattr(self.bg_rect, 'size', v))

        # 顶部标题
        title_lbl = Label(
            text=f"优选 IP 筛选工具 ({self.theme['name']})",
            size_hint_y=None, height=dp(30),
            font_size=dp(16), bold=True, color=self.theme['main']
        )
        root.add_widget(title_lbl)

        # ==========================================
        # 卡片 1：导入自定义 IP / IP段
        # ==========================================
        card1 = CardBox(self.theme['card'], self.theme['main'], orientation='vertical', padding=dp(8), spacing=dp(5), size_hint_y=0.26)
        
        card1.add_widget(Label(text="1. 自定义 IP / CIDR 网段导入", font_size=dp(13), color=self.theme['text'], size_hint_y=None, height=dp(20)))
        
        self.ip_input = TextInput(
            text="104.16.0.0/24\n173.245.60.252:443",
            hint_text="支持单IP、IP:端口 或 CIDR网段...",
            multiline=True,
            background_normal='', background_color=(0,0,0,0.3),
            foreground_color=self.theme['text'], cursor_color=self.theme['main'],
            font_size=dp(11)
        )
        card1.add_widget(self.ip_input)
        root.add_widget(card1)

        # ==========================================
        # 卡片 2：扫描设置（端口、超时）
        # ==========================================
        card2 = CardBox(self.theme['card'], self.theme['main'], orientation='vertical', padding=dp(8), spacing=dp(5), size_hint_y=0.28)
        card2.add_widget(Label(text="2. 扫描高级设置", font_size=dp(13), color=self.theme['text'], size_hint_y=None, height=dp(20)))

        # 网格输入小表单
        form_grid = GridLayout(cols=2, spacing=dp(6), size_hint_y=None, height=dp(55))
        
        # 端口输入
        p_box = BoxLayout(orientation='vertical', spacing=dp(2))
        p_box.add_widget(Label(text="端口筛选 (逗号隔开)", font_size=dp(10), color=self.theme['text']))
        self.port_input = TextInput(text="443,2053,8443", multiline=False, font_size=dp(11), background_color=(0,0,0,0.3), foreground_color=self.theme['text'])
        p_box.add_widget(self.port_input)
        form_grid.add_widget(p_box)

        # 超时输入
        t_box = BoxLayout(orientation='vertical', spacing=dp(2))
        t_box.add_widget(Label(text="超时限制 (秒)", font_size=dp(10), color=self.theme['text']))
        self.timeout_input = TextInput(text="2.5", multiline=False, font_size=dp(11), background_color=(0,0,0,0.3), foreground_color=self.theme['text'])
        t_box.add_widget(self.timeout_input)
        form_grid.add_widget(t_box)

        card2.add_widget(form_grid)

        # 按钮栏：开始扫描 / 一键复制
        action_box = BoxLayout(orientation='horizontal', spacing=dp(8), size_hint_y=None, height=dp(38))
        
        self.scan_btn = Button(
            text="开始扫描", bold=True, font_size=dp(13),
            background_normal='', background_color=self.theme['main'], color=(0,0,0,1)
        )
        self.scan_btn.bind(on_press=self.toggle_scan)
        action_box.add_widget(self.scan_btn)

        self.copy_btn = Button(
            text="一键复制 IP", bold=True, font_size=dp(13),
            background_normal='', background_color=self.theme['accent'], color=(0,0,0,1)
        )
        self.copy_btn.bind(on_press=self.copy_ips)
        action_box.add_widget(self.copy_btn)

        card2.add_widget(action_box)
        root.add_widget(card2)

        # 状态栏
        self.status_lbl = Label(text="状态: 就绪，等待指令", size_hint_y=None, height=dp(22), font_size=dp(11), color=self.theme['main'])
        root.add_widget(self.status_lbl)

        # ==========================================
        # 卡片 3：可用 IP 实时展示终端
        # ==========================================
        card3 = CardBox(self.theme['card'], self.theme['accent'], orientation='vertical', padding=dp(8), spacing=dp(5), size_hint_y=0.38)
        card3.add_widget(Label(text="3. 可用节点终端（实时更新）", font_size=dp(13), color=self.theme['text'], size_hint_y=None, height=dp(20)))

        self.result_box = TextInput(
            text="", readonly=True, multiline=True,
            hint_text="成功连接的真实IP、TLS握手延迟、地区及测速将在此显示...",
            background_normal='', background_color=(0,0,0,0.3),
            foreground_color=self.theme['accent'], font_size=dp(11)
        )
        card3.add_widget(self.result_box)
        root.add_widget(card3)

        return root

    def parse_ports(self):
        """解析用户输入的多个端口"""
        try:
            ports = []
            for p in self.port_input.text.split(','):
                p = p.strip()
                if p.isdigit():
                    ports.append(int(p))
            return ports if ports else [443]
        except Exception:
            return [443]

    def expand_ips(self, raw_text):
        """智能解析自定义IP、CIDR及多端口组合"""
        lines = re.split(r'[\r\n,\s]+', str(raw_text).strip())
        ports = self.parse_ports()
        seen = set()
        targets = []

        for line in lines:
            item = line.strip()
            if not item: continue

            # 处理 CIDR 网段
            if '/' in item:
                try:
                    ip, mask = item.split('/')
                    mask = int(mask)
                    if mask < 16: mask = 20
                    parts = [int(p) for p in ip.split('.')]
                    ip_num = (parts[0] << 24) + (parts[1] << 16) + (parts[2] << 8) + parts[3]
                    num_hosts = 1 << (32 - mask)
                    
                    # 抽样前 40 个防卡死
                    sample_count = min(num_hosts, 40)
                    step = max(1, num_hosts // sample_count)
                    for i in range(1, num_hosts - 1, step):
                        curr = ip_num + i
                        ip_s = f"{(curr >> 24) & 255}.{(curr >> 16) & 255}.{(curr >> 8) & 255}.{curr & 255}"
                        for p in ports:
                            target = f"{ip_s}:{p}"
                            if target not in seen:
                                seen.add(target)
                                targets.append(target)
                except Exception:
                    pass
                continue

            # 单个 IP 处理
            if ":" in item:
                if item not in seen:
                    seen.add(item)
                    targets.append(item)
            else:
                for p in ports:
                    target = f"{item}:{p}"
                    if target not in seen:
                        seen.add(target)
                        targets.append(target)
        return targets

    def test_node(self, ip_port):
        """TLS 握手 + 真实下载测速 + 地区自动识别"""
        try:
            ip, port = ip_port.split(":")
            port = int(port)
            timeout = float(self.timeout_input.text or 2.5)

            # 1. TLS 握手真实延迟测试
            t0 = time.time()
            sock = socket.create_connection((ip, port), timeout=timeout)
            tls_sock = SSL_CTX.wrap_socket(sock, server_hostname=ip)
            tls_delay = round((time.time() - t0) * 1000, 1)
            tls_sock.close()

            # 2. 探针获取地区与运营商
            url = f"https://check.proxyip.cmliussss.net/check?proxyip={ip_port}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if not data.get("success"): return None
                
                colo = data.get("colo", "OTHER").upper()
                region = CF_COLO.get(colo, colo)
                isp = data.get("asOrganization", "Cloudflare")[:8]

            # 3. 真实测速 (100KB小包)
            speed = 0.0
            try:
                proxy_h = urllib.request.ProxyHandler({'http': f'http://{ip_port}', 'https': f'http://{ip_port}'})
                opener = urllib.request.build_opener(proxy_h)
                s_req = urllib.request.Request("https://speed.cloudflare.com/__down?bytes=102400", headers={'User-Agent': 'Mozilla/5.0'})
                st = time.time()
                with opener.open(s_req, timeout=1.5) as s_resp:
                    buf = s_resp.read()
                    dur = time.time() - st
                    if dur > 0 and len(buf) > 0:
                        speed = round((len(buf) / 1024) / dur, 1)
            except Exception:
                pass

            return {
                "ip": ip_port,
                "region": region,
                "isp": isp,
                "tls": tls_delay,
                "speed": speed
            }
        except Exception:
            return None

    def toggle_scan(self, instance):
        if self.is_running:
            return
        self.is_running = True
        self.scan_btn.disabled = True
        self.scan_btn.text = "扫描中..."
        self.result_box.text = ""
        self.valid_ips = []
        threading.Thread(target=self.run_scan_task, daemon=True).start()

    def run_scan_task(self):
        targets = self.expand_ips(self.ip_input.text)
        if not targets:
            Clock.schedule_once(lambda dt: self.finish_scan("未解析到有效IP！", False))
            return

        results = []
        total = len(targets)

        for i, target in enumerate(targets, 1):
            Clock.schedule_once(lambda dt, idx=i, t=total: setattr(self.status_lbl, 'text', f"正在检测: 进度 ({idx}/{t})"))
            res = self.test_node(target)
            if res:
                results.append(res)
                line = f"✔ {res['ip']} | {res['region']} | {res['isp']} | TLS:{res['tls']}ms | {res['speed']}KB/s\n"
                Clock.schedule_once(lambda dt, l=line: self.append_log(l))

        results.sort(key=lambda x: x["tls"])
        self.valid_ips = [r["ip"] for r in results]
        
        msg = f"扫描完成！找到 {len(self.valid_ips)} 个可用节点"
        Clock.schedule_once(lambda dt: self.finish_scan(msg, False))

    def append_log(self, line):
        self.result_box.text += line

    def finish_scan(self, msg, status):
        self.status_lbl.text = f"状态: {msg}"
        self.scan_btn.disabled = False
        self.scan_btn.text = "开始扫描"
        self.is_running = status

    def copy_ips(self, instance):
        if self.valid_ips:
            Clipboard.copy("\n".join(self.valid_ips))
            self.status_lbl.text = "状态: 已成功将可用 IP 复制到剪贴板！"
        else:
            self.status_lbl.text = "状态: 当前没有可用 IP 可供复制"


if __name__ == "__main__":
    ProScannerApp().run()
