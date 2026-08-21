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

class ProxyScannerApp(App):
    def build(self):
        self.title = "Proxy IP 扫描器"
        self.valid_ips = []

        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # 标题
        layout.add_widget(Label(text="Proxy IP 校验与测速", size_hint_y=None, height=35, font_size=18, bold=True))

        # 自定义 IP 输入框
        self.input_text = TextInput(
            text="103.21.244.13\n173.245.60.252:443\n188.114.106.185:2053",
            hint_text="粘贴自定义 IP (每行一个，自动补齐 :443)",
            multiline=True,
            size_hint_y=0.25
        )
        layout.add_widget(self.input_text)

        # 操作按钮区
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=45, spacing=10)
        
        self.scan_btn = Button(text="开始检测", background_color=(0.2, 0.6, 1, 1))
        self.scan_btn.bind(on_press=self.start_scan)
        btn_layout.add_widget(self.scan_btn)

        self.copy_btn = Button(text="一键复制 IP", background_color=(0.2, 0.8, 0.2, 1))
        self.copy_btn.bind(on_press=self.copy_results)
        btn_layout.add_widget(self.copy_btn)

        layout.add_widget(btn_layout)

        # 状态指示
        self.status_label = Label(text="状态: 准备就绪", size_hint_y=None, height=30)
        layout.add_widget(self.status_label)

        # 结果输出框
        self.result_text = TextInput(
            text="",
            readonly=True,
            multiline=True,
            hint_text="检测结果将在此处显示..."
        )
        layout.add_widget(self.result_text)

        return layout

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
        self.status_label.text = "状态: 正在检测中..."
        self.result_text.text = ""
        self.valid_ips = []
        # 使用后台独立线程处理网络访问，防止主线程卡死黑屏
        threading.Thread(target=self._async_scan, daemon=True).start()

    def _async_scan(self):
        targets = self.parse_ips(self.input_text.text)
        if not targets:
            Clock.schedule_once(lambda dt: self._update_status("未识别到有效的 IP！", False))
            return

        results = []
        total = len(targets)

        for idx, ip in enumerate(targets, 1):
            Clock.schedule_once(lambda dt, i=idx, t=total: self._update_status(f"检测中 ({i}/{t})...", True))
            res = self.check_one_ip(ip)
            if res:
                results.append(res)
                log_line = f"✅ {res['ip']:<21} | {res['region']:<8} | {res['latency']}ms | {res['speed']}KB/s\n"
                Clock.schedule_once(lambda dt, line=log_line: self._append_result(line))

        results.sort(key=lambda x: x["latency"])
        self.valid_ips = [r["ip"] for r in results]

        final_msg = f"检测完成！找到 {len(self.valid_ips)} 个有效 IP"
        Clock.schedule_once(lambda dt: self._update_status(final_msg, False))

    def _update_status(self, text, is_scanning):
        self.status_label.text = f"状态: {text}"
        if not is_scanning:
            self.scan_btn.disabled = False

    def _append_result(self, line):
        self.result_text.text += line

    def copy_results(self, instance):
        if self.valid_ips:
            text_to_copy = "\n".join(self.valid_ips)
            Clipboard.copy(text_to_copy)
            self.status_label.text = "状态: 已成功复制有效 IP 到剪贴板！"
        else:
            self.status_label.text = "状态: 暂无有效 IP 可复制！"

if __name__ == "__main__":
    ProxyScannerApp().run()
