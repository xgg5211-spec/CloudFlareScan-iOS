import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.core.text import LabelBase

# 强制调用 iOS 系统自带的苹方字体，无需任何额外文件，完美支持中文且不乱码
def setup_font():
    pingfang_path = "/System/Library/Fonts/PingFang.ttc"
    if os.path.exists(pingfang_path):
        LabelBase.register(name="Chinese", fn_regular=pingfang_path)
    else:
        # 如果找不到系统路径，才回退到默认（极少数老版本 iOS）
        LabelBase.register(name="Chinese", fn_regular="Roboto")

setup_font()

class ChineseApp(App):
    def build(self):
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        
        # 现在所有标签都使用 "Chinese" 这个字体名，它会调用系统的苹方
        layout.add_widget(Label(text="优选 IP 扫描器", font_name="Chinese"))
        
        self.ip_input = TextInput(text="104.16.0.0/24", font_name="Chinese")
        layout.add_widget(self.ip_input)
        
        btn = Button(text="开始扫描", font_name="Chinese")
        layout.add_widget(btn)
        
        self.status = Label(text="准备就绪", font_name="Chinese")
        layout.add_widget(self.status)
        
        return layout

if __name__ == "__main__":
    ChineseApp().run()
