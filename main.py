import customtkinter as ctk
import ctypes

# 모듈 임포트
from config_manager import ConfigManager
from ui_components.main_ui import MainUI

# 윈도우 DPI 설정 (글자 흐림 방지)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    # 1. 설정 매니저 생성
    config_manager = ConfigManager()

    # 2. UI 실행 (config_manager 전달)
    app = MainUI(config_manager)
    app.mainloop()