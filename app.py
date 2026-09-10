import os
import ccxt
import time
import urllib.request
import urllib.parse
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
import streamlit as st

# API 키 및 설정 
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
            return json.loads(response.read().decode()).get('ok', False)
    except:
        return False

def fetch_macro_news():
    news_summaries = []
    try:
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
                    if count >= 3: break
    except:
        pass
    news_text = "\n".join(news_summaries) if news_summaries else "실시간 주요 경제 뉴스 헤드라인 수집 중"
    return f"[최신 매크로 이슈]\n{news_text}"

def save_trading_journal(data_record):
    try:
        journal_data = []
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                journal_data = json.load(f)
        journal_data.append(data_record)
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(journal_data, f, ensure_ascii=False, indent=4)
    except:
        pass

# 개별 전문가 분석을 수행하는 함수 (병렬 처리용)
def ask_single_expert(name, role, market_data):
    prompt = f"너는 {role}\n다음 상황을 보고 포지션(롱/숏/관망)을 추천하고 핵심을 요약해.\n[상황]\n{market_data}"
    try:
        res = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        if res and res.text:
            return name, res.text
    except Exception as e:
        pass
    return name, "분석 오류 또는 응답 지연"

# ==========================================
# 🎨 Streamlit 웹 대시보드 UI 구성
# ==========================================
st.set_page_config(page_title="AI 트레이딩 봇", page_icon="🤖", layout="wide")
st.title("🤖 AI 트레이딩 봇 실시간 대시보드 (듀얼 브리핑 모드)")
st.write("유료 플랜 파워 적용! **단타용 / 추세용 듀얼 오더**를 동시 생성합니다.")

if st.button("🚀 듀얼 브리핑 즉시 실행", type="primary"):
    if not client:
        st.error("API 키가 없습니다. 환경 변수를 확인해 주세요.")
        st.stop()

    with st.status("듀얼 분석 엔진 가동 중...", expanded=True) as status:
        st.write("📊 1. 거래소 데이터 및 매크로 지표 수집 중...")
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
                f"{macro_news}"
            )
            st.info(f"**현재 BTC 가격:** {current_price} USDT 확보 완료")
        except Exception as e:
            st.error(f"데이터 수집 실패: {e}")
            st.stop()

        st.write("🧠 2. 6인 AI 전문가 **동시 심층 회의** 진행 중...")
        experts_roles = {
            "단타 전문가": "10년 경력 초단타/스캘핑 전문가. VWAP, 오더블록, RSI 활용.",
            "스캘핑 전문가": "10년 경력 오더북/펀딩비 스캘퍼. 호가창 돌파 타점 집중.",
            "스윙 전문가": "10년 경력 스윙 전문가. 단기 추세매매 파동 집중.",
            "추세매매 전문가": "10년 경력 추세매매 전문가. 다중 타임프레임 추세 분석.",
            "거시경제 전문가": "30년 경력 거시경제 전문가. 금리와 유동성 분석.",
            "지정학 리스크 전문가": "30년 경력 지정학 전문가. 국제 분쟁 심리 분석."
        }

        opinions = {}
        success_count = 0

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [
                executor.submit(ask_single_expert, name, role, market_data)
                for name, role in experts_roles.items()
            ]
            
            for future in as_completed(futures):
                name, result_text = future.result()
                opinions[name] = result_text
                if "분석 오류" not in result_text:
                    success_count += 1

        if success_count < 3:
            st.warning("⚠️ 전문가 의견 수집에 실패했습니다.")
            st.stop()

        st.write("👨‍💼 3. [단타용] 및 [추세용] 듀얼 팀장 오더 생성 및 전송 중...")
        all_opinions = "\n\n".join([f"[{k}]\n{v}" for k, v in opinions.items()])
        
        # 1. 단타 팀장 프롬프트
        scap_prompt = f"너는 공격적인 수십억 원 운용 수석 단타/스캘핑 팀장. 아래 전문가 의견을 바탕으로 1분~15분봉 기준 초단타 타점을 짜줘.\n[의견]\n{all_opinions}\n[양식]\n1. 단타 방향 (롱/숏):\n2. 추천 레버리지 (고배율 위주):\n3. 진입 타점:\n4. 칼손절가/익절가:\n5. 단타 타점 핵심 근거:"
        
        # 2. 추세 팀장 프롬프트
        trend_prompt = f"너는 안정적인 수십억 원 운용 수석 추세매매/스윙 팀장. 아래 전문가 의견을 바탕으로 1시간~4시간봉 기준 거시/추세 방향을 짜줘.\n[의견]\n{all_opinions}\n[양식]\n1. 추세 방향 (롱/숏/관망):\n2. 추천 레버리지 (안정형):\n3. 분할 진입 구간:\n4. 목표가/손절가:\n5. 추세 분석 근거:"

        try:
            # 듀얼 오더 동시 생성
            res_scap = client.models.generate_content(model='gemini-3.6-flash', contents=scap_prompt)
            res_trend = client.models.generate_content(model='gemini-3.6-flash', contents=trend_prompt)
            
            scap_order = res_scap.text
            trend_order = res_trend.text
            
            journal_record = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "price": current_price,
                "scap_result": scap_order,
                "trend_result": trend_order
            }
            save_trading_journal(journal_record)

            # 텔레그램 메시지 2개로 분할 전송
            tele_msg_scap = f"⚡ [1분~15분봉 초단타/스캘핑 브리핑] ⚡\n\n현재 BTC 가격: {current_price} USDT\n\n{scap_order}"
            tele_msg_trend = f"📈 [1시간~4시간봉 메이저 추세 브리핑] 📈\n\n현재 BTC 가격: {current_price} USDT\n\n{trend_order}"
            
            send_telegram_message(tele_msg_scap)
            time.sleep(0.5) # 메시지 순서 꼬임 방지 미세 딜레이
            send_telegram_message(tele_msg_trend)
            
            status.update(label="듀얼 초고속 브리핑 전송 완료!", state="complete", expanded=False)
        except Exception as e:
            st.error(f"팀장 오더 생성 실패: {e}")
            st.stop()

    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("⚡ [단타용] 팀장 오더")
        st.success(scap_order)
    with col2:
        st.subheader("📈 [추세용] 팀장 오더")
        st.info(trend_order)
    
    st.subheader("🧠 6인 전문가 개별 의견")
    cols = st.columns(2)
    for i, (name, op) in enumerate(opinions.items()):
        cols[i % 2].info(f"**{name}**\n\n{op}")