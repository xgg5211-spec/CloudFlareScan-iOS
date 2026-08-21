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
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp

# ==========================================
# 1. 🎲 随机 UI 主题配色方案 (RGB 0-1)
# ==========================================
THEMES = [
    # 01. Cyberpunk Neon (赛博霓虹)
    {
        "name": "NEON CYBER",
        "bg": (0.04, 0.04, 0.07, 1),
        "card": (0.08, 0.10, 0.15, 1),
        "main": (0.0, 0.9, 0.9, 1),       # Cyan
        "accent": (0.0, 1.0, 0.5, 1),     # Green
        "text": (0.85, 0.92, 1.0, 1)
    },
    # 02. Hacker Matrix (黑客帝国)
    {
        "name": "MATRIX TERMINAL",
        "bg": (0.02, 0.05, 0.02, 1),
        "card": (0.05, 0.12, 0.05, 1),
        "main": (0.2, 1.0, 0.2, 1),       # Matrix Green
        "accent": (0.8, 1.0, 0.0, 1),     # Lime
        "text": (0.7, 1.0, 0.7, 1)
    },
    # 03. Vaporwave Sunset (日落蒸汽波)
    {
        "name": "SUNSET DRIFT",
        "bg": (0.08, 0.04, 0.09, 1),
        "card": (0.15, 0.08, 0.18, 1),
        "main": (1.0, 0.2, 0.6, 1),       # Magenta
        "accent": (0.4, 0.8, 1.0, 1),     # Sky Blue
        "text": (1.0, 0.85, 0.95, 1)
    },
    # 04. Minimalist Mono (极简暗黑)
    {
        "name": "MONO DARK",
        "bg": (0.08, 0.08, 0.08, 1),
        "card": (0.14, 0.14, 0.14, 1),
        "main": (0.9, 0.9, 0.9, 1),       # White/Grey
        "accent": (1.0, 0.6, 0.0, 1),     # Amber
        "text": (0.9, 0.9, 0.9, 1)
    }
]

# 地区缩写表
CF_COLO = {
    "HKG": "HK", "TPE": "TW", "KHH": "TW", "NRT": "JP", "KIX": "JP", 
    "ICN": "KR", "SIN": "SG", "BKK": "TH", "KUL": "MY", "SJC": "US", 
    "LAX": "US", "SEA": "US", "FRA": "DE", "LHR": "UK", "CDG": "FR"
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


class CyberApp(App):
    def build(self):
        # 随机抽取当前套主题
        self.theme = random.choice(THEMES)
        self.title = f"PROXY SCANNER [{self.theme['name']}]"
        self.valid_ips = []

        root = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))
        
        # 应用动态随机背景
        with root.canvas.before:
            Color(*self.theme['bg'])
            self.bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda obj, val: setattr(self.bg_rect, 'pos', val),
                  size=lambda obj, val: setattr(self.bg_rect, 'size', val))

        # 1. 顶部标题栏
        title = Label(
            text=f"> {self.theme['name']} // ENGINE <",
            size_hint_y=None,
            height=dp(35),
            font_size=dp(16),
            bold=True,
            color=self.theme['main']
        )
        root.add_widget(title)

        # 2. IP 输入文本框（支持单个 IP、IP:PORT、CIDR 掩码段）
        self.input_text = TextInput(
            text="103.21.244.13\n173.245.60.252:443\n188.114.106.185:2053\n104.16.0.0/24",
            hint_text="PASTE IPS / CIDR (e.g. 104.16.0.0/24)...",
            multiline=True,
            size_hint_y=0.28,
            background_normal='',
            background_color=self.theme['card'],
            foreground_color=self.theme['text'],
            cursor_color=self.theme['main'],
            font_size=dp(12)
        )
        root.add_widget(self.input_text)

        # 3. 操作按钮区
        btn_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(42), spacing=dp(10))
        
        self.scan_btn = Button(
            text="START SCAN",
            bold=True,
            font_size=dp(13),
            background_normal='',
            background_color=self.theme['main'],
            color=(0, 0, 0, 1)
        )
        self.scan_btn.bind(on_press=self.start_scan)
        btn_box.add_widget(self.scan_btn)

        self.copy_btn = Button(
            text="COPY VALID",
            bold=True,
            font_size=dp(13),
            background_normal='',
            background_color=self.theme['accent'],
            color=(0, 0, 0, 1)
        )
        self.copy_btn.bind(on_press=self.copy_results)
        btn_box.add_widget(self.copy_btn)

        root.add_widget(btn_box)

        # 4. 状态栏
        self.status_label = Label(
            text="SYSTEM READY",
            size_hint_y=None,
            height=dp(25),
            font_size=dp(12),
            color=self.theme['main']
        )
        root.add_widget(self.status_label)

        # 5. 日志与结果面板
        self.result_text = TextInput(
            text="",
            readonly=True,
            multiline=True,
            hint_text="RESULTS TERMINAL READY...",
            background_normal='',
            background_color=self.theme['card'],
            foreground_color=self.theme['accent'],
            font_size=dp(11)
        )
        root.add_widget(self.result_text)

        return root

    def parse_region(self, colo):
        if not colo: return "OTHER"
        code = str(colo).strip().upper()
        return CF_COLO.get(code, code)

    def expand_cidr(self, cidr_str):
        """支持 CIDR 段展开与随机抽样（防内存爆满卡顿）"""
        try:
            ip, mask = cidr_str.split('/')
            mask = int(mask)
            if mask < 16: mask = 20  # 限制最大网段，避免抽样过长
            
            parts = [int(p) for p in ip.split('.')]
            ip_num = (parts[0] << 24) + (parts[1] << 16) + (parts[2] << 8) + parts[3]
            num_hosts = 1 << (32 - mask)
            
            sampled_ips = []
            sample_count = min(num_hosts, 32) # 每个 CIDR 最多智能采样 32 个 IP 防卡顿
            step = max(1, num_hosts // sample_count)
            
            for i in range(1, num_hosts - 1, step):
                curr = ip_num + i
                ip_s = f"{(curr >> 24) & 255}.{(curr >> 16) & 255}.{(curr >> 8) & 255}.{curr & 255}"
                sampled_ips.append(f"{ip_s}:443")
            return sampled_ips
        except Exception:
            return []

    def parse_ips(self, raw_text):
        lines = re.split(r'[\r\n,\s]+', str(raw_text).strip())
        seen = set()
        ips = []
        for line in lines:
            item = line.strip()
            if not item: continue
            
            # 处理 CIDR 网段
            if '/' in item:
                expanded = self.expand_cidr(item)
                for exp_ip in expanded:
                    if exp_ip not in seen:
                        seen.add(exp_ip)
                        ips.append(exp_ip)
                continue

            # 自动补齐 443 端口
            if ":" not in item:
                item = f"{item}:443"
                
            if item not in seen:
                seen.add(item)
                ips.append(item)
        return ips

    def measure_tls_handshake(self, ip, port):
        """底层 TLS 1.3 真实握手时延测试"""
        try:
            t0 = time.time()
            sock = socket.create_connection((ip, port), timeout=1.8)
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            tls_sock = context.wrap_socket(sock, server_hostname=ip)
            tls_delay = round((time.time() - t0) * 1000, 1)
            tls_sock.close()
            return tls_delay
        except Exception:
            return None

    def test_speed(self, ip_port):
        """真实 HTTP 数据包下载测速"""
        try:
            proxy_h = urllib.request.ProxyHandler({'http': f'http://{ip_port}', 'https': f'http://{ip_port}'})
            opener = urllib.request.build_opener(proxy_h)
            s_req = urllib.request.Request("https://speed.cloudflare.com/__down?bytes=102400", headers={'User-Agent': 'Mozilla/5.0'})
            st = time.time()
            with opener.open(s_req, timeout=2.0) as s_resp:
                buf = s_resp.read()
                dur = time.time() - st
                if dur > 0 and len(buf) > 0:
                    return round((len(buf) / 1024) / dur, 1)
        except Exception:
            pass
        return 0.0

    def check_one_ip(self, ip_port):
        """综合探针检测（TLS 握手 + 地区 + 运营商 + 真实速度）"""
        try:
            ip, port = ip_port.split(":")
            port = int(port)

            # 1. 先进行真实 TLS 握手测试
            tls_delay = self.measure_tls_handshake(ip, port)
            if not tls_delay:
                return None

            # 2. HTTP 探针验证 + ISP 识别
            url = f"https://check.proxyip.cmliussss.net/check?proxyip={ip_port}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=2.5, context=SSL_CTX) as resp:
                if resp.status != 200: return None
                data = json.loads(resp.read().decode('utf-8'))
                if not data.get("success"): return None
                
                region = self.parse_region(data.get("colo", ""))
                isp = data.get("asOrganization", "Cloudflare")[:10]  # 提取运营商组织简称
                
                # 3. 真实速度
                speed = self.test_speed(ip_port)

                return {
                    "ip": ip_port,
                    "region": region,
                    "isp": isp,
                    "tls": tls_delay,
                    "speed": speed
                }
        except Exception:
            return None

    def start_scan(self, instance):
        self.scan_btn.disabled = True
        self.status_label.text = "STATUS: SCANNING..."
        self.result_text.text = ""
        self.valid_ips = []
        threading.Thread(target=self._async_scan, daemon=True).start()

    def _async_scan(self):
        targets = self.parse_ips(self.input_text.text)
        if not targets:
            Clock.schedule_once(lambda dt: self._update_status("NO IP DETECTED!", False))
            return

        results = []
        total = len(targets)

        for idx, ip in enumerate(targets, 1):
            Clock.schedule_once(lambda dt, i=idx, t=total: self._update_status(f"SCANNING ({i}/{t})...", True))
            res = self.check_one_ip(ip)
            if res:
                results.append(res)
                log_line = f"[+] {res['ip']:<19} | {res['region']:<4} | {res['isp']:<10} | TLS:{res['tls']}ms | {res['speed']}KB/s\n"
                Clock.schedule_once(lambda dt, line=log_line: self._append_result(line))

        # 按 TLS 延迟升序排序
        results.sort(key=lambda x: x["tls"])
        self.valid_ips = [r["ip"] for r in results]

        final_msg = f"SCAN DONE: {len(self.valid_ips)} ONLINE"
        Clock.schedule_once(lambda dt: self._update_status(final_msg, False))

    def _update_status(self, text, is_scanning):
        self.status_label.text = f"STATUS: {text}"
        if not is_scanning:
            self.scan_btn.disabled = False

    def _append_result(self, line):
        self.result_text.text += line

    def copy_results(self, instance):
        if self.valid_ips:
            text_to_copy = "\n".join(self.valid_ips)
            Clipboard.copy(text_to_copy)
            self.status_label.text = "COPIED TO CLIPBOARD!"
        else:
            self.status_label.text = "NO VALID IP TO COPY"

if __name__ == "__main__":
    CyberApp().run()
