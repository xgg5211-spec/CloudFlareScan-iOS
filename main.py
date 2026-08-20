# -*- coding: utf-8 -*-
import os
import sys
import time
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard

class CloudFlareScaniOSApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stop_event = threading.Event()
        self.logs = []
        self.results = []
        self.current_tab = "log"

    def build(self):
        self.title = "CloudFlare Scan"

        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=6)

        # 1. 顶部标题
        title_lbl = Label(
            text="CloudFlare Scan (iOS)",
            font_size=22,
            bold=True,
            size_hint_y=0.08,
            color=(1, 0.4, 0, 1)
        )
        main_layout.add_widget(title_lbl)

        # 2. 功能按钮区
        grid_btns1 = GridLayout(cols=3, spacing=6, size_hint_y=0.08)
        self.btn_v4 = Button(text="IPv4 扫描", background_color=(0.2, 0.5, 1, 1), on_press=lambda x: self.start_scan("v4"))
        self.btn_v6 = Button(text="IPv6 扫描", background_color=(0.2, 0.8, 0.4, 1), on_press=lambda x: self.start_scan("v6"))
        self.btn_stop = Button(text="停止任务", background_color=(0.8, 0.8, 0.8, 1), disabled=True, on_press=self.stop_scan)
        
        grid_btns1.add_widget(self.btn_v4)
        grid_btns1.add_widget(self.btn_v6)
        grid_btns1.add_widget(self.btn_stop)
        main_layout.add_widget(grid_btns1)

        grid_btns2 = GridLayout(cols=3, spacing=6, size_hint_y=0.08)
        self.btn_region = Button(text="地区测速", background_color=(0.9, 0.3, 0.6, 1))
        self.btn_full = Button(text="完全测速", background_color=(1, 0.5, 0, 1))
        self.btn_export = Button(text="复制结果", background_color=(0.7, 0.7, 0.7, 1), on_press=self.export_results)
        
        grid_btns2.add_widget(self.btn_region)
        grid_btns2.add_widget(self.btn_full)
        grid_btns2.add_widget(self.btn_export)
        main_layout.add_widget(grid_btns2)

        # 3. 参数配置区
        param_grid = GridLayout(cols=3, spacing=6, size_hint_y=0.14)
        self.input_region = TextInput(hint_text="地区码", multiline=False)
        self.input_count = TextInput(text="10", hint_text="测速数量", multiline=False, input_filter="int")
        self.input_port = TextInput(text="443", hint_text="端口", multiline=False, input_filter="int")
        self.input_threads = TextInput(text="15", hint_text="并发(<=20)", multiline=False, input_filter="int")
        self.input_max_latency = TextInput(text="300", hint_text="延迟上限ms", multiline=False, input_filter="int")
        dummy_label = Label(text="")

        param_grid.add_widget(self.input_region)
        param_grid.add_widget(self.input_count)
        param_grid.add_widget(self.input_port)
        param_grid.add_widget(self.input_threads)
        param_grid.add_widget(self.input_max_latency)
        param_grid.add_widget(dummy_label)
        main_layout.add_widget(param_grid)

        # 4. 状态栏
        status_box = BoxLayout(orientation='horizontal', size_hint_y=0.05)
        self.lbl_status = Label(text="就绪", size_hint_x=0.6, halign="left")
        self.lbl_speed = Label(text="速度: 0.0 IP/s", size_hint_x=0.4, halign="right")
        status_box.add_widget(self.lbl_status)
        status_box.add_widget(self.lbl_speed)
        main_layout.add_widget(status_box)

        # 5. 选项卡
        tab_box = BoxLayout(orientation='horizontal', size_hint_y=0.07, spacing=4)
        self.btn_tab_log = Button(text="扫描日志", on_press=lambda x: self.switch_tab("log"))
        self.btn_tab_result = Button(text="测速结果", on_press=lambda x: self.switch_tab("result"))
        tab_box.add_widget(self.btn_tab_log)
        tab_box.add_widget(self.btn_tab_result)
        main_layout.add_widget(tab_box)

        # 6. 主文本展示区
        self.text_display = TextInput(
            readonly=True,
            multiline=True,
            size_hint_y=0.50,
            background_color=(0.08, 0.12, 0.18, 1),
            foreground_color=(0.9, 0.9, 0.9, 1)
        )
        main_layout.add_widget(self.text_display)

        return main_layout

    def switch_tab(self, tab_name):
        self.current_tab = tab_name
        if tab_name == "log":
            self.text_display.text = "".join(self.logs[-100:])
        else:
            self.text_display.text = "IP 地址 | 端口 | 延迟\n" + "-"*35 + "\n" + "".join(self.results)

    def append_log(self, text):
        def _update(dt):
            formatted_text = f"{text}\n"
            self.logs.append(formatted_text)
            if self.current_tab == "log":
                self.text_display.text += formatted_text
        Clock.schedule_once(_update)

    def add_result(self, ip, port, latency):
        def _update(dt):
            res_line = f"{ip:<15} | {port:<5} | {latency}ms\n"
            self.results.append(res_line)
            if self.current_tab == "result":
                self.text_display.text += res_line
        Clock.schedule_once(_update)

    def start_scan(self, mode):
        self.stop_event.clear()
        self.logs.clear()
        self.results.clear()
        self.text_display.text = ""
        
        self.btn_v4.disabled = True
        self.btn_v6.disabled = True
        self.btn_stop.disabled = False
        self.lbl_status.text = f"扫描中 ({mode.upper()})..."

        threading.Thread(target=self._scan_worker, args=(mode,), daemon=True).start()

    def stop_scan(self, instance):
        self.stop_event.set()
        self.append_log("[!] 正在停止...")

    def _scan_worker(self, mode):
        try:
            port = int(self.input_port.text or 443)
            max_threads = max(1, min(int(self.input_threads.text or 15), 20))
            max_latency = int(self.input_max_latency.text or 300)

            test_ips = [f"104.16.{i}.{j}" for i in range(1, 3) for j in range(1, 15)]

            self.append_log(f"开始测试 {len(test_ips)} 个 IP，并发线程数: {max_threads}")

            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                for ip in test_ips:
                    if self.stop_event.is_set():
                        break
                    executor.submit(self._tcp_ping, ip, port, max_latency)
                    time.sleep(0.02)

        except Exception as e:
            self.append_log(f"[!] 异常: {e}")
        finally:
            Clock.schedule_once(self._reset_ui)

    def _tcp_ping(self, ip, port, max_latency):
        if self.stop_event.is_set():
            return
        
        s = None
        start = time.time()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(max_latency / 1000.0)
            s.connect((ip, port))
            latency = int((time.time() - start) * 1000)
            self.append_log(f"[+] {ip}:{port} - {latency}ms")
            self.add_result(ip, port, latency)
        except Exception:
            pass
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass

    def _reset_ui(self, dt):
        self.btn_v4.disabled = False
        self.btn_v6.disabled = False
        self.btn_stop.disabled = True
        self.lbl_status.text = "已完成"
        self.append_log(f"扫描结束，共获取 {len(self.results)} 个可用节点。")

    def export_results(self, instance):
        if not self.results:
            self.append_log("[!] 无结果")
            return
        
        content = "".join(self.results)
        try:
            Clipboard.copy(content)
            self.append_log("[✓] 结果已复制到剪贴板！")
        except Exception:
            self.append_log("[!] 剪贴板不可用")

if __name__ == "__main__":
    CloudFlareScaniOSApp().run()
