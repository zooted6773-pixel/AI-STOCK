import streamlit as st
import google.generativeai as genai
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import os
import feedparser
from urllib.parse import quote
from dotenv import load_dotenv

# 1. 초기 설정
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY") or "AIzaSy..." 
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

# 2. 디자인 설정
st.set_page_config(page_title="PRO INVESTOR AI", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"], .stApp { background-color: #FFFFFF !important; color: #202124 !important; font-family: 'Google Sans', sans-serif; }
    
    /* 검색창 스타일 (버튼 없이 혼자 예쁘게) */
    div[data-testid="stTextInput"] input {
        border-radius: 30px !important; /* 더 둥글게 */
        border: 1px solid #dfe1e5 !important;
        padding: 15px 25px !important;
        font-size: 18px !important; /* 글자 키움 */
        text-align: center; /* 입력 텍스트 가운데 정렬 */
        box-shadow: 0 2px 5px rgba(32,33,36,0.1) !important;
        height: 60px !important; /* 높이 키움 */
        transition: all 0.3s;
    }
    div[data-testid="stTextInput"] input:focus {
        box-shadow: 0 4px 12px rgba(32,33,36,0.2) !important;
        border-color: #4285F4 !important;
        outline: none !important;
    }

    /* 나머지 버튼 스타일 (답변받기, 뉴스요약 등) */
    div.stButton > button {
        background-color: #4285F4 !important; color: #FFFFFF !important;
        border-radius: 24px !important; height: 50px !important; border: none !important;
        font-weight: 600 !important; font-size: 16px !important; width: 100% !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1) !important; transition: all 0.2s;
    }
    div.stButton > button:hover {
        background-color: #357ABD !important; box-shadow: 0 4px 8px rgba(0,0,0,0.15) !important;
    }

    .stTabs [data-baseweb="tab-list"] { gap: 20px; background-color: #FFFFFF; border-bottom: 1px solid #dfe1e5; padding-top: 10px; }
    .stTabs [data-baseweb="tab"] { height: 45px; background-color: transparent; border: none; font-weight: 600; color: #5f6368; }
    .stTabs [aria-selected="true"] { color: #4285F4 !important; border-bottom: 3px solid #4285F4 !important; }
    div[data-testid="stMetric"] { background-color: #FFFFFF !important; border: 1px solid #dfe1e5 !important; border-radius: 12px !important; padding: 15px !important; }
    .block-container { padding-top: 3rem !important; }
    </style>
    """, unsafe_allow_html=True)

# 3. AI 티커 변환기
def get_ticker_auto(name):
    name = name.strip().upper()
    stock_map = {
        "삼성전자": "005930.KS", "삼전": "005930.KS", "SK하이닉스": "000660.KS",
        "현대차": "005380.KS", "기아": "000270.KS", "네이버": "035420.KS", "카카오": "035720.KS",
        "엔비디아": "NVDA", "테슬라": "TSLA", "애플": "AAPL", "마소": "MSFT", "구글": "GOOGL",
        "비트코인": "BTC-USD", "이더리움": "ETH-USD", "금": "GC=F", "환율": "USDKRW=X"
    }
    if name in stock_map: return stock_map[name]
    try:
        response = model.generate_content(f"Find Yahoo Finance ticker for '{name}'. Return ONLY ticker.")
        return response.text.strip()
    except: return name

# 4. 보조 함수
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        df = yf.download("USDKRW=X", period="1d")
        return float(df['Close'].iloc[-1])
    except: return 1360.0

def get_google_news(search_query, lang='ko'):
    try:
        encoded = quote(search_query)
        if lang == 'en': url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        else: url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        return feed.entries[:5]
    except: return []

exchange_rate = get_exchange_rate()

# 5. 메인 화면
st.markdown("<h3 style='text-align: center; margin-bottom: 30px; color: #202124;'>📈 PRO Finance AI</h3>", unsafe_allow_html=True)

# [수정됨] 돋보기 버튼 제거, 검색창을 중앙에 넓게 배치
col_spacer1, col_input, col_spacer2 = st.columns([1, 6, 1])

with col_input:
    # 돋보기 없이 깔끔한 입력창
    user_input = st.text_input("검색", placeholder="종목명 입력 후 Enter (예: 엔비디아)", label_visibility="collapsed")

if user_input:
    with st.spinner('검색 중...'):
        ticker = get_ticker_auto(user_input)
    
    try:
        stock_obj = yf.Ticker(ticker)
        info = stock_obj.info
        hist = stock_obj.history(period="5d")
        
        if not hist.empty:
            if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
            
            current_p = float(hist['Close'].iloc[-1])
            prev_p = float(hist['Close'].iloc[-2])
            change_pct = ((current_p - prev_p) / prev_p) * 100
            
            is_kr_stock = ".KS" in ticker or ".KQ" in ticker
            price_krw = current_p if is_kr_stock else current_p * exchange_rate
            high_krw = float(info.get('fiftyTwoWeekHigh', 0))
            if not is_kr_stock: high_krw *= exchange_rate

            st.markdown("---")
            st.markdown(f"### {info.get('shortName', ticker)} <span style='font-size:16px;color:#5f6368;'>{ticker}</span>", unsafe_allow_html=True)
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("현재가", f"₩{price_krw:,.0f} (${current_p:,.2f})", f"{change_pct:+.2f}%")
            m2.metric("52주 최고", f"₩{high_krw:,.0f}")
            m3.metric("시가총액", f"${info.get('marketCap', 0)/1e12:.2f}T" if info.get('marketCap') else "-")
            m4.metric("PER", f"{info.get('trailingPE', 0):.2f}" if info.get('trailingPE') else "-")
            
            st.markdown("<br>", unsafe_allow_html=True)

            tab1, tab2, tab3 = st.tabs(["💡 팩트체크", "📰 뉴스", "📈 차트"])

            with tab1:
                st.markdown("#### 💡 AI 투자 상담 & 팩트체크")
                user_q = st.text_input("질문 입력", placeholder="예: 인텔 인수설 진짜야?")
                
                if st.button("답변 받기", key='qa'):
                    with st.spinner('🇺🇸 미국 뉴스 교차 검증 중...'):
                        news_ko = get_google_news(f"{user_input} {user_q}", lang='ko')
                        news_en = []
                        if not is_kr_stock:
                            eng_name = info.get('shortName', ticker)
                            news_en = get_google_news(f"{eng_name} {user_q}", lang='en')

                        all_news = news_ko + news_en
                        news_context = "\n".join([f"- [{n.title}] (출처: {n.source.title if hasattr(n, 'source') else 'Google'})" for n in all_news])
                        
                        prompt = f"""
                        당신은 팩트체크 전문 투자 분석가입니다.
                        사용자 질문: "{user_q}" (대상: {user_input})
                        
                        [검색된 뉴스]
                        {news_context}
                        
                        [가이드]
                        1. 뉴스에 기반해 사실 여부를 판단하세요.
                        2. 뉴스에 없으면 "보도된 바 없다"고 하세요.
                        3. 한국어로 답변하세요.
                        """
                        res = model.generate_content(prompt)
                        st.write(res.text)
                        
                        if all_news:
                            with st.expander("뉴스 출처 보기"):
                                for n in all_news[:5]: st.write(f"- [{n.title}]({n.link})")

            with tab2:
                st.markdown("#### 📰 최신 뉴스")
                if st.button("🔥 요약 리포트", key='news'):
                    with st.spinner('분석 중...'):
                        news = get_google_news(f"{user_input} 투자", lang='ko')
                        if news:
                            txt = "\n".join([f"- {n.title}" for n in news[:5]])
                            res = model.generate_content(f"{user_input} 뉴스 3줄 요약:\n{txt}")
                            st.info(res.text)
                            for n in news[:5]: st.write(f"- [{n.title}]({n.link})")
                        else: st.warning("뉴스가 없습니다.")

            with tab3:
                st.markdown("#### 📈 캔들 차트")
                period = st.select_slider("기간", options=["1mo", "3mo", "6mo", "1y", "5y"], value="1y")
                full_h = stock_obj.history(period=period).reset_index()
                if isinstance(full_h.columns, pd.MultiIndex): full_h.columns = full_h.columns.get_level_values(0)
                
                fig = go.Figure(data=[go.Candlestick(x=full_h['Date'], open=full_h['Open'], high=full_h['High'], low=full_h['Low'], close=full_h['Close'], increasing_line_color='#22C55E', decreasing_line_color='#EF4444')])
                fig.update_layout(template="plotly_white", height=400, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig, use_container_width=True)

    except Exception:
        st.error("종목을 찾을 수 없습니다.")