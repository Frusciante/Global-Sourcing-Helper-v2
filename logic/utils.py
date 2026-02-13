import requests
import re

# 기본 환율 하드코딩 (네트워크 실패 대비)
DEFAULT_RATES = {
    "USD": 1450.0,
    "JPY": 10.0,
    "CNY": 200.0
}

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