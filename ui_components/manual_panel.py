import customtkinter as ctk
import threading
import re
from logic.utils import fetch_naver_exchange_rate, fetch_naver_trend_keywords

class ManualControlPanel(ctk.CTkToplevel):
    def __init__(self, master, on_collect, on_stop):
        super().__init__(master)
        self.title("중국 수집 리모컨")
        self.geometry("400x750") # 계산기 공간을 위해 세로 길이 확장
        self.attributes('-topmost', True)
        self.protocol("WM_DELETE_WINDOW", on_stop)
        self.on_collect = on_collect
        
        # 환율 데이터 및 루프 방지 플래그
        self.current_rate = 200.0 # 기본값
        self._is_updating = False

        # 1. 제어 버튼 영역
        self.control_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.control_frame.pack(fill="x", padx=15, pady=10)
        self.btn_collect = ctk.CTkButton(self.control_frame, text="📸 현재 페이지 수집", height=60, 
                                         font=("bold", 18), fg_color="#2CC985", command=self.on_collect)
        self.btn_collect.pack(fill="x", pady=5)

        # 2. 실시간 양방향 환율 계산기 영역 (신규 추가)
        self.calc_frame = ctk.CTkFrame(self)
        self.calc_frame.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(self.calc_frame, text="💰 CNY ↔ KRW 실시간 계산기", font=("bold", 14), text_color="#3b8ed0").pack(pady=5)
        
        self.rate_label = ctk.CTkLabel(self.calc_frame, text="환율 로딩 중...", font=("Arial", 11))
        self.rate_label.pack()

        # 위안화 입력창
        self.cny_var = ctk.StringVar()
        self.cny_var.trace_add("write", self._convert_cny_to_krw)
        self.entry_cny = ctk.CTkEntry(self.calc_frame, textvariable=self.cny_var, placeholder_text="위안화 (￥) 입력")
        self.entry_cny.pack(padx=20, pady=5, fill="x")

        ctk.CTkLabel(self.calc_frame, text="↕").pack()

        # 원화 입력창
        self.krw_var = ctk.StringVar()
        self.krw_var.trace_add("write", self._convert_krw_to_cny)
        self.entry_krw = ctk.CTkEntry(self.calc_frame, textvariable=self.krw_var, placeholder_text="원화 (₩) 입력")
        self.entry_krw.pack(padx=20, pady=5, fill="x")

        # 3. 트렌드 영역 (기존 유지)
        self.trend_frame = ctk.CTkFrame(self)
        self.trend_frame.pack(fill="both", expand=True, padx=15, pady=10)
        ctk.CTkLabel(self.trend_frame, text="🔥 실시간 BEST (Selenium)", text_color="yellow").pack(anchor="w", padx=10, pady=5)

        filter_f = ctk.CTkFrame(self.trend_frame, fg_color="transparent")
        filter_f.pack(fill="x", padx=10)
        self.naver_map = {"전체": "ALL", "패션": "50000000", "디지털": "50000003", "생활": "50000008"}
        self.combo = ctk.CTkComboBox(filter_f, values=list(self.naver_map.keys()), state="readonly")
        self.combo.set("전체"); self.combo.pack(side="left")
        self.btn_ref = ctk.CTkButton(filter_f, text="🔄", width=40, command=self.refresh); self.btn_ref.pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(self.trend_frame)
        self.scroll.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 시작 시 환율 가져오기 및 트렌드 새로고침
        self._fetch_exchange_rate()
        self.refresh()

    # --- 환율 관련 로직 ---
    def _fetch_exchange_rate(self):
        """유틸리티 함수를 사용하여 리모컨 환율 조회 (스레드)"""
        def task():
            # 리모컨은 중국 전용이므로 CNY 고정 호출
            rate = fetch_naver_exchange_rate("CNY")
            self.current_rate = rate
            
            # UI 업데이트
            self.after(0, lambda: self.rate_label.configure(
                text=f"현재 환율: 1￥ = {rate:,.2f}원",
                text_color="#3b8ed0"
            ))
        
        threading.Thread(target=task, daemon=True).start()

    def _convert_cny_to_krw(self, *args):
        if self._is_updating: return
        try:
            val = re.sub(r'[^0-9.]', '', self.cny_var.get())
            if not val: self.krw_var.set(""); return
            self._is_updating = True
            res = float(val) * self.current_rate
            self.krw_var.set(f"{int(res)}")
        except: pass
        finally: self._is_updating = False

    def _convert_krw_to_cny(self, *args):
        if self._is_updating: return
        try:
            val = re.sub(r'[^0-9.]', '', self.krw_var.get())
            if not val: self.cny_var.set(""); return
            self._is_updating = True
            res = float(val) / self.current_rate
            self.cny_var.set(f"{res:.2f}")
        except: pass
        finally: self._is_updating = False

    # --- 기존 트렌드 로직 (수정 없음) ---
    def refresh(self):
        for w in self.scroll.winfo_children(): w.destroy()
        ctk.CTkLabel(self.scroll, text="로딩 중...").pack()
        self.btn_ref.configure(state="disabled")
        cat_name = self.combo.get()
        cat_code = self.naver_map.get(cat_name, "50000008")
        
        # Selenium 드라이버 없이 requests 함수 호출
        threading.Thread(target=self._fetch_trend, args=(cat_code,), daemon=True).start()

    def _fetch_trend(self, cat_code):
        try:
            # utils.py에 추가한 함수 호출
            keywords = fetch_naver_trend_keywords(cat_code)
            
            if keywords:
                self.after(0, lambda: self._update_ui(True, keywords))
            else:
                self.after(0, lambda: self._update_ui(False, "데이터를 불러오지 못했습니다."))
        except Exception as e:
            self.after(0, lambda: self._update_ui(False, str(e)))

    def _update_ui(self, success, items):
        """메인 스레드에서 UI 업데이트"""
        self.btn_ref.configure(state="normal")
        for w in self.scroll.winfo_children(): w.destroy()
        
        if not success:
            ctk.CTkLabel(self.scroll, text=f"⚠️ {items}", text_color="red").pack(pady=10)
            return
            
        for idx, item in enumerate(items):
            # 클릭 시 클립보드에 키워드가 복사되는 버튼 생성
            btn = ctk.CTkButton(
                self.scroll, 
                text=f"{idx+1:02d}. {item}", 
                anchor="w", 
                fg_color="transparent", 
                hover_color="#3b8ed0",
                command=lambda t=item: self._copy_to_clipboard(t)
            )
            btn.pack(fill="x", padx=5, pady=2)

    def _copy_to_clipboard(self, text):
        """키워드 복사 기능"""
        self.clipboard_clear()
        self.clipboard_append(text)
        # 선택 사항: 복사 완료 알림 처리 등