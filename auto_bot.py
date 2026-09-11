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
import yfinance as yf
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
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            data = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': chunk}).encode('utf-8')
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req) as response:
                pass
            time.sleep(0.5)
        return True
    except:
        return False

# 🚀 [업그레이드 1] 전통금융 데이터를 15분 단위로 수집하여 실시간 반응 포착
def fetch_tradfi_data():
    try:
        tickers = {"나스닥": "NQ=F", "원유(WTI)": "CL=F", "금(Gold)": "GC=F", "미 국채 2년물": "^IRX", "미 국채 10년물": "^TNX", "미 국채 30년물": "^TYX"}
        results = []
        for name, symbol in tickers.items():
            ticker = yf.Ticker(symbol)
            # 최근 하루치 데이터를 15분 간격으로 가져와서 가장 최근 2개 캔들 비교 (추세 변화 포착)
            hist = ticker.history(period="1d", interval="15m")
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                curr_close = hist['Close'].iloc[-1]
                trend = "상승 📈" if curr_close > prev_close else "하락 📉"
                results.append(f"{name}: {curr_close:.2f} (직전대비 {trend})")
            elif not hist.empty:
                results.append(f"{name}: {hist['Close'].iloc[-1]:.2f}")
        return "\n".join(results)
    except Exception as e:
        return f"전통금융 데이터 수집 지연 ({e})"

# 🚀 [업그레이드 2] 매크로 지표 중심 뉴스 크롤링
def fetch_macro_news():
    news_summaries = []
    try:
        query = urllib.parse.quote("CPI OR PPI OR FOMC OR Bitcoin Funding Rate OR 트럼프 OR 금리 인하")
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            count = 0
            for item in root.findall('.//item'):
                title = item.find('title')
                pubDate = item.find('pubDate')
                if title is not None and title.text:
                    time_info = pubDate.text if pubDate is not None else ""
                    news_summaries.append(f"- [{time_info}] {title.text}")
                    count += 1
                    if count >= 10: break
    except:
        pass
    news_text = "\n".join(news_summaries) if news_summaries else "실시간 주요 경제 뉴스 수집 중"
    return f"[최신 매크로 이슈 (CPI/PPI 집중)]\n{news_text}"

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

def ask_expert(name, prompt):
    try:
        res = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        if res and res.text:
            return name, res.text
    except Exception as e:
        pass
    return name, "분석 오류 또는 응답 지연"

def get_market_data():
    exchange = ccxt.bitget()
    ticker = exchange.fetch_ticker(COIN_SYMBOL)
    orderbook = exchange.fetch_order_book(COIN_SYMBOL, limit=5)
    
    # 🚀 [업그레이드 3] 펀딩비 데이터 추가 (롱/숏 포지션 과열 상태 파악)
    funding_rate = "정보 없음"
    try:
        funding_info = exchange.fetch_funding_rate(COIN_SYMBOL)
        funding_rate = funding_info.get('fundingRate', '정보 없음')
    except:
        pass

    current_price = ticker['last']
    bid_wall = orderbook['bids'][0][0] if orderbook['bids'] else "정보 없음"
    ask_wall = orderbook['asks'][0][0] if orderbook['asks'] else "정보 없음"
    
    macro_news = fetch_macro_news()
    tradfi_data = fetch_tradfi_data()
    
    raw_data = (
        f"[비트코인 실시간 데이터]\n현재 가격: {current_price} USDT\n"
        f"최고 매수 호가: {bid_wall}, 최저 매도 호가: {ask_wall}\n"
        f"현재 펀딩비(Funding Rate): {funding_rate} (양수면 롱 과열, 음수면 숏 과열)\n\n"
        f"[전통금융 15분봉 동향 (국채/나스닥)]\n{tradfi_data}\n\n"
        f"{macro_news}"
    )
    return current_price, raw_data

def generate_and_send_briefing(current_price, raw_data):
    # 🚀 [업그레이드 4] CoT(사고과정) 및 이벤트 전/후 디커플링 강제 분석 프롬프트
    macro_geo_prompts = {
        "거시경제 전문가": f"너는 미국 연준 출신 거시경제 분석가. 다음 정보를 분석하되, 반드시 <사고 과정>을 먼저 거쳐라.\n1. 오늘이 CPI/PPI/FOMC 발표 전인가 후인가?\n2. 발표 전이라면 수치가 가격에 '선반영' 되었는지 분석하라.\n3. 발표 후라면 '예측치 vs 실제치'를 비교하고, 국채 금리는 내리는데 비트코인은 오르는 식의 '디커플링(이상 현상)'이 있는지, 자금 흐름이 왜 그렇게 움직였는지 논리적으로 증명하라.\n\n[데이터]\n{raw_data}",
        "지정학 리스크 전문가": f"너는 월스트리트 자산 배분 전문가. 15분 단위 국채 금리 증감과 펀딩비를 확인하라. 국채 금리가 하락하는데 비트코인이 상승한다면, 시장이 비트코인을 '위험자산'이 아닌 '대체 가치저장 수단'으로 보고 있는지 분석하라. 논리적 근거 없이 결론 내리지 마라.\n\n[데이터]\n{raw_data}"
    }
    
    foundation_opinions = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(ask_expert, name, prompt) for name, prompt in macro_geo_prompts.items()]
        for future in as_completed(futures):
            name, res = future.result()
            foundation_opinions[name] = res

    foundation_context = "\n\n".join([f"[{k}]\n{v}" for k, v in foundation_opinions.items()])
    
    tech_prompts = {
        "스캘핑 전문가": f"거시 분석을 바탕으로 북맵 유동성, 오더블록, 펀딩비 과열 상태를 체크하여 1~15분봉 숏/롱 타점을 잡아라. 이미 선반영되어 반등이 끝났다면 역추세 숏을 쳐라.\n\n[거시/지정학]\n{foundation_context}\n[현재가]: {current_price}",
        "단타 전문가": f"데이 트레이더 관점에서 VPVR, 다이버전스를 분석하라. 펀딩비가 양수 과열이면 롱 스퀴즈(하락) 가능성을 염두에 두고 타점을 제시하라.\n\n[거시/지정학]\n{foundation_context}\n[현재가]: {current_price}",
        "단기 스윙 전문가": f"1~2주 스윙 타점. 단기 채널 지지선과 저항선을 명시하라.\n\n[거시/지정학]\n{foundation_context}\n[현재가]: {current_price}",
        "추세매매 전문가": f"다이버전스 및 거래량 감소를 통한 변곡점 포착. 하락 반전 징후를 가장 우선적으로 찾아라.\n\n[거시/지정학]\n{foundation_context}\n[현재가]: {current_price}"
    }

    tech_opinions = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(ask_expert, name, prompt) for name, prompt in tech_prompts.items()]
        for future in as_completed(futures):
            name, res = future.result()
            tech_opinions[name] = res

    all_opinions_dict = {**foundation_opinions, **tech_opinions}
    all_opinions_text = "\n\n".join([f"[{k}]\n{v}" for k, v in all_opinions_dict.items()])
    
    # 🚀 [업그레이드 5] 악마의 변호인(리스크 팩터) 분석 강제
    scap_prompt = f"너는 수십억 운용 수석 스캘핑 팀장. 아래 분석을 보고 타점을 짜되, 반드시 [악마의 변호인: 이 타점이 실패할 경우의 논리]를 먼저 작성하고 그 리스크를 덮을 만큼 확실한 자리일 때만 포지션을 내라. 아니면 '관망'하라.\n[의견]\n{all_opinions_text}\n[양식]\n1. 악마의 변호인 (리스크 점검):\n2. 최종 방향 (롱/숏/관망):\n3. 레버리지:\n4. 진입 타점:\n5. 칼손절가/익절가:"
    trend_prompt = f"너는 단기 스윙 수석 팀장. 반드시 [악마의 변호인: 이 추세가 가짜일 확률]을 먼저 검증하라. 어설프면 무조건 '관망'하라.\n[의견]\n{all_opinions_text}\n[양식]\n1. 악마의 변호인 (리스크 점검):\n2. 최종 방향 (롱/숏/관망):\n3. 레버리지:\n4. 진입 타점:\n5. 목표가/손절가:"

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_scap = executor.submit(ask_expert, "단타팀장", scap_prompt)
        future_trend = executor.submit(ask_expert, "추세팀장", trend_prompt)
        _, scap_order = future_scap.result()
        _, trend_order = future_trend.result()
    
    journal_record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "price": current_price,
        "scap_result": scap_order,
        "trend_result": trend_order
    }
    save_trading_journal(journal_record)

    msg_3_part1 = f"⏰ [1/2] 거시/지정학/스캘핑 심층분석\n\n[거시경제]\n{all_opinions_dict.get('거시경제 전문가', '')}\n\n[지정학]\n{all_opinions_dict.get('지정학 리스크 전문가', '')}\n\n[스캘핑]\n{all_opinions_dict.get('스캘핑 전문가', '')}"
    msg_3_part2 = f"⏰ [2/2] 단타/스윙/추세 심층분석\n\n[단타]\n{all_opinions_dict.get('단타 전문가', '')}\n\n[단기 스윙]\n{all_opinions_dict.get('단기 스윙 전문가', '')}\n\n[추세매매]\n{all_opinions_dict.get('추세매매 전문가', '')}"
    
    send_telegram_message(msg_3_part1)
    time.sleep(1)
    send_telegram_message(msg_3_part2)

    tele_msg_scap = f"🔥 [최종 오더: 단타/스캘핑 (리스크 검증 완료)] 🔥\n\n현재가: {current_price}\n\n{scap_order}"
    tele_msg_trend = f"📈 [최종 오더: 단기 스윙 (리스크 검증 완료)] 📈\n\n현재가: {current_price}\n\n{trend_order}"
    
    time.sleep(1)
    send_telegram_message(tele_msg_scap)
    time.sleep(1)
    send_telegram_message(tele_msg_trend)
    
    return all_opinions_dict, scap_order, trend_order

# ==========================================
# 실행 모드 분기 (웹사이트 vs 깃허브 자동화)
# ==========================================
if __name__ == "__main__":
    # 터미널이나 깃허브 액션에서 직접 실행될 때 (Streamlit UI 없이 백그라운드 전송)
    try:
        import streamlit.web.cli
        is_streamlit = True
    except ImportError:
        is_streamlit = False

    # Streamlit으로 실행 중일 때만 UI 렌더링
    if "streamlit" in os.environ.get("_", "") or os.environ.get("STREAMLIT_SERVER_PORT"):
        st.set_page_config(page_title="AI 실전 퀀트 봇", page_icon="🤖", layout="wide")
        st.title("🤖 AI 트레이딩 봇 (적중률 극대화 버전)")
        st.write("15분봉 TradFi 데이터, 펀딩비, CPI/PPI 디커플링 강제 분석 장착.")

        if st.button("🚀 실전 듀얼 브리핑 즉시 실행", type="primary"):
            if not client:
                st.error("API 키가 없습니다.")
                st.stop()
            with st.status("실전 퀀트 분석 엔진 가동 중...", expanded=True):
                st.write("📊 데이터 수집 및 심층 분석 중 (약 15~20초 소요)...")
                try:
                    curr_price, raw_data = get_market_data()
                    all_ops, scap, trend = generate_and_send_briefing(curr_price, raw_data)
                    st.success("텔레그램 전송 완료!")
                    
                    st.divider()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("⚡ [단타용] 팀장 오더 (리스크 검증)")
                        st.success(scap)
                    with col2:
                        st.subheader("📈 [단기 스윙용] 팀장 오더 (리스크 검증)")
                        st.info(trend)
                except Exception as e:
                    st.error(f"오류 발생: {e}")
    else:
        # 깃허브 액션(정각 스케줄)으로 실행될 때 UI 없이 즉시 실행
        print(f"[{datetime.now()}] 🤖 정각 자동 퀀트 분석 시작...")
        if client:
            try:
                curr_price, raw_data = get_market_data()
                generate_and_send_briefing(curr_price, raw_data)
                print("✅ 텔레그램 전송 완료.")
            except Exception as e:
                print(f"❌ 오류: {e}")