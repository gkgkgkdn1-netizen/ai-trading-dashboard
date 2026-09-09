import os
import time
import ccxt
import urllib.request
import urllib.parse
import json
from google import genai

# ==================== [사용자 설정 영역] ====================
RAW_KEY = ""
MY_GEMINI_KEY = RAW_KEY.strip().replace("\n", "").replace("\r", "")

# 텔레그램 봇 토큰과 본인의 채팅 ID를 입력하세요
TELEGRAM_BOT_TOKEN = "8923714208:AAH3sH-BHlAeDdfWz6n-kalVBS4awb_C-Y0"
TELEGRAM_CHAT_ID = "@MokDongPeople"
# ==========================================================

client = genai.Client(api_key=MY_GEMINI_KEY)

# 텔레그램으로 메시지를 보내는 함수 (마크다운 에러 원천 차단형)
def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            if result.get('ok'):
                print("📲 [텔레그램] 최종 오더가 성공적으로 전송되었습니다!")
            else:
                print(f"⚠️ [텔레그램 전송 실패]: {result}")
    except Exception as e:
        print(f"⚠️ [텔레그램 에러 발생]: {e}")


print("🔗 비트겟(Bitget) 거래소에서 실시간 데이터를 수집하는 중입니다...")

exchange = ccxt.bitget()
symbol = 'BTC/USDT:USDT'

try:
    ticker = exchange.fetch_ticker(symbol)
    orderbook = exchange.fetch_order_book(symbol, limit=5)
    
    current_price = ticker['last']
    bid_wall = orderbook['bids'][0][0] if orderbook['bids'] else "정보 없음"
    ask_wall = orderbook['asks'][0][0] if orderbook['asks'] else "정보 없음"
    
    market_data = f"""
    현재 비트코인 선물 실시간 가격: {current_price} USDT
    실시간 호가창 정보: 최고 매수 호가(지지선 근처): {bid_wall}, 최저 매도 호가(저항선 근처): {ask_wall}
    최근 시장 상황 참고: 현재 비트코인 실시간 시세를 반영하여 분석할 것.
    """
    print(f"✅ 실시간 데이터 수집 완료! (현재 비트코인 가격: {current_price} USDT)\n")

except Exception as e:
    print(f"⚠️ 실시간 데이터 수집 실패, 기본값으로 대체합니다. (er: {e})")
    current_price = 79266
    market_data = "현재 비트코인 가격: 79,266 USDT (실시간 연동 실패로 인한 대체값)"

print("🧠 7인의 AI 전문가 팀이 실시간 차트 분석을 시작합니다...\n")
print("=" * 60)

experts_roles = {
    "단타 전문가": "10년 경력의 단타 전문 트레이더. VWAP, 오더블록, RSI, MACD, 일목균형표, 그리고 각종 이동평균선(EMA, MA, SMA) 등 활용 가능한 모든 지표를 융합하여 교차 검증한 뒤, 하루 이내의 가장 승률 높은 타점을 잡아내는 분석가.",
    "스캘핑 전문가": "10년 경력의 스캘핑 전문 트레이더. 펀딩비 비율과 초단기 호가창 틱 데이터 분석에 더해, 핵심 '매물대(Order Block)'를 뚫고 나가는 돌파 타점과 지지/저항 리테스트를 활용하여 찰나의 수익을 극대화하는 스타일.",
    "스윙 전문가": "10년 경력의 스윙 전문 트레이더. MACD, 파라볼릭 SAR, ADX, 일목균형표 선행스팬, 볼린저밴드 등 5가지 이상의 추세 확인 지표를 복합적으로 사용하되, 오직 '단기 추세매매' 파동에만 광적으로 집착하여 며칠 단위의 짧고 굵은 파동만 발라먹음.",
    "추세매매 전문가": "10년 경력의 추세매매 전문 트레이더. 5가지 이상의 주요 추세 지표를 활용하며, 특히 '단기, 중기, 장기' 세 가지 타임프레임의 추세 정렬 상태만 지독하게 파고들어 거대한 방향성을 쫓는 스타일.",
    "거시경제 전문가": "30년 경력의 거시경제 전문가. FOMC, CPI 등 주요 경제 지표가 코인 시장 유동성에 미치는 영향을 분석함.",
    "지정학 리스크 전문가": "30년 경력의 지정학 전문가. 국제 분쟁, 전쟁 리스크, 자본 도피 심리 등을 분석하여 리스크를 평가함."
}

opinions = {}

for name, role in experts_roles.items():
    print(f"⏳ [{name}] 분석 중...")
    
    prompt = f"""
    너는 {role}
    다음 실시간 시장 상황을 보고 너의 전문 분야와 지표들에 입각해 분석해.
    반드시 '포지션 추천 (롱/숏/관망)'을 명시하고, 그 이유를 3줄 이내로 핵심만 브리핑해.
    
    [실시간 시장 상황]
    {market_data}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt
        )
        opinions[name] = response.text
        print(f"✅ [{name} 완료]\n")
    except Exception as e:
        print(f"⚠️ [{name}] 지연 발생, 5초 후 재시도...")
        time.sleep(5)
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt
        )
        opinions[name] = response.text
        print(f"✅ [{name} 완료 (재시도 성공)]\n")
        
    time.sleep(3)

print("👑 팀장이 모든 전문가의 의견을 취합하여 최종 오더를 내리고 있습니다...\n")
time.sleep(3)

all_opinions_text = ""
for name, opinion in opinions.items():
    all_opinions_text += f"[{name} 의견]\n{opinion}\n\n"

leader_prompt = f"""
너는 이 트레이딩 팀의 30년 경력 최종 결정권자(팀장)야. 
현재 비트코인 실시간 가격({current_price} USDT)을 기준으로, 아래 전문가들의 의견을 꼼꼼히 읽고 논리가 충돌하는 부분을 조율해.
최종적으로 롱(매수), 숏(매도), 관망 중 단 하나만 결정하고 아래 양식에 맞춰서 최종 오더를 내려줘.

[전문가 의견 종합]
{all_opinions_text}

[출력 양식]
1. 최종 결정: (롱 / 숏 / 관망)
2. 권장 레버리지: (예: 5x, 10x 등)
3. 진입 타점: (구체적인 가격)
4. 목표가 및 손절가:
5. 결정 핵심 근거: (3줄 이내로 요약)
"""

leader_decision = client.models.generate_content(
    model='gemini-3.6-flash',
    contents=leader_prompt
)

final_order_text = leader_decision.text

print("🚀 [팀장 최종 실시간 매매 오더]")
print("=" * 60)
print(final_order_text)
print("=" * 60)

# 텔레그램으로 최종 결과 발송
telegram_message = f"🚨 [AI 트레이딩 팀 실시간 오더] 🚨\n\n현재 BTC 가격: {current_price} USDT\n\n{final_order_text}"
send_telegram_message(telegram_message)