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

# 2. 디자인 설정 (구글 스타일)
st.set_page_config(page_title="PRO INVESTOR AI", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"], .stApp { background-color: #FFFFFF !important; color: #202124 !important; font-family: 'Google Sans', sans-serif; }
    
    div[data-testid="stTextInput"] input {
        border-radius: 24px !important; border: 1px solid #dfe1e5 !important;
        padding: 15px 25px !important; font-size: 16px !important;
        box-shadow: 0 2px 5px rgba(32,33,36,0.05) !important; height: 50px !important;
    }
    div[data-testid="stTextInput"] input:focus {
        box-shadow: 0 2px 8px rgba(32,33,36,0.15) !important; border-color: #4285F4 !important; outline: none !important;
    }

    /* 버튼 스타일 */
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

# 4. 보조 함수 (한국어/영어 뉴스 동시 수집)
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        df = yf.download("USDKRW=X", period="1d")
        return float(df['Close'].iloc[-1])
    except: return 1360.0

def get_google_news(search_query, lang='ko'):
    try:
        encoded = quote(search_query)
        # 언어 설정에 따라 검색 주소 변경
        if lang == 'en':
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        else:
            url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
            
        feed = feedparser.parse(url)
        return feed.entries[:5] # 각각 5개씩
    except: return []

exchange_rate = get_exchange_rate()

# 5. 메인 화면
st.markdown("<h3 style='text-align: center; margin-bottom: 20px; color: #202124;'>📈 Google Finance AI</h3>", unsafe_allow_html=True)

col_spacer1, col_input, col_btn, col_spacer2 = st.columns([0.1, 4, 0.8, 0.1], gap="small")
with col_input:
    user_input = st.text_input("검색", placeholder="종목명 (예: 엔비디아)", label_visibility="collapsed")

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

            tab1, tab2, tab3 = st.tabs(["💡 Q&A (팩트체크)", "📰 뉴스", "📈 차트"])

            with tab1:
                st.markdown("#### 💡 AI 팩트체크 & 상담")
                user_q = st.text_input("질문 입력", placeholder="예: 인텔에 투자했다는 게 사실이야?")
                
                if st.button("답변 받기", key='qa'):
                    with st.spinner('🇺🇸 미국 원문 뉴스까지 뒤져보는 중...'):
                        
                        # [핵심] 한국 뉴스 + 미국 뉴스 동시 검색
                        news_ko = get_google_news(f"{user_input} {user_q}", lang='ko')
                        
                        # 미국 주식이면 영어로도 검색 (더 정확함)
                        news_en = []
                        if not is_kr_stock:
                            # AI에게 영어 검색어 생성을 요청해도 되지만, 간단히 종목명+질문으로 처리
                            # 더 정확하게 하려면 영문명(info['shortName'])을 사용
                            eng_name = info.get('shortName', ticker)
                            news_en = get_google_news(f"{eng_name} {user_q}", lang='en')

                        # 검색 결과 합치기
                        all_news = news_ko + news_en
                        news_context = "\n".join([f"- [{n.title}] (출처: {n.source.title if hasattr(n, 'source') else 'Google'})" for n in all_news])
                        
                        # AI에게 판단 요청
                        prompt = f"""
                        당신은 팩트체크 전문 투자 분석가입니다.
                        사용자는 '{user_input}'에 대해 질문하고 있으며, 루머인지 사실인지 확인하고 싶어합니다.
                        
                        질문: "{user_q}"
                        
                        [검색된 최신 뉴스 (한국어 및 영어)]
                        {news_context}
                        
                        [분석 가이드]
                        1. 위 뉴스 목록을 철저히 분석하여 사실 여부를 판단하세요.
                        2. 만약 뉴스에 명확한 근거가 있다면 "뉴스에 따르면~" 이라고 출처를 밝히세요.
                        3. 뉴스에도 없다면 "현재 언론에 보도된 바 없습니다"라고 명확히 하세요.
                        4. 영어 뉴스가 있다면 그 내용도 한국어로 해석해서 알려주세요.
                        """
                        res = model.generate_content(prompt)
                        st.write(res.text)
                        
                        # 참고한 뉴스 링크 보여주기
                        if all_news:
                            with st.expander("🔍 AI가 참고한 뉴스 원문 보기"):
                                for n in all_news: st.write(f"- [{n.title}]({n.link})")
                        else:
                            st.caption("관련된 최신 뉴스가 검색되지 않았습니다.")

            with tab2:
                st.markdown("#### 📰 최신 뉴스")
                if st.button("🔥 요약 리포트", key='news'):
                    with st.spinner('뉴스 수집 중...'):
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