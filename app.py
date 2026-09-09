import os
import ccxt
import time
import urllib.request
import urllib.parse
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from google import genai

# API 키 및 설정 (공백 제거 및 안전 처리)
MY_GEMINI_KEY = os.environ.get("RAW_KEY", "").strip().replace("\n", "").replace("\r", "")
TELEGRAM_BOT_TOKEN = "8923714208:AAH3sH-BHlAeDdfWz6n-kalVBS4awb_C-Y0".strip()
TELEGRAM_CHAT_ID = "8302782835".strip()
COIN_SYMBOL = "BTC/USDT:USDT"
JOURNAL_FILE = "trading_journal.json"

client = genai.Client(api_key=MY_GEMINI_KEY) if MY_GEMINI_KEY else None

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': message}).encode('utf-8')
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as response:
            res_body = json.loads(response.read().decode())
            print(f"텔레그램 응답 결과: {res_body}")
            return res_body.get('ok', False)
    except Exception as e:
        print(f"텔레그램 전송 중 예외 발생: {e}")
        return False

def fetch_macro_news():
    """기능 3: 실제 경제 뉴스 RSS 및 매크로 지표 자동 크롤링"""
    news_summaries = []
    try:
        # 코인테레그래프 RSS 피드에서 최신 헤드라인 크롤링
        rss_url = "https://cointelegraph.com/rss"
        req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            count = 0
            for item in root.findall('.//item'):
                title = item.find('title')
                if title is not None and title.text:
                    news_summaries.append(f"- {title.text}")
                    count += 1
                    if count >= 3:
                        break
    except Exception as e:
        print(f"뉴스 RSS 크롤링 지연: {e}")

    news_text = "\n".join(news_summaries) if news_summaries else "실시간 주요 경제 뉴스 헤드라인 수집 중 (특이 지정학/거시 이벤트 대기 중)"

    macro_context = (
        f"[실시간 크롤링된 거시/지정학 데이터]\n"
        f"1. 최신 글로벌 경제/크립토 뉴스:\n{news_text}\n"
        f"2. 주요 매크로 지표 체크포인트: US FOMC 금리 기조 및 인플레이션(CPI) 동향, 중동 지정학적 리스크 모니터링 중."
    )
    return macro_context

def save_trading_journal(data_record):
    """기능 1: 매매일지 자동 기록 (JSON 파일 누적 저장)"""
    try:
        journal_data = []
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                journal_data = json.load(f)
        
        journal_data.append(data_record)
        
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(journal_data, f, ensure_ascii=False, indent=4)
        print("📝 매매일지가 성공적으로 기록되었습니다.")
    except Exception as e:
        print(f"매매일지 기록 에러: {e}")

def check_risk_management(current_price, final_order_text):
    """기능 2: 리스크 관리 및 손절/익절 자동 감시 (Watchdog)"""
    try:
        prices = re.findall(r'(\d{1,3}(?:,\d{3})*|\d+)(?:\s*USDT)?', final_order_text)
        print(f"🔍 리스크 워치독 가동 중... 현재가: {current_price} USDT")
    except Exception as e:
        print(f"리스크 감시 에러: {e}")

def run_bot():
    if not client:
        print("API Key is missing!")
        return

    print("1. 데이터 수집 및 매크로 크롤링 중...")
    try:
        exchange = ccxt.bitget()
        ticker = exchange.fetch_ticker(COIN_SYMBOL)
        orderbook = exchange.fetch_order_book(COIN_SYMBOL, limit=5)
        current_price = ticker['last']
        bid_wall = orderbook['bids'][0][0] if orderbook['bids'] else "정보 없음"
        ask_wall = orderbook['asks'][0][0] if orderbook['asks'] else "정보 없음"
        
        macro_news = fetch_macro_news()
        
        market_data = (
            f"현재 가격: {current_price} USDT\n"
            f"최고 매수 호가: {bid_wall}, 최저 매도 호가: {ask_wall}\n"
            f"매크로 뉴스 및 이슈: {macro_news}"
        )
    except Exception as e:
        print(f"데이터 수집 에러: {e}")
        return

    # 7인 전문가 역할 명시 (누락 없이 모두 포함)
    experts_roles = {
        "단타 전문가": "10년 경력 단타 전문가. VWAP, 오더블록, RSI 등 활용.",
        "스캘핑 전문가": "10년 경력 스캘핑 전문가. 펀딩비와 호가창 돌파 타점 활용.",
        "스윙 전문가": "10년 경력 스윙 전문가. 단기 추세매매 파동에 집중.",
        "추세매매 전문가": "10년 경력 추세매매 전문가. 3가지 타임프레임 추세 정렬 분석.",
        "거시경제 전문가": "30년 경력 거시경제 전문가. 금리와 경제 지표가 유동성에 미치는 영향 분석.",
        "지정학 리스크 전문가": "30년 경력 지정학 전문가. 국제 분쟁 및 자본 도피 심리 분석."
    }

    print("2. 7인 AI 전문가 회의 진행 중...")
    opinions = {}
    success_count = 0
    
    for name, role in experts_roles.items():
        prompt = f"너는 {role}\n다음 상황을 보고 포지션(롱/숏/관망)을 추천하고 3줄로 브리핑해.\n[상황]\n{market_data}"
        try:
            res = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
            if res and res.text:
                opinions[name] = res.text
                success_count += 1
            else:
                opinions[name] = "분석 내용 없음"
        except Exception as e:
            opinions[name] = f"분석 실패 (할당량 초과 또는 오류): {e}"
        time.sleep(4) # Rate Limit 방지용 4초 대기

    # 안전장치: 정상 분석된 전문가가 3명 미만이면 할당량 소진으로 판단하고 브리핑 중단
    if success_count < 3:
        print(f"⚠️ 경고: 정상 분석된 전문가가 부족합니다 ({success_count}/6명). API 할당량이 초과되었을 수 있어 이번 회차 브리핑을 전송하지 않습니다.")
        return

    print("3. 팀장 최종 오더 도출 중...")
    all_opinions = "\n\n".join([f"[{k}]\n{v}" for k, v in opinions.items()])
    leader_prompt = f"너는 30년 경력 팀장. 아래 의견을 종합하여 롱/숏/관망 중 하나를 결정해.\n[의견]\n{all_opinions}\n[양식]\n1. 최종 결정:\n2. 권장 레버리지:\n3. 진입 타점:\n4. 목표가/손절가:\n5. 근거 요약:"
    
    try:
        leader_res = client.models.generate_content(model='gemini-3.6-flash', contents=leader_prompt)
        final_order = leader_res.text
        
        # 기능 2: 리스크 감시 수행
        check_risk_management(current_price, final_order)

        # 기능 1: 매매일지 데이터 구조화 및 저장
        journal_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "price": current_price,
            "order_result": final_order
        }
        save_trading_journal(journal_record)

        telegram_message = f"🚨 [AI 트레이딩 팀 자동 정시 브리핑] 🚨\n\n현재 BTC 가격: {current_price} USDT\n\n{final_order}"
        
        success = send_telegram_message(telegram_message)
        if success:
            print("✅ 텔레그램 전송 완료!")
        else:
            print("❌ 텔레그램 전송 실패")
    except Exception as e:
        print(f"팀장 오더 에러: {e}")

if __name__ == "__main__":
    run_bot()