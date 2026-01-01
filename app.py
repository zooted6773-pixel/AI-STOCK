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

# 2. 디자인 설정 (깔끔한 화이트 테마)
st.set_page_config(page_title="PRO INVESTOR AI", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    /* 전체 배경 및 텍스트: 화이트 & 블랙 */
    html, body, [class*="css"], .stApp { 
        background-color: #FFFFFF !important; 
        color: #000000 !important; 
    }
    
    /* 사이드바 스타일 */
    section[data-testid="stSidebar"] { 
        background-color: #F8F9FA !important; 
        border-right: 1px solid #EEEEEE !important; 
    }

    /* 지표 박스 크기 통일 (칼각 정렬) */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #EEEEEE !important;
        border-radius: 12px !important;
        padding: 20px !important;
        min-height: 130px !important; /* 높이 고정 */
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02) !important;
    }

    /* 버튼 스타일 (레드 포인트) */
    div.stButton > button:first-child { 
        background-color: #FF0000 !important; 
        color: #FFFFFF !important; 
        border-radius: 8px !important; 
        font-weight: 700; 
        width: 100%; 
        height: 45px; 
        border: none; 
    }
    </style>
    """, unsafe_allow_html=True)

# 3. 보조 함수 (환율, 뉴스)
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        df = yf.download("USDKRW=X", period="1d")
        return float(df['Close'].iloc[-1])
    except: return 1360.0

def get_google_news(search_query):
    try:
        encoded = quote(search_query)
        # 한국어 뉴스 검색
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        return feed.entries[:10]
    except: return []

exchange_rate = get_exchange_rate()

# 4. 사이드바 구성
with st.sidebar:
    st.markdown("<h2 style='color: black;'>📈 PRO AI</h2>", unsafe_allow_html=True)
    menu = st.radio("메뉴 선택", ["💡 지식 Q&A", "📰 구글 뉴스 분석", "📈 실시간 차트"], index=2)
    st.divider()
    ticker = st.text_input("종목 코드 (Ticker)", value="AAPL").upper()
    if menu == "📈 실시간 차트":
        period = st.select_slider("조회 기간", options=["1mo", "3mo", "6mo", "1y", "5y"], value="1y")

# 5. 메인 로직
try:
    stock_obj = yf.Ticker(ticker)
    info = stock_obj.info
    hist = stock_obj.history(period="5d")
    
    if not hist.empty:
        # 데이터 정리
        if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
        
        current_p = float(hist['Close'].iloc[-1])
        prev_p = float(hist['Close'].iloc[-2])
        change_pct = ((current_p - prev_p) / prev_p) * 100
        
        current_p_krw = current_p * exchange_rate
        high_p_krw = float(info.get('fiftyTwoWeekHigh', 0)) * exchange_rate

        # 종목명 표시
        st.title(f"{info.get('shortName', ticker)}")
        
        # 지표 박스 (원화/달러 병기)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("현재가", f"₩{current_p_krw:,.0f} (${current_p:,.2f})", f"{change_pct:+.2f}%")
        m2.metric("52주 최고가", f"₩{high_p_krw:,.0f} (${info.get('fiftyTwoWeekHigh', 0):,.2f})")
        m3.metric("시가총액", f"${info.get('marketCap', 0)/1e12:.2f}T")
        m4.metric("P/E Ratio", f"{info.get('trailingPE', 0):.2f}")
        
        st.divider()

        # 메뉴별 기능
        if menu == "📰 구글 뉴스 분석":
            st.subheader("🌐 실시간 구글 뉴스 분석")
            if st.button("🔥 뉴스 하이라이트 요약 시작"):
                with st.spinner('구글 뉴스를 분석 중입니다...'):
                    news = get_google_news(f"{info.get('shortName', ticker)} 주가 전망")
                    if news:
                        news_txt = "\n".join([f"- {n.title}" for n in news[:5]])
                        res = model.generate_content(f"{ticker} 최신 뉴스 기반 투자 리포트 작성해줘:\n{news_txt}")
                        st.info(res.text)
                        
                        # 원본 링크 표시
                        with st.expander("🔗 원본 뉴스 링크"):
                            for n in news[:5]: st.write(f"- [{n.title}]({n.link})")
                    else: st.warning("최신 뉴스를 가져오지 못했습니다.")

        elif menu == "💡 지식 Q&A":
            st.subheader("💡 경제 지식 Q&A")
            user_q = st.text_input("질문을 입력하세요")
            if st.button("질문하기"):
                with st.spinner('AI 생각 중...'):
                    res = model.generate_content(f"경제 전문가로서 답변해줘: {user_q}")
                    st.write(res.text)

        elif menu == "📈 실시간 차트":
            st.subheader(f"📈 {ticker} 차트 ({period})")
            full_h = stock_obj.history(period=period).reset_index()
            if isinstance(full_h.columns, pd.MultiIndex): full_h.columns = full_h.columns.get_level_values(0)
            
            # 깔끔한 화이트 테마 차트
            fig = go.Figure(data=[go.Candlestick(x=full_h['Date'], open=full_h['Open'], high=full_h['High'], low=full_h['Low'], close=full_h['Close'], increasing_line_color='#22C55E', decreasing_line_color='#EF4444')])
            fig.update_layout(template="plotly_white", height=600, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig, use_container_width=True)
            
except Exception as e:
    st.error(f"실행 중 오류가 발생했습니다: {e}")