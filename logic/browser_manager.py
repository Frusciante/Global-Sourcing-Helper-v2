import os
import subprocess
import time
import urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from tkinter import messagebox

class BrowserManager:
    def __init__(self, log_callback):
        self.log_callback = log_callback
        self.driver = None
        self.proc = None 
        self.checked_sites = set()

    def start_driver(self):
        """브라우저 실행 및 연결 최적화"""

        bot_path = os.path.join(os.getcwd(), "bot_profile_copy")
        chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(chrome_exe): 
            chrome_exe = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        
        port = 9222
        cmd = f'"{chrome_exe}" --remote-debugging-port={port} --user-data-dir="{bot_path}" --profile-directory=Default --no-first-run --no-default-browser-check --disable-blink-features=AutomationControlled --remote-allow-origins=* --homepage=about:blank'
        subprocess.Popen(cmd, shell=True)

        for i in range(20):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=1) as r:
                    if r.status == 200: break
            except: time.sleep(0.5)

        try:
            opts = Options()
            opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            opts.page_load_strategy = 'eager' 
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            self.driver.set_page_load_timeout(20)
            self.log_callback("✅ 브라우저 연결 성공")
            return self.driver
        except Exception as e:
            self.log_callback(f"❌ 연결 실패: {e}")
            raise e

    def close(self):
        if self.driver: self.driver.quit()

    def get_current_page_info(self):
        try: return self.driver.title, self.driver.current_url
        except: return None, None

    def process_current_page(self, callback):
        try:
            self.driver.execute_script("window.scrollTo(0, 800)")
            time.sleep(0.5)
            return callback(self.driver, self.driver.title)
        except: return False

    def search_and_collect(self, url, keyword, count, is_running_check, process_callback=None):
        driver = self.driver
        if not driver: return 0

        collected_count = 0
        page_num = 1
        is_first_load = True 
        processed_links = set()

        # [개선] 훨씬 더 넓고 유연한 셀렉터 구성
        site_config = {
            'amazon': {
                'search': "input#twotabsearchtextbox",
                'items': [
                    "div.s-result-item[data-component-type='s-search-result'] h2 a",
                    "div[data-cy='title-recipe'] a",
                    ".s-line-clamp-2 a",
                    "h2 a.a-link-normal"
                ],
                'next': "//a[contains(@aria-label, 'Next') or contains(@class, 's-pagination-next')]"
            },
            'rakuten': {
                'search': "input#commonSearchInput",
                'items': [
                    "a[data-link='item']",             # 라쿠텐 표준 데이터 속성
                    "a[class*='title-link']",          # 난수 클래스 대응 (title-link--...)
                    ".searchresultitem h2 a",          # 기존 구조
                    ".dui-card.searchresultitem a"     # 광고/특수 레이아웃
                ],
                'next': "//a[contains(@class, 'nextPage') or contains(text(), '次') or contains(text(), '다음')]"
            }
        }

        while is_running_check() and collected_count < count:
            try:
                if is_first_load:
                    driver.get(url)
                    time.sleep(2)
                    cur_url = driver.current_url.lower()
                    mode = 'amazon' if 'amazon' in cur_url else 'rakuten' if 'rakuten' in cur_url else 'amazon'
                    cfg = site_config[mode]

                    self.log_callback(f"🔍 [Search] '{keyword}' 검색 입력...")
                    try:
                        search_box = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, cfg['search'])))
                        search_box.click()
                        search_box.clear()
                        search_box.send_keys(keyword + Keys.ENTER)
                        time.sleep(4) 
                    except: pass
                    is_first_load = False

                # [수정] 스크롤을 살짝 내려서 Lazy Loading(뒤늦게 로딩되는 상품)을 활성화
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)

                # 상품 스캔 대기 조건 강화
                try:
                    # amazon의 데이터 혹은 rakuten의 리스트 요소 중 하나라도 뜰 때까지 대기
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-asin], .searchresultitem, a[data-link='item']")))
                except: pass

                links_on_page = []
                # [개선] 모든 셀렉터를 돌며 상품을 긁어모읍니다.
                for selector in cfg['items']:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        try:
                            href = el.get_attribute('href')
                            # [개선] title 속성이 있다면 우선적으로 가져옵니다.
                            title = el.get_attribute('title') or el.text.strip()
                            
                            # [수정] 필터링 완화: 제목이 5자만 넘어도 수집 (AI가 2차로 걸러줄 것임)
                            if href and "http" in href and href not in processed_links and len(title) > 5:
                                if "/slredirect/" in href: continue
                                links_on_page.append((title, href))
                                processed_links.add(href) # 중복 수집 방지
                        except: continue
                    # 상품을 찾았다면 다음 셀렉터로 넘어가기 전에 중단하지 않고 계속 수집하게 할 수도 있지만, 
                    # 중복 방지를 위해 우선 순위가 높은 셀렉터에서 찾았다면 break 해도 좋습니다.
                    if len(links_on_page) > 10: break

                if not links_on_page:
                    self.log_callback("🚫 상품 발견 실패. 페이지 구조를 다시 확인하거나 다음 페이지 시도.")
                else:
                    self.log_callback(f"📊 {len(links_on_page)}개 상품 분석 시작")

                # =========================================================
                # 🚀 상세 페이지 분석 루프 (탭 관리 강화)
                # =========================================================
                for title, link in links_on_page:
                    if not is_running_check() or collected_count >= count: break
                    
                    # 현재 메인 리스트 창의 핸들을 확실히 저장
                    main_win = driver.current_window_handle
                    processed_links.add(link)

                    try:
                        # 1. 새 탭 열기
                        driver.execute_script(f"window.open('{link}', '_blank');")
                        time.sleep(1) # 핸들 업데이트 대기
                        
                        # 2. 새 탭으로 전환
                        all_wins = driver.window_handles
                        driver.switch_to.window(all_wins[-1])
                        
                        self.log_callback(f"   🚀 [{collected_count+1}] 진입: {title[:15]}...")

                        # 3. 로딩 대기
                        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                        
                        # 4. 분석 실행
                        if process_callback and process_callback(driver, title):
                            collected_count += 1
                            self.log_callback(f"   ✅ 성공 ({collected_count}/{count})")
                        
                    except Exception as e:
                        self.log_callback(f"   ⚠️ 탭 작업 중 오류: {str(e)[:50]}")
                    
                    finally:
                        # [핵심] 안전하게 탭 닫기 및 복귀
                        try:
                            curr_wins = driver.window_handles
                            if len(curr_wins) > 1:
                                # 현재가 메인이 아니면 닫기
                                if driver.current_window_handle != main_win:
                                    driver.close()
                            # 무조건 메인으로 복귀
                            driver.switch_to.window(main_win)
                            time.sleep(0.5)
                        except:
                            # 만약 세션 자체가 끊겼다면 루프 탈출
                            self.log_callback("❌ 브라우저 세션이 끊겼습니다.")

                # 다음 페이지 이동
                if collected_count < count:
                    try:
                        next_btn = driver.find_element(By.XPATH, cfg['next'])
                        driver.execute_script("arguments[0].click();", next_btn)
                        page_num += 1
                        time.sleep(4)
                    except:
                        break
                
            except Exception as e:
                self.log_callback(f"⚠️ 루프 에러: {e}")
                break

        return collected_count