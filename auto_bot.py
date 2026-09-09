import os
import ccxt
import time
import urllib.request
import urllib.parse
import json
from google import genai

# API 키 및 설정
MY_GEMINI_KEY = os.environ.get("RAW_KEY", "").strip().replace("\n", "").replace("\r", "")
TELEGRAM_BOT_TOKEN = "8302782835"
TELEGRAM_CHAT_ID = "@MokDongPeople"
COIN_SYMBOL = "BTC/USDT:USDT"

client = genai.Client(api_key=MY_GEMINI_KEY) if MY_GEMINI_KEY else None

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': message}).encode('utf-8')
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode()).get('ok', False)
    except Exception:
        return False

def run_bot():
    if not client:
        print("API Key is missing!")
        return

    print("1. 데이터 수집 중...")
    try:
        exchange = ccxt.bitget()
        ticker = exchange.fetch_ticker(COIN_SYMBOL)
        orderbook = exchange.fetch_order_book(COIN_SYMBOL, limit=5)
        current_price = ticker['last']
        bid_wall = orderbook['bids'][0][0] if orderbook['bids'] else "정보 없음"
        ask_wall = orderbook['asks'][0][0] if orderbook['asks'] else "정보 없음"
        market_data = f"현재 가격: {current_price} USDT\n최고 매수 호가: {bid_wall}, 최저 매도 호가: {ask_wall}"
    except Exception as e:
        print(f"데이터 수집 에러: {e}")
        return

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
    for name, role in experts_roles.items():
        prompt = f"너는 {role}\n다음 상황을 보고 포지션(롱/숏/관망)을 추천하고 3줄로 브리핑해.\n[상황]\n{market_data}"
        try:
            res = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
            opinions[name] = res.text
        except Exception as e:
            opinions[name] = f"분석 실패: {e}"
        time.sleep(8) # Rate Limit 방지용 8초 대기

    print("3. 팀장 최종 오더 도출 중...")
    all_opinions = "\n\n".join([f"[{k}]\n{v}" for k, v in opinions.items()])
    leader_prompt = f"너는 30년 경력 팀장. 아래 의견을 종합하여 롱/숏/관망 중 하나를 결정해.\n[의견]\n{all_opinions}\n[양식]\n1. 최종 결정:\n2. 권장 레버리지:\n3. 진입 타점:\n4. 목표가/손절가:\n5. 근거 요약:"
    
    try:
        leader_res = client.models.generate_content(model='gemini-3.6-flash', contents=leader_prompt)
        final_order = leader_res.text
        telegram_message = f"🚨 [AI 트레이딩 팀 자동 정시 브리핑] 🚨\n\n현재 BTC 가격: {current_price} USDT\n\n{final_order}"
        send_telegram_message(telegram_message)
        print("✅ 텔레그램 전송 완료!")
    except Exception as e:
        print(f"팀장 오더 에러: {e}")

if __name__ == "__main__":
    run_bot()