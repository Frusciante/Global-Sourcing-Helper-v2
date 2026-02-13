import customtkinter as ctk
import threading
import json
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from logic.utils import fetch_naver_exchange_rate

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
        cat = self.naver_map.get(self.combo.get(), "ALL")
        threading.Thread(target=self._fetch, args=(cat,), daemon=True).start()

    def _fetch(self, cat_code):
        driver = None
        try:
            url = f"https://search.shopping.naver.com/best/category/click?period=P1D"
            if cat_code != "ALL": url += f"&categoryCategoryId={cat_code}&categoryRootCategoryId={cat_code}"
            opts = Options()
            opts.add_argument("--headless=new")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            driver.get(url)
            driver.implicitly_wait(3)
            raw = driver.find_element(By.ID, "__NEXT_DATA__").get_attribute("innerHTML")
            data = json.loads(raw)
            prods = []
            for q in data['props']['pageProps']['dehydratedState']['queries']:
                if 'data' in q['state'] and 'products' in q['state']['data']:
                    prods = q['state']['data']['products']; break
            items = [p['productName'] for p in prods[:20] if p.get('productName')]
            self.after(0, lambda: self._update(True, items))
        except Exception as e:
            self.after(0, lambda: self._update(False, str(e)))
        finally:
            if driver: driver.quit()

    def _update(self, success, items):
        self.btn_ref.configure(state="normal")
        for w in self.scroll.winfo_children(): w.destroy()
        if not success:
            ctk.CTkLabel(self.scroll, text=f"오류: {items}", text_color="red").pack()
            return
        for idx, item in enumerate(items):
            ctk.CTkButton(self.scroll, text=f"{idx+1}. {item}", anchor="w", fg_color="transparent", 
                          command=lambda t=item: [self.clipboard_clear(), self.clipboard_append(t)]).pack(fill="x")