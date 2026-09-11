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

# 만약을 대비한 안전장치는 남겨두되, 기본적으로 원본 그대로 전송되도록 처리
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

def fetch_tradfi_data():
    try:
        tickers = {"나스닥": "NQ=F", "원유(WTI)": "CL=F", "금(Gold)": "GC=F", "미 국채 2년물": "^IRX", "미 국채 10년물": "^TNX", "미 국채 30년물": "^TYX"}
        results = []
        for name, symbol in tickers.items():
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                results.append(f"{name}: {hist['Close'].iloc[-1]:.2f}")
        return "\n".join(results)
    except:
        return "전통금융 데이터 수집 지연"

def fetch_macro_news():
    news_summaries = []
    try:
        query = urllib.parse.quote("Bitcoin OR FOMC OR CPI OR PPI OR 트럼프 OR Clarity Act")
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
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
                    if count >= 7: break
    except:
        pass
    news_text = "\n".join(news_summaries) if news_summaries else "실시간 주요 경제 뉴스 수집 중"
    return f"[최신 매크로 & 뉴스 이슈]\n{news_text}"

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

# ==========================================
# 🎨 Streamlit 웹 대시보드
# ==========================================
st.set_page_config(page_title="AI 실전 트레이딩 봇", page_icon="🤖", layout="wide")
st.title("🤖 AI 트레이딩 봇 (하드코어 실전 모드)")
st.write("나스닥, 국채, 유가 데이터 연동 완료. **3단계 크로스체킹 파이프라인** 가동.")

if st.button("🚀 실전 듀얼 브리핑 즉시 실행", type="primary"):
    if not client:
        st.error("API 키가 없습니다.")
        st.stop()

    with st.status("실전 분석 엔진 가동 중...", expanded=True) as status:
        st.write("📊 [1단계] 코인 & 전통금융(TradFi) & 매크로 뉴스 동시 수집 중...")
        try:
            exchange = ccxt.bitget()
            ticker = exchange.fetch_ticker(COIN_SYMBOL)
            orderbook = exchange.fetch_order_book(COIN_SYMBOL, limit=5)
            current_price = ticker['last']
            bid_wall = orderbook['bids'][0][0] if orderbook['bids'] else "정보 없음"
            ask_wall = orderbook['asks'][0][0] if orderbook['asks'] else "정보 없음"
            
            macro_news = fetch_macro_news()
            tradfi_data = fetch_tradfi_data()
            
            raw_data = (
                f"[비트코인 실시간]\n현재 가격: {current_price} USDT\n"
                f"최고 매수 호가: {bid_wall}, 최저 매도 호가: {ask_wall}\n\n"
                f"[전통금융(TradFi) 지표]\n{tradfi_data}\n\n"
                f"{macro_news}"
            )
        except Exception as e:
            st.error(f"데이터 수집 실패: {e}")
            st.stop()

        st.write("🧠 [2단계] 거시경제 & 지정학 전문가 선행 분석 중...")
        macro_geo_prompts = {
            "거시경제 전문가": f"너는 미국 연준(Fed) 출신 최고 거시경제 분석가. 다음 정보를 미국 공식 데이터 바탕으로 10회 이상 크로스체킹하는 과정을 거쳐 분석하라. CPI, PPI, FOMC 금리 동향, 트럼프 관련 이슈, 미국 디지털 자산 입법(Clarity Act)이 비트코인 롱/숏에 미칠 영향을 철저히 분석해라.\n\n[데이터]\n{raw_data}",
            "지정학 리스크 전문가": f"너는 월스트리트 출신 자산 배분 전문가. 나스닥, 유가(WTI), 금, 미 국채(2년, 10년, 30년)의 현재 수치와 변동성을 바탕으로 안전자산 선호도와 비트코인 자금 이탈/유입을 분석해라. 10번 이상 검증된 논리만 출력해라.\n\n[데이터]\n{raw_data}"
        }
        
        foundation_opinions = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(ask_expert, name, prompt) for name, prompt in macro_geo_prompts.items()]
            for future in as_completed(futures):
                name, res = future.result()
                foundation_opinions[name] = res

        st.write("⚔️ [3단계] 기술적 타점 전문가(단타/스캘핑/스윙/추세) 심층 분석 중...")
        foundation_context = "\n\n".join([f"[{k}]\n{v}" for k, v in foundation_opinions.items()])
        
        tech_prompts = {
            "스캘핑 전문가": f"너는 세계 트레이딩 대회 1위 출신 스캘퍼. 앞선 [거시/지정학 분석]을 인지한 상태에서, 최상위 스캘퍼들의 지표(VWAP, 오더블록, CVD(누적볼륨델타), 북맵 유동성, 1m/5m RSI 다이버전스) 5개 이상을 가상으로 시뮬레이션해라. 이미 반등이 끝난 자리면 절대 롱을 주지 말고 숏(Short) 타점을 잡아라. 짧은 프레임 진입 타점과 손절가를 명시하라.\n\n[거시/지정학 분석]\n{foundation_context}\n\n[현재 BTC 가격]: {current_price}",
            "단타 전문가": f"너는 하루 2~5회 매매하는 데이트레이더. 탑티어 트레이더 지표 10개(마켓 프로파일, VPVR 매물대, EMA 리본, MACD, 스토캐스틱, 피보나치, 볼린저 밴드, ATR, 유동성 스윕 등)를 기반으로 분석하라. 숏(Short) 관점을 절대 배제하지 마라. 현재 가격 기준 가장 확률 높은 롱 또는 숏 타점을 제시하라.\n\n[거시/지정학 분석]\n{foundation_context}\n\n[현재 BTC 가격]: {current_price}",
            "단기 스윙 전문가": f"너는 며칠에서 최대 2주 내에 승부를 보는 단기 스윙 트레이더. 너무 장기적인 관점은 버려라. 현재 매물대와 채널 하단/상단 돌파 여부를 보고 단기 스윙 롱/숏 타점을 잡아라.\n\n[거시/지정학 분석]\n{foundation_context}\n\n[현재 BTC 가격]: {current_price}",
            "추세매매 전문가": f"너는 다이버전스 및 추세 변곡점 포착의 대가. 현재 추세가 어디까지 이어질지, 추세선 이탈 및 거래량 감소 등 변곡점(하락 반전 등)의 징후가 있는지 파악하라.\n\n[거시/지정학 분석]\n{foundation_context}\n\n[현재 BTC 가격]: {current_price}"
        }

        tech_opinions = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(ask_expert, name, prompt) for name, prompt in tech_prompts.items()]
            for future in as_completed(futures):
                name, res = future.result()
                tech_opinions[name] = res

        all_opinions_dict = {**foundation_opinions, **tech_opinions}
        all_opinions_text = "\n\n".join([f"[{k}]\n{v}" for k, v in all_opinions_dict.items()])

        st.write("👨‍💼 [4단계] 듀얼 팀장 엄격 검열 및 오더 생성 중...")
        
        scap_prompt = f"너는 수십억 운용 수석 스캘핑 팀장. 아래 모든 분석을 10회 이상 검토하라. 승률이 확실치 않거나 근거가 상충하면 무조건 '관망(No Position)'을 지시하라. 포지션 진입 시 숏(Short)도 적극 고려하라.\n[의견]\n{all_opinions_text}\n[양식]\n1. 단타 방향 (롱/숏/관망):\n2. 레버리지:\n3. 진입 타점:\n4. 칼손절가/익절가:\n5. 핵심 근거:"
        trend_prompt = f"너는 단기 스윙/추세 수석 팀장. 아래 모든 분석을 10회 이상 검토하라. 변곡점이 불확실하면 억지로 타점을 주지 말고 '관망'하라. 1~2주 내 쇼부 보는 타점만 잡아라.\n[의견]\n{all_opinions_text}\n[양식]\n1. 스윙 방향 (롱/숏/관망):\n2. 레버리지:\n3. 진입 타점:\n4. 목표가/손절가:\n5. 핵심 근거:"

        try:
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

            # 📱 텔레그램 메시지 2명씩 논리적 그룹화 전송
            msg_group1 = f"🌍 [1/3] 거시 & 지정학 관점\n\n[거시경제 전문가]\n{all_opinions_dict.get('거시경제 전문가', '')}\n\n[지정학 리스크 전문가]\n{all_opinions_dict.get('지정학 리스크 전문가', '')}"
            msg_group2 = f"⚡ [2/3] 초단타 & 단타 관점\n\n[스캘핑 전문가]\n{all_opinions_dict.get('스캘핑 전문가', '')}\n\n[단타 전문가]\n{all_opinions_dict.get('단타 전문가', '')}"
            msg_group3 = f"🌊 [3/3] 스윙 & 추세 관점\n\n[단기 스윙 전문가]\n{all_opinions_dict.get('단기 스윙 전문가', '')}\n\n[추세매매 전문가]\n{all_opinions_dict.get('추세매매 전문가', '')}"
            
            tele_msg_scap = f"🔥 [최종 오더: 단타/스캘핑 팀장] 🔥\n\n현재 BTC 가격: {current_price} USDT\n\n{scap_order}"
            tele_msg_trend = f"📈 [최종 오더: 단기 스윙 팀장] 📈\n\n현재 BTC 가격: {current_price} USDT\n\n{trend_order}"
            
            # 순차적으로 발송 (순서 꼬임 방지)
            send_telegram_message(msg_group1)
            time.sleep(1)
            send_telegram_message(msg_group2)
            time.sleep(1)
            send_telegram_message(msg_group3)
            time.sleep(1)
            send_telegram_message(tele_msg_scap)
            time.sleep(1)
            send_telegram_message(tele_msg_trend)
            
            status.update(label="실전 하드코어 브리핑 전송 완료!", state="complete", expanded=False)
        except Exception as e:
            st.error(f"오더 생성 실패: {e}")
            st.stop()

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("⚡ [단타용] 팀장 오더")
        st.success(scap_order)
    with col2:
        st.subheader("📈 [단기 스윙용] 팀장 오더")
        st.info(trend_order)
        
    # 💻 웹 대시보드 UI를 보기 편하게 그룹별로 정리
    st.divider()
    st.subheader("🧠 6인 전문가 개별 심층 분석")
    
    st.markdown("#### 🌍 1. 거시 / 지정학 리스크 관점")
    c1, c2 = st.columns(2)
    with c1: st.info(f"**거시경제 전문가**\n\n{all_opinions_dict.get('거시경제 전문가', '')}")
    with c2: st.warning(f"**지정학 리스크 전문가**\n\n{all_opinions_dict.get('지정학 리스크 전문가', '')}")

    st.markdown("#### ⚡ 2. 초단타 / 스캘핑 관점")
    c3, c4 = st.columns(2)
    with c3: st.success(f"**스캘핑 전문가**\n\n{all_opinions_dict.get('스캘핑 전문가', '')}")
    with c4: st.success(f"**단타 전문가**\n\n{all_opinions_dict.get('단타 전문가', '')}")

    st.markdown("#### 🌊 3. 스윙 / 추세매매 관점")
    c5, c6 = st.columns(2)
    with c5: st.error(f"**단기 스윙 전문가**\n\n{all_opinions_dict.get('단기 스윙 전문가', '')}")
    with c6: st.error(f"**추세매매 전문가**\n\n{all_opinions_dict.get('추세매매 전문가', '')}")