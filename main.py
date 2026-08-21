import os
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
from kivy.graphics import Color, Rectangle, Line
from kivy.metrics import dp
from kivy.core.text import LabelBase

# -------------------------------------------------------------------
# iOS 系统中文字体加载（彻底解决 □□□ 方块乱码）
# -------------------------------------------------------------------
FONT_PATH = "/System/Library/Fonts/Language-Support/PingFang.ttc"
CYBER_FONT = "Roboto"  # 回退默认字体

if os.path.exists(FONT_PATH):
    LabelBase.register(name="PingFang", fn_regular=FONT_PATH)
    CYBER_FONT = "PingFang"

# 机房代码转中文地区
CF_COLO = {
    "HKG": "中国·香港", "TPE": "中国·台湾", "KHH": "中国·高雄",
    "NRT": "日本·东京", "KIX": "日本·大阪", "ICN": "韩国·首尔",
    "SIN": "新加坡", "BKK": "泰国·曼谷", "KUL": "马来西亚·吉隆坡",
    "SJC": "美国·圣何塞", "LAX": "美国·洛杉矶", "SEA": "美国·西雅图",
    "FRA": "德国·法兰克福", "LHR": "英国·伦敦", "CDG": "法国·巴黎"
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# 赛博朋克配色方案
BG_COLOR = (0.04, 0.04, 0.07, 1)        # 暗黑底色
CARD_COLOR = (0.08, 0.10, 0.15, 1)      # 输入框背景
CYAN_COLOR = (0.0, 0.9, 0.9, 1)        # 霓虹青蓝 (主色)
GREEN_COLOR = (0.0, 1.0, 0.5, 1)       # 荧光绿 (高亮/成功)
TEXT_COLOR = (0.85, 0.92, 1.0, 1)      # 荧光灰白文字


class CyberApp(App):
    def build(self):
        self.title = "PROXY SCANNER"
        self.valid_ips = []

        # 根布局：深色背景 + dp 单位自适应
        root = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))
        with root.canvas.before:
            Color(*BG_COLOR)
            self.bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda obj, val: setattr(self.bg_rect, 'pos', val),
                  size=lambda obj, val: setattr(self.bg_rect, 'size', val))

        # 1. 赛博风格标题
        title = Label(
            text="⚡ PROXY // 节点扫描器 ⚡",
            font_name=CYBER_FONT,
            size_hint_y=None,
            height=dp(35),
            font_size=dp(18),
            bold=True,
            color=CYAN_COLOR
        )
        root.add_widget(title)

        # 2. 自定义 IP 输入框
        self.input_text = TextInput(
            text="103.21.244.13\n173.245.60.252:443\n188.114.106.185:2053",
            hint_text="粘贴自定义 IP 列表（每行一个，自动补齐 :443）",
            font_name=CYBER_FONT,
            multiline=True,
            size_hint_y=0.28,
            background_normal='',
            background_color=CARD_COLOR,
            foreground_color=TEXT_COLOR,
            cursor_color=CYAN_COLOR,
            font_size=dp(13)
        )
        root.add_widget(self.input_text)

        # 3. 霓虹按钮区
        btn_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(45), spacing=dp(10))
        
        self.scan_btn = Button(
            text="▶ 开始扫描",
            font_name=CYBER_FONT,
            bold=True,
            font_size=dp(14),
            background_normal='',
            background_color=CYAN_COLOR,
            color=(0, 0, 0, 1)
        )
        self.scan_btn.bind(on_press=self.start_scan)
        btn_box.add_widget(self.scan_btn)

        self.copy_btn = Button(
            text="📋 一键复制 IP",
            font_name=CYBER_FONT,
            bold=True,
            font_size=dp(14),
            background_normal='',
            background_color=GREEN_COLOR,
            color=(0, 0, 0, 1)
        )
        self.copy_btn.bind(on_press=self.copy_results)
        btn_box.add_widget(self.copy_btn)

        root.add_widget(btn_box)

        # 4. 终端状态栏
        self.status_label = Label(
            text="系统状态: 准备就绪",
            font_name=CYBER_FONT,
            size_hint_y=None,
            height=dp(25),
            font_size=dp(12),
            color=CYAN_COLOR
        )
        root.add_widget(self.status_label)

        # 5. 检测日志结果显示框
        self.result_text = TextInput(
            text="",
            font_name=CYBER_FONT,
            readonly=True,
            multiline=True,
            hint_text="[日志终端] 等待扫描任务发起...",
            background_normal='',
            background_color=CARD_COLOR,
            foreground_color=GREEN_COLOR,
            font_size=dp(12)
        )
        root.add_widget(self.result_text)

        return root

    def parse_region(self, colo):
        if not colo: return "其它地区"
        code = str(colo).strip().upper()
        return CF_COLO.get(code, f"其它地区({code})")

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
        self.status_label.text = "系统状态: 深度扫描中..."
        self.result_text.text = ""
        self.valid_ips = []
        threading.Thread(target=self._async_scan, daemon=True).start()

    def _async_scan(self):
        targets = self.parse_ips(self.input_text.text)
        if not targets:
            Clock.schedule_once(lambda dt: self._update_status("未识别到可用的 IP！", False))
            return

        results = []
        total = len(targets)

        for idx, ip in enumerate(targets, 1):
            Clock.schedule_once(lambda dt, i=idx, t=total: self._update_status(f"正在扫描 ({i}/{t})...", True))
            res = self.check_one_ip(ip)
            if res:
                results.append(res)
                log_line = f"✔ {res['ip']:<20} | {res['region']} | 延迟:{res['latency']}ms | 速度:{res['speed']}KB/s\n"
                Clock.schedule_once(lambda dt, line=log_line: self._append_result(line))

        results.sort(key=lambda x: x["latency"])
        self.valid_ips = [r["ip"] for r in results]

        final_msg = f"扫描完成！找到 {len(self.valid_ips)} 个有效节点"
        Clock.schedule_once(lambda dt: self._update_status(final_msg, False))

    def _update_status(self, text, is_scanning):
        self.status_label.text = f"系统状态: {text}"
        if not is_scanning:
            self.scan_btn.disabled = False

    def _append_result(self, line):
        self.result_text.text += line

    def copy_results(self, instance):
        if self.valid_ips:
            text_to_copy = "\n".join(self.valid_ips)
            Clipboard.copy(text_to_copy)
            self.status_label.text = "系统状态: 已成功复制有效 IP 到剪贴板！"
        else:
            self.status_label.text = "系统状态: 暂无可用 IP"

if __name__ == "__main__":
    CyberApp().run()
