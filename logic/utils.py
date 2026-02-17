import requests
import datetime
import translators as ts
import time
import re
from googletrans import Translator
import time

# 기본 환율 하드코딩 (네트워크 실패 대비)
DEFAULT_RATES = {
    "USD": 1450.0,
    "JPY": 10.0,
    "CNY": 200.0
}

# 전역 Translator 객체 생성
google_translator = Translator()

def translate_text(text, target_lang='ko'):
    """
    상품 제목 등 문장 형태의 단일 입력을 한국어로 번역합니다.
    AI 개입 없이 googletrans를 사용하여 할루시네이션을 방지합니다.
    """
    if not text or len(str(text).strip()) < 2:
        return text
    
    clean_text = str(text).strip()
    print(f"🌐 [googletrans] 번역 요청: '{clean_text[:30]}...' -> {target_lang}")
    
    # 재시도 로직 포함
    for attempt in range(2):
        try:
            # dest에 'ko', 'en', 'ja', 'zh-cn' 등을 사용합니다.
            res = google_translator.translate(clean_text, dest=target_lang)
            if res and res.text:
                return res.text.strip()
        except Exception as e:
            if attempt == 0:
                print(f"⚠️ 문장 번역 1차 실패, 재시도 중... ({e})")
                time.sleep(1)
            else:
                print(f"❌ 문장 번역 최종 실패: {e}")
                
    return clean_text # 최종 실패 시 원문 반환

def translate_keywords_list(keyword_list, target_lang='ko', max_retries=2):
    """
    리스트 단위 번역을 수행합니다. 
    항목 내부에 쉼표가 있을 경우를 대비해 '|' 구분자를 사용하여 개수 불일치를 방지합니다.
    """
    if not keyword_list:
        return []
    
    original_count = len(keyword_list)
    # 항목 내 쉼표와 섞이지 않도록 ' | '를 구분자로 사용합니다.
    separator = " | "
    combined_query = separator.join(keyword_list)
    
    print(f"🌐 [googletrans] 리스트 번역 요청 (항목 {original_count}개) -> {target_lang}")
    
    for attempt in range(max_retries):
        try:
            res = google_translator.translate(combined_query, dest=target_lang)
            
            if res and res.text:
                translated_raw = res.text
                # 파이프 기호로 분리하여 리스트화
                translated_list = [
                    item.strip() 
                    for item in translated_raw.split('|')
                    if item.strip()
                ]
                
                # 개수가 일치하면 즉시 반환
                if len(translated_list) == original_count:
                    return translated_list
                
                # [보정 로직] 번역기가 파이프를 쉼표로 바꿔버린 경우를 대비해 한 번 더 체크
                print(f"🔄 번역된 결과: '{translated_raw}'")
                alt_list = [
                    i.strip() 
                    for i in translated_raw.replace('，', ',').split(',') 
                    if i.strip()
                ]
                if len(alt_list) == original_count:
                    return alt_list

                print(f"⚠️ 개수 불일치 (재시도 {attempt+1}/{max_retries}): "
                      f"원본 {original_count}개 -> 결과 {len(translated_list)}개")
                time.sleep(1.5)
                
        except Exception as e:
            print(f"⚠️ 시도 {attempt+1} 실패: {e}")
            time.sleep(1.5)

    # 2. 최종 안전 장치 (Fallback): 개별 단어 하나씩 번역
    print(f"🔄 최종 보정: 개별 번역 모드로 전환합니다.")
    final_list = []
    for word in keyword_list:
        # 위에 정의한 단일 텍스트 번역 함수 호출
        translated_word = translate_text(word, target_lang)
        final_list.append(translated_word)
        time.sleep(0.5) # IP 차단 방지
            
    return final_list

def fetch_naver_trend_keywords(category_code="50000008"):
    """
    네이버 데이터랩 쇼핑인사이트에서 카테고리별 인기 키워드 TOP 20을 가져옵니다.
    """
    # 데이터랩 데이터는 보통 2일 전 데이터가 가장 안정적입니다.
    target_date = (datetime.date.today() - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    
    url = "https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://datalab.naver.com/shoppingInsight/sCategory.naver",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://datalab.naver.com"
    }
    
    # 카테고리가 "ALL"인 경우 기본값(생활/건강)을 할당하거나 특정 처리
    cid = "50000008" if category_code == "ALL" else category_code
    
    data = {
        "cid": cid,
        "timeUnit": "date",
        "startDate": target_date,
        "endDate": target_date,
        "age": "",
        "gender": "",
        "device": "",
        "page": "1",
        "count": "20"
    }

    try:
        response = requests.post(url, headers=headers, data=data, timeout=5)
        if response.status_code == 200:
            result_json = response.json()
            if isinstance(result_json, dict) and 'ranks' in result_json:
                # 키워드만 리스트로 추출
                return [r['keyword'] for r in result_json['ranks']]
        return []
    except Exception as e:
        print(f"네이버 트렌드 요청 실패: {e}")
        return []

def fetch_naver_exchange_rate(target="USD"):
    """
    네이버 PC 버전에서 특정 통화의 환율을 크롤링합니다.
    :param target: "USD", "JPY", "CNY" 중 하나
    :return: float 환율값
    """
    target = target.upper()
    try:
        # PC 버전 레이아웃을 위해 데스크톱 User-Agent 설정
        search_url = f"https://search.naver.com/search.naver?query={target}+환율"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        res = requests.get(search_url, headers=headers, timeout=5)
        
        # 분석하신 data-value="up" 속성을 가진 input 태그의 value 추출
        pattern = r'value="([\d,.]+)"[^>]*data-value="up"'
        match = re.search(pattern, res.text)
        
        if match:
            rate_str = match.group(1).replace(",", "")
            rate = float(rate_str)
            
            # 엔화(JPY) 100엔 단위 보정
            if target == "JPY" and rate > 100:
                rate /= 100
            
            # 최소 상식 검증
            if (target == "USD" and rate < 1000) or (target == "CNY" and rate < 100):
                raise ValueError("조회된 환율이 너무 낮습니다.")
                
            return rate
        
        raise Exception("태그 매칭 실패")

    except Exception:
        # 실패 시 하드코딩된 기본값 반환
        return DEFAULT_RATES.get(target, 1450.0)