import os
import pandas as pd
import openpyxl

class ExcelHandler:
    def __init__(self, target_file, log_callback, config):
        self.target_file = target_file
        self.log_callback = log_callback
        self.config = config
        self.coupang_cat = None
        self.naver_cat = None
        self.load_categories()

    def load_categories(self):
        try:
            if not os.path.exists(self.target_file): 
                self.log_callback(f"⚠️ [Excel] 파일 없음: {self.target_file}")
                return
            self.log_callback("📂 [Excel] 카테고리 로딩 중...")
            
            cp_df = pd.read_excel(self.target_file, sheet_name='쿠팡 전체 카테고리 (240517)', dtype=str)
            nv_df = pd.read_excel(self.target_file, sheet_name='네이버 전체 카테고리 (251215)', dtype=str)
            
            # [수정 핵심] 첫 번째 컬럼(.iloc[:, 0])을 리스트(.tolist())로 즉시 변환합니다.
            self.coupang_cat = cp_df.iloc[:, 0].dropna().tolist()
            self.naver_cat = nv_df.iloc[:, 0].dropna().tolist()

            self.log_callback("✅ [Excel] 카테고리 로드 완료")
        except Exception as e:
            self.log_callback(f"❌ [Excel] 로드 실패: {e}")

    def find_best_category(self, candidates, shop_type):
        """
        1단계: 정확히 일치(Exact Match)하는 경로 탐색
        2단계: 1단계 실패 시 포함(Contains)하는 경로 탐색
        공통: 경로의 뒤쪽(세분류)에 매칭될수록 높은 점수 부여
        """
        best_path = ""
        max_score = -1

        # 금지 단어 (도서, 종교 등 오매칭 방지)
        forbidden = ["도서", "종교", "잡지", "불교", "성경"]

        # 1. 엑셀 데이터 미리 로드 (성능 최적화)
        target_data = self.coupang_cat if shop_type == 'coupang' else self.naver_cat
        if target_data is None or len(target_data) == 0: 
            return best_path

        # --- [Phase 1: 정확히 일치 검사] ---
        for path in target_data:
            if any(f in path for f in forbidden): continue
            
            parts = [p.strip() for p in path.split('>')]
            for cand in candidates:
                for idx, part in enumerate(parts):
                    if cand == part: # 정확히 일치
                        score = (idx + 1) * 100 # 정확 일치는 높은 가점
                        if score > max_score:
                            max_score = score
                            best_path = path

        # --- [Phase 2: 포함 검사 (1단계 실패 시)] ---
        if max_score == -1:
            for path in target_data:
                if any(f in path for f in forbidden): continue
                
                parts = [p.strip() for p in path.split('>')]
                for cand in candidates:
                    for idx, part in enumerate(parts):
                        if cand in part: # 포함 관계
                            score = (idx + 1) * 10 # 포함은 상대적으로 낮은 가점
                            if score > max_score:
                                max_score = score
                                best_path = path

        return best_path

    def save_product(self, data_row):
        try:
            wb = openpyxl.load_workbook(self.target_file)
            ws = wb['엑셀 수집 양식 (Ver.9)']
            
            start_row = 7
            while ws.cell(row=start_row, column=4).value is not None: start_row += 1
            
            tags_value = data_row.get('tags', '')
            if isinstance(tags_value, list): tags_value = ", ".join(tags_value)
            
            ws.cell(row=start_row, column=2, value=data_row.get('cp_cat', ''))
            ws.cell(row=start_row, column=3, value=data_row.get('nv_cat', ''))
            ws.cell(row=start_row, column=4, value=data_row.get('title', ''))
            ws.cell(row=start_row, column=5, value=tags_value)
            ws.cell(row=start_row, column=6, value=data_row.get('url', ''))
            
            try:
                cost_basic = int(self.config.get('COST_BASIC', 3000))
                cost_exchange = int(self.config.get('COST_EXCHANGE', 6000))
                cost_return = int(self.config.get('COST_RETURN', 6000))
            except: cost_basic, cost_exchange, cost_return = 3000, 6000, 6000

            ws.cell(row=start_row, column=7, value=0)
            ws.cell(row=start_row, column=8, value='유료' if cost_basic > 0 else '무료')
            ws.cell(row=start_row, column=9, value=cost_basic)
            ws.cell(row=start_row, column=10, value=cost_exchange)
            ws.cell(row=start_row, column=11, value=cost_return)
            
            ws.cell(row=start_row, column=12, value=data_row.get('manufacturer', 'OEM'))
            ws.cell(row=start_row, column=13, value=data_row.get('brand', 'OEM'))
            ws.cell(row=start_row, column=14, value=data_row.get('model', ''))
            
            wb.save(self.target_file)
            self.log_callback(f"💾 [Excel] 저장 완료 (행: {start_row})")
            return True
            
        except PermissionError:
            self.log_callback("❌ [Excel] 저장 실패: 엑셀 파일을 닫아주세요.")
            return False
        except Exception as e:
            self.log_callback(f"❌ [Excel] 오류: {e}")
            return False