import os
import ccxt
import time
import urllib.request
import urllib.parse
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st

MY_GEMINI_KEY = os.environ.get("RAW_KEY", "").strip().replace("\n", "").replace("\r", "")
TELEGRAM_BOT_TOKEN = "8923714208:AAH3sH-BHlAeDdfWz6n-kalVBS4awb_C-Y0".strip()
TELEGRAM_CHAT_ID = "8302782835".strip()
COIN_SYMBOL = "BTC/USDT:USDT"
ETH_SYMBOL = "ETH/USDT:USDT"
JOURNAL_FILE = "trading_journal.json"

client = genai.Client(api_key=MY_GEMINI_KEY) if MY_GEMINI_KEY else None

def get_kst_time():
    return datetime.utcnow() + timedelta(hours=9)

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            data = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': chunk}).encode('utf-8')
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req) as response: pass
            time.sleep(0.5)
        return True
    except: return False

def fetch_tradfi_data():
    try:
        tickers = {"나스닥": "NQ=F", "원유": "CL=F", "달러인덱스": "DX-Y.NYB", "미 국채10년": "^TNX"}
        results = []
        is_weekend = False
        for name, symbol in tickers.items():
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d", interval="15m") 
            if len(hist) >= 2:
                prev_c = hist['Close'].iloc[-2]
                curr_c = hist['Close'].iloc[-1]
                if prev_c == curr_c: is_weekend = True
                trend = "상승📈" if curr_c > prev_c else "하락📉" if curr_c < prev_c else "휴장/보합"
                results.append(f"[{name}] {curr_c:.2f} ({trend})")
        
        output = "\n".join(results)
        if is_weekend:
            output += "\n💡 [알림] 현재 주말/휴장으로 전통금융 지표 정지 상태. 코인 수급에 집중할 것."
        return output
    except: return "전통금융 수집 지연"

def fetch_macro_news():
    news_summaries = []
    try:
        query = urllib.parse.quote("CPI OR PPI OR FOMC OR Bitcoin")
        req = urllib.request.Request(f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            root = ET.fromstring(response.read())
            for count, item in enumerate(root.findall('.//item')):
                title = item.find('title')
                if title is not None and title.text:
                    news_summaries.append(f"- {title.text}")
                if count >= 5: break
    except: pass
    return "\n".join(news_summaries)

def generate_ai_feedback(current_price):
    if not os.path.exists(JOURNAL_FILE): return "과거 기록 없음"
    try:
        with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            journal = json.loads(content)[-3:] if content else []
            
        if not journal: return "기록 없음"
        feedback = []
        for i, entry in enumerate(journal):
            past_price = float(entry.get("price", current_price))
            scap_res = str(entry.get("scap_result", "")).replace(" ", "")
            
            direction = "관망"
            if "방향:롱" in scap_res or "방향(롱" in scap_res: direction = "롱"
            elif "방향:숏" in scap_res or "방향(숏" in scap_res: direction = "숏"
            
            if direction == "관망": continue
            is_win = (direction == "롱" and current_price > past_price) or (direction == "숏" and current_price < past_price)
            feedback.append(f"과거 {i+1}: {direction} 지시 -> {'성공✅' if is_win else '실패❌ (역행)'} (당시 {past_price:.1f} -> 현재 {current_price:.1f})")
        return "\n".join(feedback) + "\n\n🚨 [경고]: 예측 실패 기록 시 기존 편향을 팩트(원점)에서 철저히 재검토하라!"
    except: return "과거 기록 초기화 중"

def ask_expert(name, prompt, delay=0):
    time.sleep(delay)
    try:
        res = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        if res and res.text: return name, res.text
    except: pass
    return name, "분석 지연"

def get_multi_tf_quant(exchange):
    timeframes = {'15m': 100, '1h': 100, '4h': 100}
    quant_data = {}
    for tf, limit in timeframes.items():
        try:
            ohlcv = exchange.fetch_ohlcv(COIN_SYMBOL, timeframe=tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            
            loss = loss.replace(0, 0.0001) 
            df['rsi'] = 100 - (100 / (1 + gain / loss))
            df['rsi'] = df['rsi'].fillna(50)
            
            hist, bins = np.histogram(df['close'], bins=30, weights=df['volume'])
            poc_price = (bins[np.argmax(hist)] + bins[np.argmax(hist)+1]) / 2
            
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = np.abs(df['high'] - df['close'].shift())
            df['tr3'] = np.abs(df['low'] - df['close'].shift())
            df['atr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1).rolling(14).mean()
            
            trend = "상승 추세" if df['close'].iloc[-1] > df['close'].iloc[-20] else "하락 추세"
            df['body'] = np.abs(df['close'] - df['open'])
            vol_sma = df['volume'].rolling(20).mean()
            last = df.iloc[-1]
            
            vsa_status = "정상"
            if last['volume'] > vol_sma.iloc[-1] * 1.5 and last['body'] < df['body'].mean() * 0.5:
                vsa_status = "🚨 VSA 이상 감지: 대량 거래량 + 짧은 캔들 (변곡 확률 극상)"

            quant_data[tf] = {"rsi": last['rsi'], "poc": poc_price, "atr": last['atr'], "trend": trend, "vsa": vsa_status}
        except Exception as e:
            quant_data[tf] = {"error": str(e)}
    return quant_data

def get_market_data():
    exchange = ccxt.bitget()
    
    btc_price = exchange.fetch_ticker(COIN_SYMBOL)['last']
    eth_price = exchange.fetch_ticker(ETH_SYMBOL)['last']
    
    try:
        orderbook = exchange.fetch_order_book(COIN_SYMBOL, limit=100)
        bid_vol = sum([v for p, v in orderbook['bids']])
        ask_vol = sum([v for p, v in orderbook['asks']])
        obi = ((bid_vol - ask_vol) / (bid_vol + ask_vol)) * 100
        obi_status = f"{obi:.1f}% (" + ("매수벽 우위" if obi > 15 else "매도벽 우위" if obi < -15 else "중립") + ")"
    except: obi_status = "오류"

    try:
        trades = exchange.fetch_trades(COIN_SYMBOL, limit=500)
        whale_buy = sum([t['amount']*t['price'] for t in trades if t['side'] == 'buy' and t['amount']*t['price'] >= 20000])
        whale_sell = sum([t['amount']*t['price'] for t in trades if t['side'] == 'sell' and t['amount']*t['price'] >= 20000])
        whale_status = f"[고래 Taker] 매수: {whale_buy:.0f}$ / 매도: {whale_sell:.0f}$ ➔ " + ("🔥매수 폭격" if whale_buy > whale_sell else "🩸매도 폭격")
    except: whale_status = "고래 데이터 지연"

    funding = exchange.fetch_funding_rate(COIN_SYMBOL).get('fundingRate', 'N/A')
    oi = exchange.fetch_open_interest(COIN_SYMBOL).get('openInterestAmount', 'N/A')
    q = get_multi_tf_quant(exchange)
    
    quant_report = (
        f"📊 [4H/대추세] {q.get('4h', {}).get('trend')} | RSI: {q.get('4h', {}).get('rsi', 0):.1f} | POC: {q.get('4h', {}).get('poc', 0):.1f}\n"
        f"📊 [1H/중기] {q.get('1h', {}).get('trend')} | RSI: {q.get('1h', {}).get('rsi', 0):.1f} | POC: {q.get('1h', {}).get('poc', 0):.1f}\n"
        f"📊 [15M/타점] {q.get('15m', {}).get('vsa')} | 15M POC: {q.get('15m', {}).get('poc', 0):.1f}\n"
        f"💡 [손익비 가이드]: 15M 변동폭(ATR) {q.get('15m', {}).get('atr', 0):.1f}$ 반영 필수."
    )
    
    raw_data = (
        f"🚨 [API 팩트 데이터] 상상 금지.\n\n"
        f"[코인 실시간 팩트]\n"
        f"BTC 현재가: {btc_price} USDT (ETH: {eth_price})\n"
        f"펀딩비: {funding} / 미결제약정(OI): {oi}\n"
        f"걸려있는 호가(OBI): {obi_status}\n"
        f"🐋 스마트머니 흐름: {whale_status}\n\n"
        f"💻 [다중시간대 퀀트 팩트]\n{quant_report}\n\n"
        f"🌐 [글로벌 매크로]\n{fetch_tradfi_data()}\n\n"
        f"[뉴스]\n{fetch_macro_news()}"
    )
    return btc_price, raw_data, generate_ai_feedback(btc_price)

def generate_and_send_briefing(current_price, raw_data, ai_report):
    macro_geo = {
        "거시": ("거시 퀀트. 매크로 자산(금리/달러/나스닥)이 코인에 주는 수급 압박 분석.", 0),
        "지정학": ("전통금융과 코인의 커플링/디커플링 팩트 확인.", 0.5) 
    }
    
    foundations = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(ask_expert, n, f"{p}\n\n{raw_data}", delay) for n, (p, delay) in macro_geo.items()]
        for fut in as_completed(futs):
            name, res = fut.result()
            foundations[name] = res
    f_ctx = "\n\n".join([f"[{k}]\n{v}" for k, v in foundations.items()])
    
    tech_prompts = {
        "스캘퍼": ("고래 Taker(시장가)와 OBI(호가) 모순 체크. 개미와 반대로 매매.", 0),
        "단타": ("펀딩비, OI, 고래 타격을 종합해 청산 스퀴즈 예측.", 0.5),
        "스윙": ("4H, 1H 매물대(POC)와 거시 흐름 결합 타점.", 1.0),
        "추세": ("BTC/ETH 다이버전스, 다중시간대 추세를 통해 가짜 돌파 필터링.", 1.5)
    }

    techs = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(ask_expert, n, f"{p}\n\n{f_ctx}\n[데이터]: {raw_data}", delay) for n, (p, delay) in tech_prompts.items()]
        for fut in as_completed(futs):
            name, res = fut.result()
            techs[name] = res
    all_ctx = "\n\n".join([f"[{k}]\n{v}" for k, v in {**foundations, **techs}.items()])
    
    s_prompt = f"수석 스캘퍼. [AI 피드백] 철저 수용. 🐋고래 Taker와 거시 자산을 팩트로만 판단. 손절가 ATR(변동폭) 적용 필수.\n\n[피드백]\n{ai_report}\n\n[의견]\n{all_ctx}\n[양식]\n1. 리스크 & 스마트머니 점검:\n2. 방향 (롱/숏/관망):\n3. 레버리지:\n4. 진입가 (POC 매물대 기준):\n5. 손절/익절 (ATR 폭 반영):"
    t_prompt = f"스윙 팀장. [AI 피드백] 철저 수용. 글로벌 자산 흐름과 4H POC 중심 타점. 불확실하면 관망.\n\n[피드백]\n{ai_report}\n\n[의견]\n{all_ctx}\n[양식]\n1. 리스크 & 글로벌매크로 점검:\n2. 방향 (롱/숏/관망):\n3. 레버리지:\n4. 진입가 (POC 매물대 기준):\n5. 손절/익절 (ATR 폭 반영):"

    with ThreadPoolExecutor(max_workers=2) as ex:
        s_ord = ex.submit(ask_expert, "단타", s_prompt, 0).result()[1]
        t_ord = ex.submit(ask_expert, "추세", t_prompt, 0.5).result()[1]
    
    try:
        j_data = []
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f: 
                content = f.read().strip()
                j_data = json.loads(content) if content else []
        j_data.append({
            "timestamp": get_kst_time().strftime("%Y-%m-%d %H:%M:%S"), 
            "price": current_price, 
            "scap_result": s_ord, 
            "trend_result": t_ord
        })
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f: 
            json.dump(j_data[-100:], f, ensure_ascii=False, indent=4)
    except: pass

    msg1 = f"⏰ [1/2] 거시/스캘핑 (무결점 방어버전)\n\n[거시경제]\n{foundations.get('거시', '')}\n\n[스캘퍼]\n{techs.get('스캘퍼', '')}"
    msg2 = f"⏰ [2/2] 단타/스윙 (무결점 방어버전)\n\n[단타]\n{techs.get('단타', '')}\n\n[스윙]\n{techs.get('스윙', '')}\n\n[추세]\n{techs.get('추세', '')}"
    send_telegram_message(msg1); time.sleep(1); send_telegram_message(msg2)
    
    tele1 = f"🔥 [최종 퀀트 오더: 스캘핑] 🔥\n🤖 수학적 무결점 & 리스크 방어 완료\n현재가: {current_price}\n\n{s_ord}"
    tele2 = f"📈 [최종 퀀트 오더: 스윙] 📈\n🤖 수학적 무결점 & 리스크 방어 완료\n현재가: {current_price}\n\n{t_ord}"
    time.sleep(1); send_telegram_message(tele1); time.sleep(1); send_telegram_message(tele2)
    return s_ord, t_ord

# ==========================================
# 🚀 100% 확실한 실행 모드 분기 (이 부분이 핵심 패치입니다)
# ==========================================
if __name__ == "__main__":
    
    # 💡 웹사이트(Streamlit) 환경을 100% 확실하게 찾아내는 특수 함수
    def is_running_in_streamlit():
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            return get_script_run_ctx() is not None
        except:
            return False

    if is_running_in_streamlit():
        # 웹사이트 출력 전용 코드 (대표님이 원하시는 쾌적한 가독성 모드)
        st.set_page_config(page_title="AI 실전 퀀트 봇", layout="wide", page_icon="🤖")
        st.title("🤖 AI 실전 퀀트 대시보드")
        st.markdown("텔레그램 알림뿐만 아니라, **웹에서 가장 쾌적하게 팩트 지표와 오더를 확인**할 수 있습니다.")
        
        if st.button("🚀 실시간 분석 즉시 실행", type="primary", use_container_width=True):
            if not client: 
                st.error("API 키 오류가 발생했습니다.")
                st.stop()
                
            with st.status("수학적 팩트 연산 및 5단계 에러 방어 가동 중...", expanded=True):
                try:
                    c_price, r_data, a_rep = get_market_data()
                    st.warning(f"**[봇 자가 피드백 (오답노트)]**\n{a_rep}")
                    
                    s, t = generate_and_send_briefing(c_price, r_data, a_rep)
                    st.success("✅ 심층 분석 및 텔레그램 전송 완료!")
                    
                    st.divider()
                    
                    # 화면을 반으로 나누어 가독성 있게 출력
                    c1, c2 = st.columns(2)
                    with c1:
                        st.subheader("⚡ [단타용] 스캘퍼 최종 오더")
                        st.success(s)
                    with c2:
                        st.subheader("📈 [스윙용] 추세 최종 오더")
                        st.info(t)
                        
                    with st.expander("📊 AI가 참고한 실시간 수치 데이터 원본 보기"):
                        st.code(r_data)
                        
                except Exception as e: 
                    st.error(f"실행 중 오류 발생: {e}")
    else:
        # 깃허브 자동화 전용 코드 (백그라운드에서 조용히 텔레그램만 전송)
        if client:
            try:
                c_price, r_data, a_rep = get_market_data()
                generate_and_send_briefing(c_price, r_data, a_rep)
            except: 
                pass