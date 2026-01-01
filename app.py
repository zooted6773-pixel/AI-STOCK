import streamlit as st
import google.generativeai as genai
import yfinance as yf
import plotly.graph_objects as go
import os
from dotenv import load_dotenv
import pandas as pd  # <-- 이 줄이 꼭 있어야 에러가 안 납니다!

# 1. API 및 모델 설정
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key or api_key == "여기에_본인의_API_키를_직접_넣으세요":
    api_key = "AIzaSy..." # 실사용 시 직접 입력하는 것이 가장 확실합니다.

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

# 2. 화면 구성 및 스타일
st.set_page_config(page_title="경제/주식 마스터 비서", page_icon="📈", layout="wide")
st.title("📊 AI 경제/주식 통합 마스터 비서")

# 세 가지 기능을 탭으로 분리
tab1, tab2, tab3 = st.tabs(["💡 지식 Q&A", "📰 뉴스 분석", "📈 실시간 차트"])

# --- 탭 1: 지식 Q&A ---
with tab1:
    st.subheader("궁금한 경제 지식을 물어보세요")
    question = st.text_input("질문", placeholder="예: 양적완화가 주식 시장에 주는 영향은?")
    if st.button("AI 분석 요청"):
        with st.spinner('답변 생성 중...'):
            try:
                response = model.generate_content(f"경제 전문가로서 아주 친절하게 답변해줘: {question}")
                st.markdown(response.text)
            except Exception as e:
                st.error(f"오류: {e}")

# --- 탭 2: 뉴스 분석 ---
with tab2:
    st.subheader("최신 뉴스 실시간 분석")
    ticker_news = st.text_input("종목 코드 입력", value="NVDA", key="news_ticker")
    if st.button("뉴스 분석 시작"):
        with st.spinner('뉴스를 수집하고 분석 중입니다...'):
            try:
                stock = yf.Ticker(ticker_news)
                news = stock.news
                if not news:
                    st.warning("최신 뉴스를 찾을 수 없습니다.")
                else:
                    news_titles = "\n".join([f"- {n.get('title') or n.get('headline')}" for n in news[:5]])
                    prompt = f"{ticker_news}의 최신 뉴스 제목들을 보고 주가 전망을 요약해줘:\n{news_titles}"
                    response = model.generate_content(prompt)
                    st.info(f"### 🤖 {ticker_news} 뉴스 분석 요약")
                    st.write(response.text)
                    with st.expander("뉴스 원문 보기"):
                        for n in news[:5]:
                            st.write(f"- [{n.get('title') or n.get('headline')}]({n.get('link')})")
            except Exception as e:
                st.error(f"뉴스 에러: {e}")

# --- 탭 3: 실시간 차트 (데이터 정밀 보정 버전) ---
with tab3:
    st.subheader("주가 변동 추이 확인")
    col1, col2 = st.columns([1, 3])
    with col1:
        ticker_chart = st.text_input("분석할 종목", value="NVDA", key="chart_ticker")
        period = st.selectbox("기간", ["1mo", "3mo", "6mo", "1y", "5y"], index=0)
    
    with col2:
        try:
            # 1. 데이터 다운로드
            data = yf.download(ticker_chart, period=period)
            
            if data.empty:
                st.error("주가 데이터를 가져올 수 없습니다. 종목 코드를 확인해 주세요.")
            else:
                # [핵심 수정] 최신 yfinance의 중복 열 이름을 정리합니다.
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                
                # 2. 인덱스 리셋 (날짜를 차트가 인식하기 쉽게 만듦)
                data = data.reset_index()

                # 3. 캔들스틱 차트 생성
                fig = go.Figure(data=[go.Candlestick(
                    x=data['Date'],
                    open=data['Open'],
                    high=data['High'],
                    low=data['Low'],
                    close=data['Close'],
                    name=ticker_chart
                )])
                
                # 4. 디자인 설정
                fig.update_layout(
                    title=f"{ticker_chart} 상세 주가 흐름",
                    yaxis_title="가격",
                    template="plotly_dark",
                    xaxis_rangeslider_visible=True, # 하단 범위 조절 바 추가
                    height=500
                )
                
                st.plotly_chart(fig, use_container_width=True)
                st.success(f"현재 {ticker_chart}의 데이터를 성공적으로 불러왔습니다.")
        except Exception as e:
            st.error(f"차트 생성 중 오류가 발생했습니다: {e}")
            
st.divider()
st.caption("제미나이 프로와 함께 만든 나만의 주식 분석 도구 v1.0")