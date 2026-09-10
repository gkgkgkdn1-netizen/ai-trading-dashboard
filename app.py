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
    prompt = f"너는 {role}\n다음 상황을 보고 포지션(롱/숏/관망)을 추천하고 3줄로 요약해.\n[상황]\n{market_data}"
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
st.title("🤖 AI 트레이딩 봇 실시간 대시보드 (병렬 초고속 모드)")
st.write("유료 플랜 파워 적용! **6인 전문가 동시 호출(ThreadPool)**로 5초 만에 결과를 뽑아냅니다.")

if st.button("🚀 초고속 병렬 브리핑 실행", type="primary"):
    if not client:
        st.error("API 키가 없습니다. 환경 변수를 확인해 주세요.")
        st.stop()

    with st.status("병렬 고속 분석 엔진 가동 중...", expanded=True) as status:
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

        st.write("🧠 2. 6인 AI 전문가 **동시(Parallel) 심층 회의** 진행 중...")
        experts_roles = {
            "단타 전문가": "10년 경력 단타 전문가. VWAP, 오더블록, RSI 활용.",
            "스캘핑 전문가": "10년 경력 스캘핑 전문가. 펀딩비와 호가창 돌파 타점 활용.",
            "스윙 전문가": "10년 경력 스윙 전문가. 단기 추세매매 파동 집중.",
            "추세매매 전문가": "10년 경력 추세매매 전문가. 다중 타임프레임 추세 분석.",
            "거시경제 전문가": "30년 경력 거시경제 전문가. 금리와 유동성 분석.",
            "지정학 리스크 전문가": "30년 경력 지정학 전문가. 국제 분쟁 심리 분석."
        }

        opinions = {}
        success_count = 0

        # ThreadPoolExecutor를 사용해 6명에게 동시에 질문을 와르르 던집니다!
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

        st.write("👨‍💼 3. 팀장 의견 종합 및 텔레그램 전송 중...")
        all_opinions = "\n\n".join([f"[{k}]\n{v}" for k, v in opinions.items()])
        leader_prompt = f"너는 30년 경력 팀장. 아래 의견을 종합하여 롱/숏/관망 중 하나를 결정해.\n[의견]\n{all_opinions}\n[양식]\n1. 최종 결정:\n2. 권장 레버리지:\n3. 진입 타점:\n4. 목표가/손절가:\n5. 근거 요약:"
        
        try:
            leader_res = client.models.generate_content(model='gemini-3.6-flash', contents=leader_prompt)
            final_order = leader_res.text
            
            journal_record = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "price": current_price,
                "order_result": final_order
            }
            save_trading_journal(journal_record)

            tele_msg = f"🚨 [초고속 병렬 브리핑] 🚨\n\n현재 BTC 가격: {current_price} USDT\n\n{final_order}"
            send_telegram_message(tele_msg)
            
            status.update(label="5초 컷 병렬 브리핑 완료!", state="complete", expanded=False)
        except Exception as e:
            st.error(f"팀장 오더 생성 실패: {e}")
            st.stop()

    st.divider()
    st.subheader("👨‍💼 팀장 최종 오더")
    st.success(final_order)
    
    st.subheader("🧠 6인 전문가 개별 의견")
    cols = st.columns(2)
    for i, (name, op) in enumerate(opinions.items()):
        cols[i % 2].info(f"**{name}**\n\n{op}")