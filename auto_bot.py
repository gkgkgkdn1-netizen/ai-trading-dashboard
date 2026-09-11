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

# 전통금융(TradFi) 수집 (15분봉 동향)
def fetch_tradfi_data():
    try:
        tickers = {"나스닥": "NQ=F", "원유(WTI)": "CL=F", "미 국채 10년물": "^TNX"}
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
        return "전통금융 수집 지연"

# 매크로 지표 중심 뉴스
def fetch_macro_news():
    news_summaries = []
    try:
        query = urllib.parse.quote("CPI OR PPI OR FOMC OR 트럼프 OR Bitcoin")
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
    return f"[최신 매크로 뉴스]\n" + ("\n".join(news_summaries) if news_summaries else "뉴스 수집 지연")

# 매매일지 저장
def save_trading_journal(data_record):
    try:
        journal_data = []
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                journal_data = json.load(f)
        journal_data.append(data_record)
        journal_data = journal_data[-100:]
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(journal_data, f, ensure_ascii=False, indent=4)
    except:
        pass

# 🔥 [수정됨] AI 오답노트 - 원점 재검토 및 객관적 분석 강제
def generate_ai_feedback(current_price):
    if not os.path.exists(JOURNAL_FILE):
        return "과거 매매 기록 없음 (첫 분석)"
    try:
        with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
            journal_data = json.load(f)
        
        if not journal_data:
            return "과거 매매 기록 없음"

        recent_entries = journal_data[-3:]
        feedback_texts = []
        
        for i, entry in enumerate(recent_entries):
            past_price = float(entry.get("price", current_price))
            scap_res = entry.get("scap_result", "")
            
            direction = "관망"
            if "방향: 롱" in scap_res or "방향: Long" in scap_res or "방향 (롱" in scap_res:
                direction = "롱"
            elif "방향: 숏" in scap_res or "방향: Short" in scap_res or "방향 (숏" in scap_res:
                direction = "숏"
            
            if direction == "관망":
                feedback_texts.append(f"과거 {i+1}: 관망 지시함 (당시 {past_price:.1f} -> 현재 {current_price:.1f})")
                continue

            is_win = False
            if direction == "롱" and current_price > past_price: is_win = True
            if direction == "숏" and current_price < past_price: is_win = True

            result_str = "적중 성공✅" if is_win else "예측 실패❌ (반대 방향 진행)"
            feedback_texts.append(f"과거 {i+1}: {direction} 지시 -> 결과: {result_str} (당시 {past_price:.1f} -> 현재 {current_price:.1f})")
        
        # 🚨 대표님 지시사항 반영: 무지성 스위칭 방지, 제로베이스 분석 강제
        warning_msg = (
            "\n\n🚨 [자가 학습 경고]: 만약 이전 예측이 실패했다면, 너의 기존 분석 논리에 편향(Bias)이 있었다는 뜻이다. "
            "롱이 실패했다고 무작정 숏으로 스위칭하는 뇌동매매를 절대 하지 마라. "
            "기존의 편향을 전면 폐기하고, 오직 현재의 팩트 지표(OBI, VWAP, RSI 등)를 '제로베이스(원점)'에서 철저히 재검토하여 "
            "가장 객관적이고 올바른 시장 구조(방향)를 새롭게 찾아내라. 만약 방향이 불확실하다면 무조건 '관망(No Position)'을 지시하라!"
        )
        return "\n".join(feedback_texts) + warning_msg
    except Exception as e:
        return f"피드백 분석 오류: {e}"

def ask_expert(name, prompt):
    try:
        res = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        if res and res.text:
            return name, res.text
    except Exception as e:
        pass
    return name, "분석 오류 또는 응답 지연"

# 팩트 퀀트 연산 (RSI, VWAP, BB 등)
def get_quant_indicators(exchange):
    try:
        ohlcv = exchange.fetch_ohlcv(COIN_SYMBOL, timeframe='15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (df['tp'] * df['volume']).cumsum() / df['volume'].cumsum()
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        df['sma20'] = df['close'].rolling(window=20).mean()
        df['std20'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['sma20'] + (df['std20'] * 2)
        df['bb_lower'] = df['sma20'] - (df['std20'] * 2)
        
        last = df.iloc[-1]
        bb_width = (last['bb_upper'] - last['bb_lower']) / last['sma20'] * 100
        regime = "추세장 (변동성 폭발)" if bb_width > 2.5 else "횡보장 (변동성 수렴중)"

        return {
            "rsi": f"{last['rsi']:.1f}",
            "vwap": f"{last['vwap']:.1f}",
            "bb_width": f"{bb_width:.2f}%",
            "regime": regime
        }
    except Exception as e:
        return {"error": f"퀀트 연산 실패: {e}"}

def get_market_data():
    exchange = ccxt.bitget()
    ticker = exchange.fetch_ticker(COIN_SYMBOL)
    current_price = ticker['last']
    
    # 100호가 OBI (Order Book Imbalance) 연산
    try:
        orderbook = exchange.fetch_order_book(COIN_SYMBOL, limit=100)
        bid_vol = sum([vol for price, vol in orderbook['bids']]) 
        ask_vol = sum([vol for price, vol in orderbook['asks']]) 
        obi = ((bid_vol - ask_vol) / (bid_vol + ask_vol)) * 100
        obi_status = f"{obi:.1f}% (" + ("매수 우위/숏커버 주의" if obi > 10 else "매도 우위/하락 압력" if obi < -10 else "매수/매도 팽팽함") + ")"
    except:
        obi_status = "호가창 분석 지연"

    funding_rate = "정보 없음"
    open_interest = "정보 없음"
    try:
        funding_rate = exchange.fetch_funding_rate(COIN_SYMBOL).get('fundingRate', '정보 없음')
        open_interest = exchange.fetch_open_interest(COIN_SYMBOL).get('openInterestAmount', '정보 없음')
    except:
        pass

    quant = get_quant_indicators(exchange)
    quant_text = (
        f"- 장세 판단: {quant.get('regime', 'N/A')}\n"
        f"- 15m RSI: {quant.get('rsi', 'N/A')} (30이하 과매도, 70이상 과매수)\n"
        f"- 15m VWAP 기준가: {quant.get('vwap', 'N/A')}\n"
    ) if "error" not in quant else "지표 연산 오류"

    macro_news = fetch_macro_news()
    tradfi_data = fetch_tradfi_data()
    
    ai_feedback_report = generate_ai_feedback(current_price)
    
    raw_data = (
        f"🚨 [수치화된 팩트 데이터] 상상 금지. 아래 팩트만 신뢰하라.\n\n"
        f"[코인 실시간 체결/호가 팩트]\n"
        f"현재 가격: {current_price} USDT\n"
        f"펀딩비: {funding_rate} / 미결제약정(OI): {open_interest}\n"
        f"🔥 100호가 OBI(순매수 압력): {obi_status}\n\n"
        f"💻 [파이썬 퀀트 지표 (15분봉)]\n{quant_text}\n\n"
        f"[전통금융 동향]\n{tradfi_data}\n\n"
        f"{macro_news}"
    )
    return current_price, raw_data, ai_feedback_report

def generate_and_send_briefing(current_price, raw_data, ai_feedback_report):
    macro_geo_prompts = {
        "거시경제 전문가": f"너는 거시 퀀트. [데이터]를 바탕으로 <사고 과정>을 거쳐 팩트만 서술하라.\n\n[데이터]\n{raw_data}",
        "지정학 리스크 전문가": f"전통금융 자산 흐름과 비트코인 자금 유입/유출을 연관지어 분석하라.\n\n[데이터]\n{raw_data}"
    }
    
    foundation_opinions = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(ask_expert, name, prompt) for name, prompt in macro_geo_prompts.items()]
        for future in as_completed(futures):
            name, res = future.result()
            foundation_opinions[name] = res

    foundation_context = "\n\n".join([f"[{k}]\n{v}" for k, v in foundation_opinions.items()])
    
    tech_prompts = {
        "스캘핑 전문가": f"거시 분석과 [팩트 데이터]의 OBI(호가 불균형) 및 펀딩비를 보고 1~15분 숏/롱 타점을 잡아라. 허매수를 조심하라.\n\n[거시/지정학]\n{foundation_context}\n[팩트 데이터]: {raw_data}",
        "단타 전문가": f"데이 트레이더 관점에서 OI(미결제약정)와 RSI 팩트를 조합하라.\n\n[거시/지정학]\n{foundation_context}\n[팩트 데이터]: {raw_data}",
        "단기 스윙 전문가": f"1~2주 스윙 타점. 현 가격과 장세(추세/횡보) 팩트에 기반하라.\n\n[거시/지정학]\n{foundation_context}\n[팩트 데이터]: {raw_data}",
        "추세매매 전문가": f"RSI와 BB 수치를 바탕으로 변곡점을 분석하라.\n\n[거시/지정학]\n{foundation_context}\n[팩트 데이터]: {raw_data}"
    }

    tech_opinions = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(ask_expert, name, prompt) for name, prompt in tech_prompts.items()]
        for future in as_completed(futures):
            name, res = future.result()
            tech_opinions[name] = res

    all_opinions_dict = {**foundation_opinions, **tech_opinions}
    all_opinions_text = "\n\n".join([f"[{k}]\n{v}" for k, v in all_opinions_dict.items()])
    
    # 🔥 [수정됨] 팀장 프롬프트 수정
    scap_prompt = f"너는 수십억 운용 수석 스캘퍼. 먼저 아래 [AI 매매일지 피드백]을 읽어라. 과거 예측이 틀렸다면 고집 부리지 말고 팩트 지표를 제로베이스에서 재검토하여 객관적이고 정확한 방향을 새롭게 찾아라. 이후 [악마의 변호인: 리스크 점검]을 거쳐 오더를 내라.\n\n[AI 매매일지 피드백 (오답노트)]\n{ai_feedback_report}\n\n[의견]\n{all_opinions_text}\n[양식]\n1. 리스크 & 피드백 점검:\n2. 최종 방향 (롱/숏/관망):\n3. 레버리지:\n4. 진입가:\n5. 손절가/익절가:"
    
    trend_prompt = f"너는 단기 스윙 팀장. 아래 [AI 매매일지 피드백]을 읽어라. 과거 예측이 틀렸다면 방향을 원점에서 객관적으로 재검토하라. 이후 [악마의 변호인]을 거쳐 오더를 내라. 불확실하면 무조건 관망하라.\n\n[AI 매매일지 피드백 (오답노트)]\n{ai_feedback_report}\n\n[의견]\n{all_opinions_text}\n[양식]\n1. 리스크 & 피드백 점검:\n2. 최종 방향 (롱/숏/관망):\n3. 레버리지:\n4. 진입가:\n5. 목표가/손절가:"

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

    msg_3_part1 = f"⏰ [1/2] 거시/지정학/스캘핑 (OBI + 팩트수치)\n\n[거시경제]\n{all_opinions_dict.get('거시경제 전문가', '')}\n\n[지정학]\n{all_opinions_dict.get('지정학 리스크 전문가', '')}\n\n[스캘핑]\n{all_opinions_dict.get('스캘핑 전문가', '')}"
    msg_3_part2 = f"⏰ [2/2] 단타/스윙/추세 (OBI + 팩트수치)\n\n[단타]\n{all_opinions_dict.get('단타 전문가', '')}\n\n[단기 스윙]\n{all_opinions_dict.get('단기 스윙 전문가', '')}\n\n[추세매매]\n{all_opinions_dict.get('추세매매 전문가', '')}"
    
    send_telegram_message(msg_3_part1)
    time.sleep(1)
    send_telegram_message(msg_3_part2)

    tele_msg_scap = f"🔥 [최종 퀀트 오더: 단타/스캘핑] 🔥\n🤖 제로베이스 피드백 검증 완료\n\n현재가: {current_price}\n\n{scap_order}"
    tele_msg_trend = f"📈 [최종 퀀트 오더: 단기 스윙] 📈\n🤖 제로베이스 피드백 검증 완료\n\n현재가: {current_price}\n\n{trend_order}"
    
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
        st.title("🤖 AI 트레이딩 봇 (자가학습 & OBI 버전)")
        st.write("100호가 불균형(OBI) 파악 및 스스로 과거 승률을 반성하는 AI 오답노트 시스템 탑재.")

        if st.button("🚀 실전 퀀트 브리핑 즉시 실행", type="primary"):
            if not client:
                st.error("API 키가 없습니다.")
                st.stop()
            with st.status("실시간 OBI 연산 및 AI 자가 피드백 분석 중...", expanded=True):
                try:
                    curr_price, raw_data, ai_report = get_market_data()
                    st.warning(f"**[봇 내부 오답노트 분석 결과]**\n{ai_report}")
                    all_ops, scap, trend = generate_and_send_briefing(curr_price, raw_data, ai_report)
                    st.success("텔레그램 전송 완료!")
                    
                    st.divider()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("⚡ [단타용] 팀장 오더 (피드백 반영)")
                        st.success(scap)
                    with col2:
                        st.subheader("📈 [단기 스윙용] 팀장 오더 (피드백 반영)")
                        st.info(trend)
                except Exception as e:
                    st.error(f"오류 발생: {e}")
    else:
        print(f"[{datetime.now()}] 🤖 OBI 연산 및 자가 피드백 정각 브리핑 시작...")
        if client:
            try:
                curr_price, raw_data, ai_report = get_market_data()
                generate_and_send_briefing(curr_price, raw_data, ai_report)
                print("✅ 텔레그램 전송 완료.")
            except Exception as e:
                print(f"❌ 오류: {e}")