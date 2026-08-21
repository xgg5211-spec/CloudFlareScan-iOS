import json
import re
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

# 地区代码映射（纯英文缩写，防乱码）
CF_COLO = {
    "HKG": "HK", "TPE": "TW", "KHH": "TW",
    "NRT": "JP", "KIX": "JP", "ICN": "KR",
    "SIN": "SG", "BKK": "TH", "KUL": "MY",
    "SJC": "US", "LAX": "US", "SEA": "US",
    "FRA": "DE", "LHR": "UK", "CDG": "FR"
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# 赛博朋克深色调
BG_COLOR = (0.04, 0.04, 0.07, 1)        # 极深底色
CARD_COLOR = (0.08, 0.10, 0.15, 1)      # 卡片背景
CYAN_COLOR = (0.0, 0.9, 0.9, 1)        # 青色霓虹
GREEN_COLOR = (0.0, 1.0, 0.5, 1)       # 荧光绿
TEXT_COLOR = (0.85, 0.92, 1.0, 1)      # 文本颜色

class CyberApp(App):
    def build(self):
        self.title = "PROXY SCANNER"
        self.valid_ips = []

        root = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))
        with root.canvas.before:
            Color(*BG_COLOR)
            self.bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda obj, val: setattr(self.bg_rect, 'pos', val),
                  size=lambda obj, val: setattr(self.bg_rect, 'size', val))

        # 1. 标题栏
        title = Label(
            text="> PROXY // SCANNER <",
            size_hint_y=None,
            height=dp(35),
            font_size=dp(18),
            bold=True,
            color=CYAN_COLOR
        )
        root.add_widget(title)

        # 2. IP 输入框
        self.input_text = TextInput(
            text="103.21.244.13\n173.245.60.252:443\n188.114.106.185:2053",
            hint_text="PASTE IPS HERE (AUTO ADD :443)...",
            multiline=True,
            size_hint_y=0.28,
            background_normal='',
            background_color=CARD_COLOR,
            foreground_color=TEXT_COLOR,
            cursor_color=CYAN_COLOR,
            font_size=dp(13)
        )
        root.add_widget(self.input_text)

        # 3. 操作按钮
        btn_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(45), spacing=dp(10))
        
        self.scan_btn = Button(
            text="START SCAN",
            bold=True,
            font_size=dp(14),
            background_normal='',
            background_color=CYAN_COLOR,
            color=(0, 0, 0, 1)
        )
        self.scan_btn.bind(on_press=self.start_scan)
        btn_box.add_widget(self.scan_btn)

        self.copy_btn = Button(
            text="COPY IPS",
            bold=True,
            font_size=dp(14),
            background_normal='',
            background_color=GREEN_COLOR,
            color=(0, 0, 0, 1)
        )
        self.copy_btn.bind(on_press=self.copy_results)
        btn_box.add_widget(self.copy_btn)

        root.add_widget(btn_box)

        # 4. 状态栏
        self.status_label = Label(
            text="STATUS: STANDBY",
            size_hint_y=None,
            height=dp(25),
            font_size=dp(12),
            color=CYAN_COLOR
        )
        root.add_widget(self.status_label)

        # 5. 结果区域
        self.result_text = TextInput(
            text="",
            readonly=True,
            multiline=True,
            hint_text="WAITING FOR TASK...",
            background_normal='',
            background_color=CARD_COLOR,
            foreground_color=GREEN_COLOR,
            font_size=dp(12)
        )
        root.add_widget(self.result_text)

        return root

    def parse_region(self, colo):
        if not colo: return "OTHER"
        code = str(colo).strip().upper()
        return CF_COLO.get(code, code)

    def parse_ips(self, raw_text):
        lines = re.split(r'[\r\n,\s]+', str(raw_text).strip())
        seen = set()
        ips = []
        for line in lines:
            item = line.strip()
            if not item: continue
            if ":" not in item: item = f"{item}:443"
            if item not in seen:
                seen.add(item)
                ips.append(item)
        return ips

    def test_speed(self, ip_port):
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
        try:
            url = f"https://check.proxyip.cmliussss.net/check?proxyip={ip_port}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=2.5, context=SSL_CTX) as resp:
                if resp.status != 200: return None
                latency = round((time.time() - t0) * 1000, 1)
                data = json.loads(resp.read().decode('utf-8'))
                if not data.get("success"): return None
                region = self.parse_region(data.get("colo", ""))
                real_latency = data.get("responseTime", latency)
                speed = self.test_speed(ip_port)
                return {"ip": ip_port, "region": region, "latency": real_latency, "speed": speed}
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
            Clock.schedule_once(lambda dt: self._update_status("NO IP FOUND!", False))
            return

        results = []
        total = len(targets)

        for idx, ip in enumerate(targets, 1):
            Clock.schedule_once(lambda dt, i=idx, t=total: self._update_status(f"PROGRESS ({i}/{t})...", True))
            res = self.check_one_ip(ip)
            if res:
                results.append(res)
                log_line = f"[+] {res['ip']:<20} | {res['region']} | {res['latency']}ms | {res['speed']}KB/s\n"
                Clock.schedule_once(lambda dt, line=log_line: self._append_result(line))

        results.sort(key=lambda x: x["latency"])
        self.valid_ips = [r["ip"] for r in results]

        final_msg = f"DONE: FOUND {len(self.valid_ips)} ONLINE IPS"
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
            self.status_label.text = "STATUS: COPIED TO CLIPBOARD!"
        else:
            self.status_label.text = "STATUS: NO VALID IP"

if __name__ == "__main__":
    CyberApp().run()
