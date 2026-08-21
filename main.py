import json
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

# 使用纯 Unicode 编码映射地区名称，绝对不乱码
CF_COLO = {
    "HKG": "\u4e2d\u56fd\u9999\u6e2f", 
    "TPE": "\u4e2d\u56fd\u53f0\u6e7e", 
    "KHH": "\u4e2d\u56fd\u9ad8\u96c4", 
    "NRT": "\u65e5\u672c\u4e1c\u4eac", 
    "KIX": "\u65e5\u672c\u5927\u962a", 
    "ICN": "\u97e9\u56fd\u9996\u5c14", 
    "SIN": "\u65b0\u52a0\u5761", 
    "BKK": "\u6cf0\u56fd\u66fc\u8c37", 
    "SJC": "\u7f8e\u56fd\u5723\u4f55\u58de", 
    "LAX": "\u7f8e\u56fd\u6d1b\u6749\u77f6", 
    "FRA": "\u5fb7\u56fd\u6cd5\u5170\u514b\u798f", 
    "LHR": "\u82f1\u56fd\u4f26\u6566"
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


class CardBox(BoxLayout):
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


class SafeUnicodeApp(App):
    def build(self):
        self.title = "\u4f18\u9009 IP \u7b5b\u9009\u5de5\u5177"
        self.valid_ips = []
        self.is_running = False

        root = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        with root.canvas.before:
            Color(0.04, 0.05, 0.08, 1)
            self.bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda o, v: setattr(self.bg_rect, 'pos', v),
                  size=lambda o, v: setattr(self.bg_rect, 'size', v))

        # 顶部标题
        title_lbl = Label(
            text="\u26a1 Cloudflare \u4f18\u9009 IP \u7b5b\u9009\u5de5\u5177 \u26a1",
            size_hint_y=None, height=dp(30),
            font_size=dp(14), bold=True, color=(0.0, 0.9, 1.0, 1)
        )
        root.add_widget(title_lbl)

        # 模块 1：自定义 IP / 网段导入
        card1 = CardBox((0.08, 0.10, 0.15, 1), (0.0, 0.9, 1.0, 1), orientation='vertical', padding=dp(8), spacing=dp(4), size_hint_y=0.28)
        card1.add_widget(Label(text="[1] \u81ea\u5b9a\u4e49 IP \u6216 CIDR \u7f51\u6bb5\u5bfc\u5165", font_size=dp(11), color=(0.7, 0.85, 1.0, 1), size_hint_y=None, height=dp(18), bold=True))
        
        self.ip_input = TextInput(
            text="104.16.0.0/24\n173.245.60.252:443",
            hint_text="\u5728\u6b64\u8f93\u5165\u6216\u7c98\u8d34 IP / \u7f51\u6bb5...",
            multiline=True,
            background_normal='', background_color=(0, 0, 0, 0.3),
            foreground_color=(0.9, 0.95, 1.0, 1), cursor_color=(0.0, 0.9, 1.0, 1),
            font_size=dp(11)
        )
        card1.add_widget(self.ip_input)
        root.add_widget(card1)

        # 模块 2：扫描配置与操作按钮
        card2 = CardBox((0.08, 0.10, 0.15, 1), (0.0, 0.9, 1.0, 1), orientation='vertical', padding=dp(8), spacing=dp(4), size_hint_y=0.28)
        card2.add_widget(Label(text="[2] \u626b\u63cf\u53c2\u6570\u8bbe\u7f6e", font_size=dp(11), color=(0.7, 0.85, 1.0, 1), size_hint_y=None, height=dp(18), bold=True))

        form_grid = GridLayout(cols=2, spacing=dp(6), size_hint_y=None, height=dp(45))
        
        p_box = BoxLayout(orientation='vertical', spacing=dp(1))
        p_box.add_widget(Label(text="\u7aef\u53e3\u7b5b\u9009 (\u9017\u53f7\u5206\u9694)", font_size=dp(9), color=(0.6, 0.7, 0.8, 1)))
        self.port_input = TextInput(text="443,2053,8443", multiline=False, font_size=dp(10), background_color=(0,0,0,0.3), foreground_color=(0.9,0.95,1.0,1))
        p_box.add_widget(self.port_input)
        form_grid.add_widget(p_box)

        t_box = BoxLayout(orientation='vertical', spacing=dp(1))
        t_box.add_widget(Label(text="\u8d85\u65f6\u9650\u5236 (\u79d2)", font_size=dp(9), color=(0.6, 0.7, 0.8, 1)))
        self.timeout_input = TextInput(text="2.0", multiline=False, font_size=dp(10), background_color=(0,0,0,0.3), foreground_color=(0.9,0.95,1.0,1))
        t_box.add_widget(self.timeout_input)
        form_grid.add_widget(t_box)

        card2.add_widget(form_grid)

        action_box = BoxLayout(orientation='horizontal', spacing=dp(8), size_hint_y=None, height=dp(36))
        
        self.scan_btn = Button(
            text="\u5f00\u59cb\u626b\u63cf", bold=True, font_size=dp(12),
            background_normal='', background_color=(0.0, 0.9, 1.0, 1), color=(0,0,0,1)
        )
        self.scan_btn.bind(on_press=self.toggle_scan)
        action_box.add_widget(self.scan_btn)

        self.copy_btn = Button(
            text="\u4e00\u952e\u590d\u5236\u53ef\u7528IP", bold=True, font_size=dp(12),
            background_normal='', background_color=(0.0, 1.0, 0.5, 1), color=(0,0,0,1)
        )
        self.copy_btn.bind(on_press=self.copy_ips)
        action_box.add_widget(self.copy_btn)

        card2.add_widget(action_box)
        root.add_widget(card2)

        # 状态栏
        self.status_lbl = Label(text="\u72b6\u6001: \u5c31\u7eea\uff0c\u7b49\u5f85\u6307\u4ee4", size_hint_y=None, height=dp(20), font_size=dp(10), color=(0.0, 0.9, 1.0, 1))
        root.add_widget(self.status_lbl)

        # 模块 3：可用 IP 实时展示终端
        card3 = CardBox((0.08, 0.10, 0.15, 1), (0.0, 1.0, 0.5, 1), orientation='vertical', padding=dp(8), spacing=dp(4), size_hint_y=0.36)
        card3.add_widget(Label(text="[3] \u53ef\u7528\u8282\u70b9\u5b9e\u65f6\u7ec8\u7aef", font_size=dp(11), color=(0.7, 1.0, 0.8, 1), size_hint_y=None, height=dp(18), bold=True))

        self.result_box = TextInput(
            text="", readonly=True, multiline=True,
            hint_text="\u5305\u542b\u771f\u5b9e TLS \u63e1\u624b\u5ef6\u8fdf\u3001\u5730\u533a\u53ca\u6d4b\u901f\u7ed5\u679c\u5c06\u5728\u6b64\u5b9e\u65f6\u8f93\u51fa...",
            background_normal='', background_color=(0,0,0,0.3),
            foreground_color=(0.0, 1.0, 0.5, 1), font_size=dp(10)
        )
        card3.add_widget(self.result_box)
        root.add_widget(card3)

        return root

    def expand_ips(self, raw_text):
        lines = re.split(r'[\r\n,\s]+', str(raw_text).strip())
        ports = [int(p.strip()) for p in self.port_input.text.split(',') if p.strip().isdigit()]
        if not ports: ports = [443]
        
        seen = set()
        targets = []

        for line in lines:
            item = line.strip()
            if not item: continue

            if '/' in item:
                try:
                    ip, mask = item.split('/')
                    mask = int(mask)
                    if mask < 16: mask = 20
                    parts = [int(p) for p in ip.split('.')]
                    ip_num = (parts[0] << 24) + (parts[1] << 16) + (parts[2] << 8) + parts[3]
                    num_hosts = 1 << (32 - mask)
                    
                    sample_count = min(num_hosts, 35)
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
        try:
            ip, port = ip_port.split(":")
            port = int(port)
            timeout = float(self.timeout_input.text or 2.0)

            # 1. 真实 TLS 握手
            t0 = time.time()
            sock = socket.create_connection((ip, port), timeout=timeout)
            tls_sock = SSL_CTX.wrap_socket(sock, server_hostname=ip)
            tls_delay = round((time.time() - t0) * 1000, 1)
            tls_sock.close()

            # 2. 地区识别
            url = f"https://check.proxyip.cmliussss.net/check?proxyip={ip_port}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if not data.get("success"): return None
                colo = data.get("colo", "OTHER").upper()
                region = CF_COLO.get(colo, colo)

            # 3. 真实测速
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
        self.scan_btn.text = "\u626b\u63cf\u4e2d..."
        self.result_box.text = ""
        self.valid_ips = []
        threading.Thread(target=self.run_scan_task, daemon=True).start()

    def run_scan_task(self):
        targets = self.expand_ips(self.ip_input.text)
        if not targets:
            Clock.schedule_once(lambda dt: self.finish_scan("\u672a\u627e\u5230\u6709\u6548\u76ee\u6807 IP\uff01", False))
            return

        results = []
        total = len(targets)

        for i, target in enumerate(targets, 1):
            Clock.schedule_once(lambda dt, idx=i, t=total: setattr(self.status_lbl, 'text', f"\u6b63\u5728\u626b\u63cf: \u8fdb\u5ea6 ({idx}/{t})"))
            res = self.test_node(target)
            if res:
                results.append(res)
                line = f"[\u221a] {res['ip']} | {res['region']} | \u5ef6\u8fdf:{res['tls']}ms | {res['speed']}KB/s\n"
                Clock.schedule_once(lambda dt, l=line: self.append_log(l))

        results.sort(key=lambda x: x["tls"])
        self.valid_ips = [r["ip"] for r in results]
        
        msg = f"\u626b\u63cf\u5b8c\u6210\uff01\u5171\u627e\u5230 {len(self.valid_ips)} \u4e2a\u53ef\u7528\u8282\u70b9"
        Clock.schedule_once(lambda dt: self.finish_scan(msg, False))

    def append_log(self, line):
        self.result_box.text += line

    def finish_scan(self, msg, status):
        self.status_lbl.text = f"\u72b6\u6001: {msg}"
        self.scan_btn.disabled = False
        self.scan_btn.text = "\u5f00\u59cb\u626b\u63cf"
        self.is_running = status

    def copy_ips(self, instance):
        if self.valid_ips:
            Clipboard.copy("\n".join(self.valid_ips))
            self.status_lbl.text = "\u72b6\u6001: \u5df2\u6210\u529f\u5c06\u53ef\u7528 IP \u590d\u5236\u5230\u526a\u8d34\u677f\uff01"
        else:
            self.status_lbl.text = "\u72b6\u6001: \u5f53\u524d\u6ca1\u6709\u53ef\u7528 IP \u53ef\u4f9b\u590d\u5236"


if __name__ == "__main__":
    SafeUnicodeApp().run()
