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
import pandas as pd
import numpy as np
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

def fetch_tradfi_data():
    try:
        tickers = {"나스닥": "NQ=F", "원유(WTI)": "CL=F", "금(Gold)": "GC=F", "미 국채 10년물": "^TNX"}
        results = []
        for name, symbol in tickers.items():
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d", interval="15m")
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                curr_close = hist['Close'].iloc[-1]
                trend = "상승 📈" if curr_close > prev_close else "하락 📉"
                results.append(f"{name}: {curr_close:.2f} (직전대비 {trend})")
            elif not hist.empty:
                results.append(f"{name}: {hist['Close'].iloc[-1]:.2f}")
        return "\n".join(results)
    except:
        return "전통금융 데이터 수집 지연"

def fetch_macro_news():
    news_summaries = []
    try:
        query = urllib.parse.quote("CPI OR PPI OR FOMC OR Bitcoin Funding Rate")
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
    news_text = "\n".join(news_summaries) if news_summaries else "최신 주요 경제 뉴스 수집 중"
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

def ask_expert(name, prompt):
    try:
        res = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        if res and res.text:
            return name, res.text
    except Exception as e:
        pass
    return name, "분석 오류 또는 응답 지연"

# 🔥 [핵심 퀀트 엔진] 파이썬 수학 연산을 통한 100% 팩트 지표 산출
def get_quant_indicators(exchange):
    try:
        # 비트겟 15분봉 100개 긁어오기
        ohlcv = exchange.fetch_ohlcv(COIN_SYMBOL, timeframe='15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 1. VWAP (거래량 가중 평균가)
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (df['tp'] * df['volume']).cumsum() / df['volume'].cumsum()
        
        # 2. RSI (상대강도지수 14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 3. 볼린저 밴드 (20, 2)
        df['sma20'] = df['close'].rolling(window=20).mean()
        df['std20'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['sma20'] + (df['std20'] * 2)
        df['bb_lower'] = df['sma20'] - (df['std20'] * 2)
        
        # 4. 장세 판별 (Regime Filter) - 밴드폭 기준
        last = df.iloc[-1]
        bb_width = (last['bb_upper'] - last['bb_lower']) / last['sma20'] * 100
        regime = "추세장 (변동성 폭발)" if bb_width > 2.5 else "횡보장 (변동성 수렴중 - 박스권 매매 요망)"

        return {
            "rsi": f"{last['rsi']:.1f}",
            "vwap": f"{last['vwap']:.1f}",
            "bb_upper": f"{last['bb_upper']:.1f}",
            "bb_lower": f"{last['bb_lower']:.1f}",
            "bb_width": f"{bb_width:.2f}%",
            "regime": regime
        }
    except Exception as e:
        return {"error": f"퀀트 연산 실패: {e}"}

def get_market_data():
    exchange = ccxt.bitget()
    ticker = exchange.fetch_ticker(COIN_SYMBOL)
    orderbook = exchange.fetch_order_book(COIN_SYMBOL, limit=5)
    
    current_price = ticker['last']
    bid_wall = orderbook['bids'][0][0] if orderbook['bids'] else "정보 없음"
    ask_wall = orderbook['asks'][0][0] if orderbook['asks'] else "정보 없음"
    
    # 펀딩비 및 미결제약정(OI) 수집 시도
    funding_rate = "정보 없음"
    open_interest = "정보 없음"
    try:
        funding_info = exchange.fetch_funding_rate(COIN_SYMBOL)
        funding_rate = funding_info.get('fundingRate', '정보 없음')
        oi_info = exchange.fetch_open_interest(COIN_SYMBOL)
        open_interest = oi_info.get('openInterestAmount', '정보 없음')
    except:
        pass

    # 파이썬 수학 퀀트 지표 연산 결과
    quant = get_quant_indicators(exchange)
    quant_text = (
        f"- 장세 판단: {quant.get('regime', 'N/A')}\n"
        f"- 15m RSI: {quant.get('rsi', 'N/A')} (30이하 과매도, 70이상 과매수)\n"
        f"- 15m VWAP: {quant.get('vwap', 'N/A')}\n"
        f"- 볼린저 밴드 상단: {quant.get('bb_upper', 'N/A')} / 하단: {quant.get('bb_lower', 'N/A')}\n"
        f"- 밴드폭(수축도): {quant.get('bb_width', 'N/A')}"
    ) if "error" not in quant else "지표 계산 오류"

    macro_news = fetch_macro_news()
    tradfi_data = fetch_tradfi_data()
    
    raw_data = (
        f"🚨 [절대 규칙] 너희는 지표를 임의로 상상하거나 추측하지 마라. 아래의 [수치화된 팩트 데이터]만을 100% 신뢰하여 분석하라.\n\n"
        f"[코인 실시간 팩트 데이터]\n"
        f"현재 가격: {current_price} USDT\n"
        f"펀딩비: {funding_rate} / 미결제약정(OI): {open_interest}\n\n"
        f"💻 [파이썬 퀀트 지표 연산 팩트 (15분봉)]\n{quant_text}\n\n"
        f"[전통금융 15분봉 동향]\n{tradfi_data}\n\n"
        f"{macro_news}"
    )
    return current_price, raw_data

def generate_and_send_briefing(current_price, raw_data):
    macro_geo_prompts = {
        "거시경제 전문가": f"너는 월가 출신 거시 퀀트. [데이터]를 바탕으로 <사고 과정>을 거쳐 팩트만 서술하라. 국채 금리 증감과 비트코인 가격의 디커플링(상반된 움직임) 여부를 수치적으로 분석하라.\n\n[데이터]\n{raw_data}",
        "지정학 리스크 전문가": f"너는 자산 배분 전문가. 전통금융 자산 대비 비트코인의 매력도를 수치 기반으로 평가하라.\n\n[데이터]\n{raw_data}"
    }
    
    foundation_opinions = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(ask_expert, name, prompt) for name, prompt in macro_geo_prompts.items()]
        for future in as_completed(futures):
            name, res = future.result()
            foundation_opinions[name] = res

    foundation_context = "\n\n".join([f"[{k}]\n{v}" for k, v in foundation_opinions.items()])
    
    tech_prompts = {
        "스캘핑 전문가": f"앞선 분석과 [수치화된 팩트 데이터]의 파이썬 연산 VWAP, RSI, 밴드 상/하단을 정확히 읽고 1~15분 숏/롱 타점을 잡아라. 횡보장이면 박스권 역추세, 추세장이면 돌파 매매를 제안하라.\n\n[거시/지정학]\n{foundation_context}\n[팩트 데이터]: {raw_data}",
        "단타 전문가": f"수치화된 OI(미결제약정)와 펀딩비를 고려하여 세력의 숏 스퀴즈/롱 스퀴즈 가능성을 계산하고 리스크 대비 확률이 높은 타점을 잡아라.\n\n[거시/지정학]\n{foundation_context}\n[팩트 데이터]: {raw_data}",
        "단기 스윙 전문가": f"1~2주 단기 채널 지지선과 저항선을 팩트 기반으로 명시하라.\n\n[거시/지정학]\n{foundation_context}\n[팩트 데이터]: {raw_data}",
        "추세매매 전문가": f"RSI와 밴드폭 수치를 바탕으로 현 추세의 지속 여부 및 변곡점을 분석하라.\n\n[거시/지정학]\n{foundation_context}\n[팩트 데이터]: {raw_data}"
    }

    tech_opinions = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(ask_expert, name, prompt) for name, prompt in tech_prompts.items()]
        for future in as_completed(futures):
            name, res = future.result()
            tech_opinions[name] = res

    all_opinions_dict = {**foundation_opinions, **tech_opinions}
    all_opinions_text = "\n\n".join([f"[{k}]\n{v}" for k, v in all_opinions_dict.items()])
    
    scap_prompt = f"너는 수십억 운용 수석 스캘퍼. [악마의 변호인: 타점 실패 확률]을 먼저 검증하고 팩트 지표가 충족 안 되면 '관망'하라.\n[의견]\n{all_opinions_text}\n[양식]\n1. 리스크 팩트 점검:\n2. 최종 방향 (롱/숏/관망):\n3. 레버리지:\n4. 진입가:\n5. 손절가/익절가:"
    trend_prompt = f"너는 단기 스윙 팀장. [악마의 변호인: 추세 속임수 확률]을 검증하고 어설프면 '관망'하라.\n[의견]\n{all_opinions_text}\n[양식]\n1. 리스크 팩트 점검:\n2. 최종 방향 (롱/숏/관망):\n3. 레버리지:\n4. 진입가:\n5. 목표가/손절가:"

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

    msg_3_part1 = f"⏰ [1/2] 거시/지정학/스캘핑 (팩트수치 기반)\n\n[거시경제]\n{all_opinions_dict.get('거시경제 전문가', '')}\n\n[지정학]\n{all_opinions_dict.get('지정학 리스크 전문가', '')}\n\n[스캘핑]\n{all_opinions_dict.get('스캘핑 전문가', '')}"
    msg_3_part2 = f"⏰ [2/2] 단타/스윙/추세 (팩트수치 기반)\n\n[단타]\n{all_opinions_dict.get('단타 전문가', '')}\n\n[단기 스윙]\n{all_opinions_dict.get('단기 스윙 전문가', '')}\n\n[추세매매]\n{all_opinions_dict.get('추세매매 전문가', '')}"
    
    send_telegram_message(msg_3_part1)
    time.sleep(1)
    send_telegram_message(msg_3_part2)

    tele_msg_scap = f"🔥 [최종 퀀트 오더: 단타/스캘핑] 🔥\n\n현재가: {current_price}\n\n{scap_order}"
    tele_msg_trend = f"📈 [최종 퀀트 오더: 단기 스윙] 📈\n\n현재가: {current_price}\n\n{trend_order}"
    
    time.sleep(1)
    send_telegram_message(tele_msg_scap)
    time.sleep(1)
    send_telegram_message(tele_msg_trend)
    
    return all_opinions_dict, scap_order, trend_order

if __name__ == "__main__":
    try:
        import streamlit.web.cli
        is_streamlit = True
    except ImportError:
        is_streamlit = False

    if "streamlit" in os.environ.get("_", "") or os.environ.get("STREAMLIT_SERVER_PORT"):
        st.set_page_config(page_title="AI 실전 퀀트 봇", page_icon="🤖", layout="wide")
        st.title("🤖 AI 트레이딩 봇 (100% 수치 팩트 퀀트 버전)")
        st.write("파이썬 수학 연산을 통해 계산된 RSI, VWAP, 밴드 수치를 AI에게 강제로 먹여 환각을 차단합니다.")

        if st.button("🚀 실전 퀀트 브리핑 즉시 실행", type="primary"):
            if not client:
                st.error("API 키가 없습니다.")
                st.stop()
            with st.status("실시간 OHLCV 연산 및 퀀트 분석 중...", expanded=True):
                try:
                    curr_price, raw_data = get_market_data()
                    all_ops, scap, trend = generate_and_send_briefing(curr_price, raw_data)
                    st.success("텔레그램 전송 완료!")
                    
                    st.divider()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("⚡ [단타용] 팀장 오더")
                        st.success(scap)
                    with col2:
                        st.subheader("📈 [단기 스윙용] 팀장 오더")
                        st.info(trend)
                except Exception as e:
                    st.error(f"오류 발생: {e}")
    else:
        print(f"[{datetime.now()}] 🤖 퀀트 수치 연산 및 정각 브리핑 시작...")
        if client:
            try:
                curr_price, raw_data = get_market_data()
                generate_and_send_briefing(curr_price, raw_data)
                print("✅ 텔레그램 전송 완료.")
            except Exception as e:
                print(f"❌ 오류: {e}")