import streamlit as st
import google.generativeai as genai
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import os
import feedparser
from urllib.parse import quote
from dotenv import load_dotenv
import scorecard as sc

# 1. 초기 설정
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try: api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception: api_key = None
genai.configure(api_key=api_key or "missing")
model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

def ask_ai(prompt):
    """Gemini 호출. 실패하면 (None, 오류메시지) 반환"""
    if not api_key:
        return None, "GEMINI_API_KEY가 설정되지 않았습니다. .env 파일이나 Streamlit Secrets에 키를 넣어주세요."
    try:
        return model.generate_content(prompt).text, None
    except Exception as e:
        return None, f"AI 호출 실패 ({type(e).__name__}): {e}"

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
    text, _ = ask_ai(f"Find Yahoo Finance ticker for '{name}'. Return ONLY ticker.")
    if text: return text.strip().strip('`').split()[0]
    try:
        quotes = yf.Search(name, max_results=1).quotes
        if quotes: return quotes[0]['symbol']
    except Exception: pass
    return name

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

@st.cache_data(ttl=1800, show_spinner=False)
def get_news_sentiment(name, eng_name, is_kr):
    """실시간 뉴스 검색 + AI 감성 점수 (30분 캐시)"""
    news = get_google_news(f"{name} 주가", lang='ko')
    if not is_kr:
        news += get_google_news(f"{eng_name} stock", lang='en')
    headlines = [n.title for n in news]
    links = [(n.title, n.link) for n in news]
    if not headlines:
        return None, links
    text, _ = ask_ai(sc.sentiment_prompt(name, headlines))
    return sc.parse_sentiment(text), links

def render_score_table(items):
    rows = []
    for name, value, pts, max_pts, note in items:
        rows.append({"항목": name, "현재값": value,
                     "점수": "-" if pts is None else f"{pts:.1f} / {max_pts:g}",
                     "해석": note})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

exchange_rate = get_exchange_rate()

# 5. 메인 화면
st.markdown("<h3 style='text-align: center; margin-bottom: 30px; color: #202124;'>📈 PRO Finance AI</h3>", unsafe_allow_html=True)

# [수정됨] 돋보기 버튼 제거, 검색창을 중앙에 넓게 배치
col_spacer1, col_input, col_spacer2 = st.columns([1, 6, 1])

with col_input:
    # 돋보기 없이 깔끔한 입력창
    user_input = st.text_input("검색", placeholder="종목명 입력 후 Enter (예: 엔비디아)", label_visibility="collapsed")

if not api_key:
    st.warning("⚠️ GEMINI_API_KEY가 없어 AI 기능(팩트체크 채팅, 뉴스 요약, 뉴스 심리 점수)이 꺼져 있습니다. 시세·차트·기술적/펀더멘털 점수는 정상 동작합니다.")

if user_input:
    with st.spinner('검색 중...'):
        ticker = get_ticker_auto(user_input)
    
    try:
        stock_obj = yf.Ticker(ticker)
        try: info = stock_obj.info or {}
        except Exception: info = {}
        hist = stock_obj.history(period="5d")
        if hist.empty:
            st.error(f"'{user_input}' → 티커 '{ticker}' 의 시세 데이터를 찾지 못했습니다. 종목명을 다르게 입력하거나 티커(예: NVDA, 005930.KS)로 검색해 보세요.")
        
        if not hist.empty:
            if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
            
            current_p = float(hist['Close'].iloc[-1])
            prev_p = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_p
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

            tab0, tab1, tab2, tab3 = st.tabs(["🎯 매수 타이밍", "💡 팩트체크", "📰 뉴스", "📈 차트"])

            with tab0:
                try:
                    st.markdown("#### 🎯 매수 타이밍 평가표")
                    with st.expander("⚙️ 가중치 설정", expanded=False):
                        w1, w2, w3 = st.columns(3)
                        w_tech = w1.slider("기술적 분석", 0, 100, 40, 5)
                        w_fund = w2.slider("펀더멘털/전망", 0, 100, 40, 5)
                        w_senti = w3.slider("뉴스 심리", 0, 100, 20, 5)

                    with st.spinner('지표·실적·뉴스 분석 중...'):
                        price_h = stock_obj.history(period="1y")
                        if isinstance(price_h.columns, pd.MultiIndex): price_h.columns = price_h.columns.get_level_values(0)
                        ind = sc.add_indicators(price_h)
                        tech_score, tech_items = sc.technical_score(ind)
                        fund_score, fund_items = sc.fundamental_score(info, current_p, sc.get_eps_growth_next_year(stock_obj))
                        senti, news_links = get_news_sentiment(user_input, info.get('shortName', ticker), is_kr_stock)
                        senti_score = senti['score'] if senti else None

                    total, eff_w = sc.combine_scores(tech_score, fund_score, senti_score,
                                                     {'tech': w_tech, 'fund': w_fund, 'senti': w_senti})
                    if total is None:
                        st.warning("가중치를 하나 이상 0보다 크게 설정하세요.")
                    else:
                        grade, desc, color = sc.verdict(total)
                        g_col, s_col = st.columns([1, 1])
                        with g_col:
                            gauge = go.Figure(go.Indicator(
                                mode="gauge+number", value=total, number={'suffix': "점"},
                                gauge={'axis': {'range': [0, 100]}, 'bar': {'color': color},
                                       'steps': [{'range': [0, 30], 'color': '#FEE2E2'}, {'range': [30, 45], 'color': '#FFEDD5'},
                                                 {'range': [45, 60], 'color': '#FEF9C3'}, {'range': [60, 75], 'color': '#ECFCCB'},
                                                 {'range': [75, 100], 'color': '#DCFCE7'}]}))
                            gauge.update_layout(height=260, margin=dict(l=20, r=20, t=20, b=0))
                            st.plotly_chart(gauge, use_container_width=True)
                        with s_col:
                            st.markdown(f"<h3 style='color:{color};margin-top:30px;'>{grade}</h3><p>{desc}</p>", unsafe_allow_html=True)
                            weight_txt = " · ".join(f"{k} {v*100:.0f}%" for k, v in eff_w.items())
                            st.caption(f"적용 가중치: {weight_txt}")

                        c1, c2, c3 = st.columns(3)
                        c1.metric("📊 기술적 분석", f"{tech_score:.0f}점")
                        c2.metric("🏢 펀더멘털/전망", f"{fund_score:.0f}점" if fund_score is not None else "평가 불가")
                        c3.metric("📰 뉴스 심리", f"{senti_score}점" if senti_score is not None else "평가 불가")

                    st.markdown("##### 📊 기술적 분석 상세")
                    render_score_table(tech_items)

                    st.markdown("##### 🏢 펀더멘털 · 실적 · 향후 예상치 상세")
                    if fund_score is None:
                        st.info("ETF·코인·원자재 등 재무 데이터가 없는 종목은 펀더멘털 점수를 제외하고 계산합니다.")
                    render_score_table(fund_items)

                    st.markdown("##### 📰 뉴스 심리 상세")
                    if senti:
                        st.write(f"**요약:** {senti['summary']}")
                        p_col, n_col = st.columns(2)
                        p_col.markdown("**👍 긍정 요인**\n" + "".join(f"\n- {x}" for x in senti['positive']))
                        n_col.markdown("**👎 부정 요인**\n" + "".join(f"\n- {x}" for x in senti['negative']))
                    else:
                        st.info("뉴스 감성 분석을 수행하지 못해 뉴스 심리 점수를 제외했습니다.")
                    if news_links:
                        with st.expander("분석에 사용된 뉴스"):
                            for title, link in news_links: st.write(f"- [{title}]({link})")

                    st.markdown("##### 📈 기술적 지표 차트")
                    ch = ind.tail(180).reset_index()
                    fig_ta = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.03)
                    fig_ta.add_trace(go.Candlestick(x=ch['Date'], open=ch['Open'], high=ch['High'], low=ch['Low'], close=ch['Close'],
                                                    increasing_line_color='#22C55E', decreasing_line_color='#EF4444', name='가격'), row=1, col=1)
                    fig_ta.add_trace(go.Scatter(x=ch['Date'], y=ch['BB_UP'], line=dict(color='#94A3B8', width=1), name='BB 상단'), row=1, col=1)
                    fig_ta.add_trace(go.Scatter(x=ch['Date'], y=ch['BB_LOW'], line=dict(color='#94A3B8', width=1), fill='tonexty',
                                                fillcolor='rgba(148,163,184,0.12)', name='BB 하단'), row=1, col=1)
                    fig_ta.add_trace(go.Scatter(x=ch['Date'], y=ch['MA20'], line=dict(color='#F59E0B', width=1.2), name='MA20'), row=1, col=1)
                    fig_ta.add_trace(go.Scatter(x=ch['Date'], y=ch['MA60'], line=dict(color='#8B5CF6', width=1.2), name='MA60'), row=1, col=1)
                    fig_ta.add_trace(go.Scatter(x=ch['Date'], y=ch['RSI'], line=dict(color='#4285F4'), name='RSI'), row=2, col=1)
                    fig_ta.add_hline(y=70, line=dict(color='#EF4444', dash='dot'), row=2, col=1)
                    fig_ta.add_hline(y=30, line=dict(color='#22C55E', dash='dot'), row=2, col=1)
                    fig_ta.add_trace(go.Bar(x=ch['Date'], y=ch['MACD_HIST'], name='MACD Hist',
                                            marker_color=['#22C55E' if v >= 0 else '#EF4444' for v in ch['MACD_HIST'].fillna(0)]), row=3, col=1)
                    fig_ta.add_trace(go.Scatter(x=ch['Date'], y=ch['MACD'], line=dict(color='#0EA5E9', width=1.2), name='MACD'), row=3, col=1)
                    fig_ta.add_trace(go.Scatter(x=ch['Date'], y=ch['MACD_SIGNAL'], line=dict(color='#F97316', width=1.2), name='Signal'), row=3, col=1)
                    fig_ta.update_layout(template="plotly_white", height=650, xaxis_rangeslider_visible=False, showlegend=False,
                                         margin=dict(l=0, r=0, t=10, b=0))
                    fig_ta.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
                    fig_ta.update_yaxes(title_text="MACD", row=3, col=1)
                    st.plotly_chart(fig_ta, use_container_width=True)
                    st.caption("※ 본 점수는 공개 데이터 기반 참고 지표이며 투자 권유가 아닙니다. 최종 판단과 책임은 투자자 본인에게 있습니다.")
                except Exception as e:
                    st.error(f"매수 타이밍 분석 중 오류가 발생했습니다: {type(e).__name__}: {e}")


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
                        text, err = ask_ai(prompt)
                        if err: st.error(err)
                        else: st.write(text)
                        
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
                            text, err = ask_ai(f"{user_input} 뉴스 3줄 요약:\n{txt}")
                            if err: st.error(err)
                            else: st.info(text)
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

    except Exception as e:
        st.error(f"'{user_input}' (티커: {ticker}) 조회 중 오류가 발생했습니다: {type(e).__name__}: {e}")