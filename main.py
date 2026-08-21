from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
import threading

# 这是一个纯中文的、极简的、绝对不会闪退的版本
class MySimpleApp(App):
    def build(self):
        # 布局
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)

        # 标题
        layout.add_widget(Label(text="优选 IP 扫描器", font_size=20))

        # 输入框
        self.input = TextInput(text="104.16.0.0/24", multiline=False)
        layout.add_widget(self.input)

        # 按钮
        self.btn = Button(text="开始扫描", size_hint_y=None, height=50)
        self.btn.bind(on_press=self.start_scan)
        layout.add_widget(self.btn)

        # 结果区
        self.result = TextInput(text="等待开始...", readonly=True)
        layout.add_widget(self.result)

        return layout

    def start_scan(self, instance):
        self.btn.disabled = True
        self.result.text = "正在扫描，请稍候..."
        # 开启后台线程，防止界面卡死
        threading.Thread(target=self.run_task).start()

    def run_task(self):
        # 这里是你的逻辑，界面上只显示中文
        import time
        time.sleep(1)
        Clock.schedule_once(self.on_complete)

    def on_complete(self, dt):
        self.result.text = "扫描完成，结果已找到。"
        self.btn.disabled = False

if __name__ == "__main__":
    MySimpleApp().run()
