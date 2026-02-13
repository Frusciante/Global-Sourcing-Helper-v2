import time
import threading
import json
from urllib.parse import urljoin
import requests
import xml.etree.ElementTree as ET
import openai
from selenium.webdriver.common.by import By
import os
import re
from urllib.parse import urljoin

# [모듈 임포트]
from logic.browser_manager import BrowserManager
from logic.excel_handler import ExcelHandler
from ui_components.manual_panel import ManualControlPanel 
from logic.utils import fetch_naver_exchange_rate

class SourcingProcessor:
    def __init__(self, config, log_callback, app_root=None):
        self.config = config
        self.log_callback = log_callback
        self.app_root = app_root
        self.is_running = False
        self.current_search_kw = ""
        
        self.cache_file = "brand_cache.json"
        self.brand_cache = self._load_cache()
        
        # 1. 기본 매니저 초기화
        self.browser = BrowserManager(self.log_callback)
        excel_file = self.config.get('EXCEL_FILE', 'result.xlsx')
        self.excel_handler = ExcelHandler(excel_file, self.log_callback, self.config)
        self.panel = None 

        '''
        # 2. AI (Gemini) 설정 (기존 코드 복원)
        raw_keys = self.config.get('GEMINI_API_KEY', '')
        self.api_keys = [k.strip() for k in raw_keys.split(',') if k.strip()]
        self.current_key_idx = 0
        self.model_candidates = ["gemini-2.5-flash", "gemini-2.5-flash-lite"] # 모델 우선순위
        self.current_model_idx = 0
        self.client = None
        '''
        raw_keys = self.config.get('AI_API_KEY', '') # 설정 파일 키 이름 변경 권장
        self.api_keys = [k.strip() for k in raw_keys.split(',') if k.strip()]
        self.current_key_idx = 0
        self.model_candidates = [
            "llama-3.3-70b", 
            "qwen-3-32b", 
            "llama3.1-8b", 
            "gpt-oss-120b"
        ]
        self.current_model_idx = 0
        self.client = None
        
        # 3. KIPRIS (상표권) 설정 (기존 코드 복원)
        raw_kipris = self.config.get('KIPRIS_API_KEY', '')
        self.kipris_keys = [k.strip() for k in raw_kipris.split(',') if k.strip()]
        self.current_kipris_idx = 0

        # 초기 AI 설정
        try:
            self._configure_ai()
        except Exception as e:
            self.log_callback(f"⚠️ [Init] AI 초기화 실패 (키 확인 필요): {e}")
            
    def _update_realtime_exchange_rate(self, url):
        """유틸리티 함수를 사용하여 환율 업데이트"""
        if "rakuten" in url.lower(): target = "JPY"
        elif any(x in url.lower() for x in ['taobao', '1688', 'tmall']): target = "CNY"
        else: target = "USD"

        self.log_callback(f"🌐 [Exchange] {target} 환율 업데이트 중...")
        
        # 유틸리티 함수 호출
        self.current_rate = fetch_naver_exchange_rate(target)
        self.log_callback(f"🌐 [Exchange] {target} 환율 업데이트 완료: {self.current_rate}")
            

    def _load_cache(self):
        """파일(리스트)에서 블랙리스트를 읽어와 메모리(딕셔너리)에 로드"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    blacklist_list = json.load(f)
                    # 리스트 형태 ["BRAND1", "BRAND2"]를 
                    # { "BRAND1": False, "BRAND2": False } 형태로 변환하여 반환
                    return {brand: False for brand in blacklist_list}
            except Exception as e:
                self.log_callback(f"⚠️ [Cache] 로드 실패: {e}")
            return {}
        return {}
    
    def _save_cache(self):
        """중복을 원천 차단하며 블랙리스트 저장"""
        try:
            # 1. 딕셔너리에서 False인 브랜드만 추출
            # 2. set()으로 감싸서 혹시 모를 중복 제거
            # 3. 다시 list()로 변환하여 JSON 저장 가능하게 만듦
            blacklist_set = {k for k, v in self.brand_cache.items() if v is False}
        
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(list(blacklist_set), f, ensure_ascii=False, indent=4)
            
        except Exception as e:
            self.log_callback(f"⚠️ [Cache] 저장 실패: {e}")

    # ============================================================
    # [Core] AI & API 헬퍼 메서드 (기존 로직 유지)
    # ============================================================
    '''
    def _configure_genai(self):
        if not self.api_keys: return
        current_key = self.api_keys[self.current_key_idx]
        try:
            self.client = genai.Client(api_key=current_key)
        except Exception as e:
            self.client = None
            self.log_callback(f"❌ [AI] 설정 오류: {e}")
    '''
    
    def _configure_ai(self):
        """Cerebras API 클라이언트 설정 (OpenAI 호환)"""
        if not self.api_keys: return
        current_key = self.api_keys[self.current_key_idx]
        try:
            self.client = openai.OpenAI(
                base_url="https://api.cerebras.ai/v1",
                api_key=current_key
            )
        except Exception as e:
            self.client = None
            self.log_callback(f"❌ [AI] 설정 오류: {e}")
            
    def _rotate_api_key(self):
        if len(self.api_keys) <= 1: return False
        
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        self.log_callback(f"🔄 [AI] API 키 교체 ({self.current_key_idx + 1}/{len(self.api_keys)})")
        self._configure_ai()
        return True

    def _switch_model(self):
        if len(self.model_candidates) <= 1: return False
        self.current_model_idx = (self.current_model_idx + 1) % len(self.model_candidates)
        new_model = self.model_candidates[self.current_model_idx]
        self.log_callback(f"⚠️ [AI] 모델 변경 -> {new_model}")
        return True

    
    '''
    def _call_gemini_with_retry(self, prompt, context=""):
        """AI 호출 (재시도 및 키 로테이션 포함)"""
        max_attempts = len(self.api_keys) * len(self.model_candidates)
        if max_attempts == 0: max_attempts = 1
        
        for attempt in range(max_attempts):
            try:
                if not self.client: self._configure_genai()
                if not self.client: raise Exception("Client 없음")

                model_name = self.model_candidates[self.current_model_idx]
                response = self.client.models.generate_content(
                    model=model_name, contents=prompt
                )
                if response and response.text:
                    return response.text.replace('```json', '').replace('```', '').strip()
            
            except Exception as e:
                err_msg = str(e).lower()
                if "429" in err_msg or "quota" in err_msg:
                    self.log_callback(f"⏳ [AI] 할당량 초과 ({context}). 키 교체 중...")
                    if not self._rotate_api_key():
                        self._switch_model()
                    time.sleep(1)
                else:
                    self.log_callback(f"⚠️ [AI] 오류: {e}")
                    time.sleep(1)
        
        self.log_callback(f"❌ [AI] '{context}' 실패 (모든 키 소진)")
        return None
    '''    

    def _call_ai_with_retry(self, prompt, context=""):
        """
        Cerebras 최적화 호출 로직
        1순위: 모델 로테이션 (RPM 분산)
        2순위: API 키 로테이션
        3순위: 모든 자원 소진 시 60초 대기 후 최종 재시도 (Grand Cycle)
        """
        if not self.client: self._configure_ai()
        system_msg = "You are a professional e-commerce assistant. Provide direct answers. DO NOT include <think> tags or reasoning."
        if any(x in context for x in ["추출", "분석", "검증"]):
            system_msg += " Always output in valid JSON format ONLY."
        else:
            system_msg = "Output ONLY the translated string, no JSON, no brackets."

        max_grand_cycles = 2 # 전체 자원 순회 횟수 (대기 포함)
        
        for cycle in range(max_grand_cycles):
            # 현재 가용한 모든 '모델 x 키' 조합의 수만큼 반복 시도
            total_resource_count = len(self.api_keys) * len(self.model_candidates)
            
            for attempt in range(total_resource_count):
                current_model = self.model_candidates[self.current_model_idx]
                
                try:
                    time.sleep(3) 

                    response = self.client.chat.completions.create(
                        model=current_model,
                        messages=[
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.1
                    )
                    raw_text = response.choices[0].message.content.strip()

                    # ------------------------------------------------------
                    # [핵심] 생각 과정 및 불필요한 텍스트 제거 로직
                    # ------------------------------------------------------
                    # 1. <think> 태그와 그 내용 전체 삭제
                    clean_text = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()

                    # 2. JSON이 시작되는 '{'와 끝나는 '}'의 위치를 찾아서 슬라이싱
                    start_idx = clean_text.find('{')
                    end_idx = clean_text.rfind('}')

                    if start_idx != -1 and end_idx != -1:
                        # 순수 JSON 부분만 추출
                        final_res = clean_text[start_idx:end_idx + 1]
                    else:
                        # JSON 형태가 아예 없다면 번역 결과 등으로 판단하여 그대로 반환
                        final_res = clean_text

                    self.log_callback(f"🔍 [DEBUG AI Raw] {context} ({current_model}):\n{final_res}")
                    return final_res

                except Exception as e:
                    err_msg = str(e).lower()
                    
                    # 429(Rate Limit) 에러 발생 시
                    if "429" in err_msg or "rate_limit" in err_msg:
                        self.log_callback(f"⏳ [AI] {current_model} 한도 초과 ({context})")
                        
                        # 1단계: 다음 모델로 전환
                        self.current_model_idx += 1
                        
                        # 모든 모델을 다 써봤다면
                        if self.current_model_idx >= len(self.model_candidates):
                            self.current_model_idx = 0 # 모델 인덱스 초기화
                            
                            # 2단계: 다음 API 키로 전환
                            if not self._rotate_api_key():
                                # 더 이상 교체할 키가 없다면 이번 Cycle 중단
                                break 
                        continue # 다음 조합으로 즉시 재시도
                    
                    else:
                        self.log_callback(f"⚠️ [AI] 오류 발생 ({context}): {e}")
                        return None # 기타 치명적 오류는 즉시 반환

            # [3단계] 모든 키와 모델을 다 써봤는데도 실패한 경우 (Grand Cycle)
            if cycle < max_grand_cycles - 1:
                wait_time = 60
                self.log_callback(f"🛑 [AI] 모든 모델/키 자원 소진 ({context}). {wait_time}초 휴식 후 마지막 재시도...")
                time.sleep(wait_time)
            else:
                self.log_callback(f"❌ [AI] 모든 재시도 실패 ({context}). 작업을 중단합니다.")
        
        return None

    # ============================================================
    # [Logic] 분석 및 데이터 추출 (기존 로직 유지)
    # ============================================================
    def detect_and_translate(self, url, keyword):
        """쇼핑몰 URL에 맞춰 키워드 번역"""
        target_lang = None
        if any(x in url for x in ['taobao', '1688', 'tmall']): target_lang = "Simplified Chinese"
        elif any(x in url for x in ['amazon', 'ebay']): target_lang = "English"
        elif any(x in url for x in ['rakuten']): target_lang = "Japanese"
        
        if target_lang:
            prompt = f"Translate the term '{keyword}' to {target_lang}. Return ONLY the translated string."
            res = self._call_ai_with_retry(prompt, "번역")
            if res:
                cleaned = res.replace('"', '').replace("'", "").strip()
                self.log_callback(f"   ㄴ 🔤 번역: {keyword} -> {cleaned}")
                return cleaned
        return keyword

    def extract_full_info(self, title, context_text="", search_keyword=""):
        """상품 정보 추출 및 검색 의도 적합성 검증"""
        prompt = (
            f"Role: Professional E-commerce Localization Expert\n"
            f"Search Intent: Finding items related to '{search_keyword}'.\n"
            f"Original Title: '{title}'\n"
            f"Context: '{context_text[:1500]}'\n\n"
            
            f"### CRITICAL RULES ###\n"
            f"1. **NO USED ITEMS**: If the product is 'Used', 'Pre-owned', 'Refurbished', or contains '중고' / '中古', set 'is_valid' to false.\n"
            f"2. **REASONING**: If 'is_valid' is false due to being a used item, the 'reason' must be: '중고 상품이므로 적절한 소싱 대상이 아님'.\n"
            f"3. **TITLE LOCALIZATION**: Translate to natural Korean. Remove all Katakana and Hanja (e.g., 工具 -> 공구). Translate to a natural Korean SEO title. Focus on the specific product name and its key features (e.g., 'Pilot G2 Retractable Gel Pen' -> '파이롯트 G2 노크식 젤펜'). Avoid generic terms like 'Stationery' if a specific name exists.\n"
            f"4. **CATEGORY CANDIDATES**: Extract 3 specific Korean product type nouns (e.g., ['라쳇', '압착기', '렌치']).\n"
            f"5. **MANUFACTURER & BRAND**: Keep the original source text as it appears. **DO NOT TRANSLATE**.\n"

            f"Output JSON format:\n"
            f"{{\n"
            f"  \"is_valid\": true/false,\n"
            f"  \"reason\": \"...\",\n"
            f"  \"productTitle\": \"자연스러운 한국어 SEO 상품명\",\n"
            f"  \"manufacturer\": \"...\",\n"
            f"  \"brand\": \"...\",\n"
            f"  \"model\": \"...\",\n"
            f"  \"keywords\": [\"태그1\", \"태그2\"]\n"
            f"  \"category_candidates\": [\"후보1\", \"후보2\", \"후보3\"]\n"
            f"}}"
        )
        res = self._call_ai_with_retry(prompt, "정보 추출 및 검증")
        if res:
            try:
                # 불필요한 마크다운 코드 블록(```json) 제거 후 로드
                clean_json = res.replace('```json', '').replace('```', '').strip()
                data = json.loads(clean_json)
                return data
            except Exception as e:
                self.log_callback(f"⚠️ [AI] JSON 파싱 실패: {e}")
        return None


    def check_trademark(self, brand):
        """KIPRIS 상표권 조회"""
        if not brand or brand.upper() in ["NULL", "OEM", "NONE", ""]: return True
        
        brand = brand.strip().upper()
        if brand in self.brand_cache: return self.brand_cache[brand]
        if not self.kipris_keys: return True

        api_url = "https://plus.kipris.or.kr/kipo-api/kipi/trademarkInfoSearchService/getWordSearch"
        
        for _ in range(len(self.kipris_keys)):
            current_key = self.kipris_keys[self.current_kipris_idx]
            try:
                res = requests.get(api_url, params={'searchString': brand, 'ServiceKey': current_key}, timeout=5)
                if res.status_code != 200: raise Exception("Status Error")
                
                root = ET.fromstring(res.content)
                count_tag = root.find(".//totalCount")
                if count_tag is None: raise Exception("XML Parse Error")
                
                count = int(count_tag.text)
                is_safe = (count == 0)
                
                if not is_safe:
                    self.log_callback(f"   🚫 [KIPRIS] 상표권 발견: '{brand}' ({count}건)")
                    self._save_cache()
                
                self.brand_cache[brand] = is_safe
                return is_safe

            except:
                # 키 교체 후 재시도
                self.current_kipris_idx = (self.current_kipris_idx + 1) % len(self.kipris_keys)
        
        return True # 조회 실패 시 통과 처리

    # ============================================================
    # [Callback] 상세 페이지 처리 핵심 로직 (자동/반자동 공용)
    # ============================================================
    def _process_product_callback(self, driver, raw_title):
        """
        BrowserManager가 상세 페이지에 진입했을 때 호출되는 콜백.
        기존 processor.py의 핵심 로직을 여기에 이식했습니다.
        """
        try:
            # 1. 상세 페이지 본문 추출 (AI 분석용)
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
            except:
                body_text = ""
                
            current_kw = getattr(self, 'current_search_kw', '상품')

            self.log_callback("   🤖 [AI] 상품 정보 분석 중...")

            # 2. AI 정보 추출 (번역된 제목, 브랜드, 태그 등)
            info = self.extract_full_info(raw_title, body_text, current_kw)
            
            if not info or not info.get('is_valid', True):
                self.log_callback("   🗑️ [Skip] 유효하지 않은 상품")
                return False

            final_title = info.get('productTitle', raw_title)
            brand = info.get('brand', '')

            # 3. KIPRIS 상표권 검사
            if not self.check_trademark(brand):
                return False # 상표권 이슈로 중단
            
            cat_hint = info.get('category_candidates', [])

            # 4. 카테고리 분석 및 매칭
            cp_cat = self.excel_handler.find_best_category(cat_hint, 'coupang')
            nv_cat = self.excel_handler.find_best_category(cat_hint, 'naver')

            # 5. 엑셀 저장
            data_row = {
                'title': final_title,
                'url': driver.current_url,
                'tags': info.get('keywords', []),
                'cp_cat': cp_cat,
                'nv_cat': nv_cat,
                'manufacturer': info.get('manufacturer', 'OEM'),
                'brand': brand,
                'model': info.get('model', '')
            }
            
            if self.excel_handler.save_product(data_row):
                self.log_callback(f"   ✅ 저장 완료: {final_title[:15]}...")
                return True
            return False

        except Exception as e:
            self.log_callback(f"   ❌ 처리 중 오류: {e}")
            return False

    # ============================================================
    # [Flow] 실행 및 제어 (분기 로직 적용됨)
    # ============================================================
    def stop(self):
        self.is_running = False
        if self.panel:
            try: self.panel.destroy()
            except: pass
        self.browser.close()

    def run(self):
        """작업 시작: URL에 따라 모드 자동 분기"""
        self.is_running = True
        keywords = [k.strip() for k in self.config.get('TARGET_ITEMS', '').split(",") if k.strip()]
        urls = [u.strip() for u in self.config.get('SHOP_URLS', '').split(",") if u.strip()]
        max_count = int(self.config.get('ITEM_COUNT', 10))

        self.browser.start_driver()

        try:
            for shop_url in urls:
                if not self.is_running: break
                
                self._update_realtime_exchange_rate(shop_url)
                
                # 중국 사이트 판별
                is_china = any(x in shop_url.lower() for x in ['taobao', '1688', 'tmall'])
                
                if is_china:
                    self.run_manual_mode(shop_url)
                else:
                    self.run_auto_mode(shop_url, keywords, max_count)
        finally:
            self.stop()
            self.log_callback("\n🏁 [Finish] 모든 작업 종료")

    def run_manual_mode(self, url):
        """반자동 모드: 리모컨 사용"""
        self.log_callback(f"\n🇨🇳 [Manual] 반자동 모드: {url}")
        self.browser.driver.get(url)
        
        self.action_event = threading.Event()
        self.action_type = None 

        def on_collect():
            self.action_type = 'collect'; self.action_event.set()
        
        def on_stop():
            self.action_type = 'stop'; self.action_event.set(); self.is_running = False

        if self.app_root:
            self.app_root.after(0, lambda: self._create_panel(on_collect, on_stop))

        while self.is_running:
            self.action_event.clear()
            self.log_callback("   ⏳ [대기] 리모컨 '수집' 버튼 대기중...")
            
            while not self.action_event.is_set():
                if not self.is_running: break
                time.sleep(0.5)
            
            if not self.is_running or self.action_type == 'stop': break

            if self.action_type == 'collect':
                title, _ = self.browser.get_current_page_info()
                if title:
                    # ★ 여기서 AI 분석 로직(_process_product_callback)이 호출됩니다.
                    self.browser.process_current_page(self._process_product_callback)

        if self.app_root:
            self.app_root.after(0, lambda: self.panel.destroy() if self.panel else None)

    def _create_panel(self, c, s):
        self.panel = ManualControlPanel(self.app_root, c, s)

    def _get_search_url(self, base_url, keyword):
        """쇼핑몰별 검색 패턴에 맞는 URL 생성"""
        base_url = base_url.rstrip('/')
        if "amazon" in base_url.lower():
            return f"{base_url}/s?k={keyword}"
        elif "rakuten" in base_url.lower():
            # 라쿠텐은 전용 검색 경로 사용이 더 정확함
            return f"https://search.rakuten.co.jp/search/mall/{keyword}/"
        # 기본값 (일반적인 쿼리 파라미터 사용)
        return f"{base_url}/search?q={keyword}"
    
    def run_auto_mode(self, shop_url, keywords, max_count):
        from urllib.parse import urljoin  # 상대 경로 결합을 위해 필요
        
        for kw in keywords:
            translated_kw = self.detect_and_translate(shop_url, kw)
            total_saved_count = 0 
            page = 1 

            while total_saved_count < max_count and self.is_running:
                search_url = self._get_search_url(shop_url, translated_kw)
                if page > 1:
                    connector = "&" if "?" in search_url else "?"
                    if "amazon" in shop_url.lower(): search_url += f"{connector}page={page}"
                    elif "rakuten" in shop_url.lower(): search_url += f"{connector}p={page}"
                    else: search_url += f"{connector}page={page}"

                self.log_callback(f"\n📑 [Page {page}] '{translated_kw}' 분석 중... (진행: {total_saved_count}/{max_count})")
                self.log_callback(f"🌐 [Step 1] URL 접속 시도 중...")
                self.browser.driver.get(search_url)
                time.sleep(3)

                is_amazon = "amazon" in shop_url.lower()
                is_rakuten = "rakuten" in shop_url.lower()

                if is_amazon:
                    item_selector = "div.s-result-item[data-component-type='s-search-result'], div.s-card-container, .s-result-item"
                    price_selector = ".a-price .a-offscreen, .a-price-whole"
                elif is_rakuten:
                    item_selector = ".searchresultitem, [data-id], .dui-card.searchresultitem, div.searchresultitem, [data-index], .dui-card" 
                    price_selector = ".price--3zUvK, div[class*='price--'], .important"
                else: continue

                self.log_callback(f"🔍 [Step 2] 상품 목록 추출 시도...")
                self.browser.driver.implicitly_wait(10)
                items = self.browser.driver.find_elements(By.CSS_SELECTOR, item_selector)
                self.log_callback(f"📊 [Step 2] 발견된 요소: {len(items)}개")
                
                if not items:
                    self.log_callback("⚠️ 상품 목록을 찾지 못했습니다. 다음 키워드로 넘어갑니다.")
                    break

                target_links = []
                # 리스트 스캔 시에는 대기 시간을 0으로 설정하여 속도 향상
                self.browser.driver.implicitly_wait(0)
                
                for idx, item in enumerate(items):
                    if (idx + 1) % 20 == 0:
                        self.log_callback(f"   ⏳ [{idx+1}/{len(items)}] 항목 필터링 중...")
                    
                    try:
                        # [1] 링크 및 제목 추출
                        try:
                            link_el = item.find_element(By.CSS_SELECTOR, "a[data-link='item']")
                        except:
                            try: link_el = item.find_element(By.CSS_SELECTOR, "a[class*='title-link']")
                            except:
                                try: link_el = item.find_element(By.CSS_SELECTOR, "h2 a")
                                except: link_el = item.find_element(By.TAG_NAME, "a")

                        link = link_el.get_attribute("href")
                        title = link_el.get_attribute("title") or link_el.text.strip()

                        # [2] 경로 정규화 및 유효성 검사
                        if link and link.startswith("/"):
                            link = urljoin(shop_url, link)
                        
                        if not isinstance(link, str) or not link.startswith("http"):
                            continue

                        # [3] 쓰레기 링크 및 중고 필터링
                        if not title or len(title) < 3: continue
                        
                        garbage_list = ['help', 'customer', 'contact', 'policy', 'terms', 'sponsored', 'previous', 'next', 'javascript:', 'faq']
                        if any(g in link.lower() or g in title.lower() for g in garbage_list):
                            continue

                        if any(x in title for x in ['중고', '中古', 'Used', 'Pre-owned', 'Refurbished']):
                            continue

                        # [4] 아마존 전용 ASIN 검증
                        if is_amazon:
                            asin = item.get_attribute("data-asin")
                            if not asin or len(asin) < 5: continue

                        # [5] 가격 추출 및 필터링
                        krw_price = 0
                        try:
                            price_el = item.find_element(By.CSS_SELECTOR, price_selector)
                            raw_price_text = price_el.get_attribute('textContent')
                            clean_price_str = re.sub(r'[^0-9.]', '', raw_price_text)
                            
                            if clean_price_str.count('.') > 1:
                                parts = clean_price_str.split('.')
                                clean_price_str = parts[0] + "." + "".join(parts[1:])
                            
                            if clean_price_str:
                                krw_price = float(clean_price_str) * self.current_rate
                        except:
                            pass # 가격 못 찾아도 일단 통과 (상세페이지에서 재확인)

                        p_min = float(self.config.get('PRICE_MIN', 0))
                        p_max = float(self.config.get('PRICE_MAX', 0))

                        if krw_price > 0:
                            if (p_min > 0 and krw_price < p_min) or (p_max > 0 and krw_price > p_max):
                                continue

                        # 최종 통과된 상품만 추가
                        target_links.append({'link': link, 'title': title})

                    except Exception:
                        continue

                # 스캔 완료 후 대기 시간 원복
                self.browser.driver.implicitly_wait(10)
                self.log_callback(f"🚀 [Step 3] 분석 대상 상품 {len(target_links)}개 확정.")

                # [6] 상세 페이지 방문 및 AI 분석
                for prod in target_links:
                    if total_saved_count >= max_count or not self.is_running: break
                    
                    self.log_callback(f"   🚀 [시도] {prod['title'][:20]}...")
                    try:
                        self.browser.driver.get(prod['link'])
                        time.sleep(2)
                        
                        if self._process_product_callback(self.browser.driver, prod['title']):
                            total_saved_count += 1
                            self.log_callback(f"      ✅ 현재 {total_saved_count}/{max_count}개 저장 완료")
                    except Exception as e:
                        self.log_callback(f"   ⚠️ 상세페이지 오류: {e}")
                        continue

                if total_saved_count < max_count:
                    page += 1
                    self.log_callback(f"🔄 수량 미달({total_saved_count}/{max_count}). 다음 {page}페이지로 이동!")
                else:
                    self.log_callback(f"🎊 목표 수량({max_count}개) 달성 완료!")

            self.log_callback(f"✅ '{kw}' 키워드 최종 종료")