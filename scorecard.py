"""매수 타이밍 평가표 (Buy Timing Scorecard)

기술적 분석(RSI, 볼린저밴드, MACD, 이동평균, 스토캐스틱),
펀더멘털(밸류에이션, 성장성, 수익성, 애널리스트 전망),
뉴스 심리(실시간 뉴스 + AI 감성 분석)를 각각 0~100점으로 환산한 뒤
가중 평균으로 최종 매수 타이밍 점수를 계산한다.
"""
import json
import re

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 1. 기술적 지표 계산
# ---------------------------------------------------------------------------
def add_indicators(df):
    """OHLCV DataFrame에 기술적 지표 컬럼을 추가해서 반환."""
    df = df.copy()
    close = df['Close']

    # RSI(14) - Wilder 방식
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = (100 - 100 / (1 + rs)).fillna(100)

    # 볼린저밴드(20, 2σ)
    df['BB_MID'] = close.rolling(20).mean()
    std = close.rolling(20).std()
    df['BB_UP'] = df['BB_MID'] + 2 * std
    df['BB_LOW'] = df['BB_MID'] - 2 * std
    df['BB_PCTB'] = (close - df['BB_LOW']) / (df['BB_UP'] - df['BB_LOW'])
    df['BB_WIDTH'] = (df['BB_UP'] - df['BB_LOW']) / df['BB_MID']

    # MACD(12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_HIST'] = df['MACD'] - df['MACD_SIGNAL']

    # 이동평균
    for n in (20, 60, 120):
        df[f'MA{n}'] = close.rolling(n).mean()

    # 스토캐스틱 슬로우(14, 3)
    low14 = df['Low'].rolling(14).min()
    high14 = df['High'].rolling(14).max()
    fast_k = (close - low14) / (high14 - low14) * 100
    df['STOCH_K'] = fast_k.rolling(3).mean()
    df['STOCH_D'] = df['STOCH_K'].rolling(3).mean()

    # 거래량 비율 (오늘 거래량 / 20일 평균)
    if 'Volume' in df:
        df['VOL_RATIO'] = df['Volume'] / df['Volume'].rolling(20).mean()

    return df


def _valid(x):
    return x is not None and not (isinstance(x, float) and np.isnan(x))


def _interp(x, xp, fp):
    """구간 선형 보간 (xp는 오름차순)."""
    return float(np.interp(x, xp, fp))


# ---------------------------------------------------------------------------
# 2. 기술적 분석 점수 (100점 만점)
# ---------------------------------------------------------------------------
def technical_score(df):
    """지표가 추가된 DataFrame을 받아 (총점, 항목별 리스트) 반환.

    항목: (이름, 현재값 표시, 획득점수, 배점, 해석)
    """
    last = df.iloc[-1]
    items = []

    # RSI (25점): 과매도일수록 고득점
    rsi = last.get('RSI')
    if _valid(rsi):
        pts = _interp(rsi, [20, 30, 50, 70, 80], [25, 22, 12, 2, 0])
        if rsi <= 30:
            note = '과매도 구간 – 반등 가능성'
        elif rsi >= 70:
            note = '과매수 구간 – 추격매수 주의'
        else:
            note = '중립 구간'
        items.append(('RSI(14)', f'{rsi:.1f}', pts, 25, note))
    else:
        items.append(('RSI(14)', '-', 12.5, 25, '데이터 부족 (중립 처리)'))

    # 볼린저밴드 %B (25점): 하단 밴드 근접/이탈일수록 고득점
    pctb = last.get('BB_PCTB')
    if _valid(pctb):
        pts = _interp(pctb, [-0.1, 0.0, 0.5, 1.0, 1.1], [25, 23, 12, 2, 0])
        if pctb <= 0.05:
            note = '하단 밴드 터치/이탈 – 저점 매수 구간'
        elif pctb >= 0.95:
            note = '상단 밴드 터치 – 단기 과열'
        elif pctb < 0.5:
            note = '중심선 아래 – 상대적 저가'
        else:
            note = '중심선 위 – 상대적 고가'
        width = last.get('BB_WIDTH')
        if _valid(width) and width < df['BB_WIDTH'].tail(120).quantile(0.2):
            note += ' / 밴드 수축(변동성 확대 임박)'
        items.append(('볼린저밴드 %B', f'{pctb:.2f}', pts, 25, note))
    else:
        items.append(('볼린저밴드 %B', '-', 12.5, 25, '데이터 부족 (중립 처리)'))

    # MACD (20점): 골든크로스/히스토그램 반등
    hist = df['MACD_HIST'].dropna()
    if len(hist) >= 6:
        h_now, h_prev = hist.iloc[-1], hist.iloc[-2]
        recent_cross = ((hist.iloc[-6:-1] < 0) & (h_now > 0)).any()
        if recent_cross:
            pts, note = 20, '최근 골든크로스 발생 – 매수 신호'
        elif h_now > 0 and h_now >= h_prev:
            pts, note = 15, '시그널선 위 + 상승 모멘텀 강화'
        elif h_now < 0 and h_now > h_prev:
            pts, note = 13, '시그널선 아래지만 하락세 둔화 – 바닥 다지기'
        elif h_now > 0:
            pts, note = 8, '시그널선 위지만 모멘텀 약화'
        else:
            pts, note = 2, '데드크로스 구간 – 하락 모멘텀'
        items.append(('MACD', f'{h_now:+.3f}', pts, 20, note))
    else:
        items.append(('MACD', '-', 10, 20, '데이터 부족 (중립 처리)'))

    # 추세/이동평균 (20점): 장기 상승추세 속 눌림목을 가장 좋게 평가
    close = last['Close']
    ma20, ma60, ma120 = last.get('MA20'), last.get('MA60'), last.get('MA120')
    if _valid(ma20) and _valid(ma60):
        pts, notes = 0.0, []
        if _valid(ma120):
            if close > ma120:
                pts += 8
                notes.append('120일선 위(장기 상승추세)')
            else:
                notes.append('120일선 아래(장기 약세)')
        else:
            pts += 4
        if ma20 > ma60:
            pts += 5
            notes.append('정배열(20>60)')
        else:
            notes.append('역배열(20<60)')
        gap = (close / ma20 - 1) * 100
        pts += _interp(gap, [-8, -3, 0, 5, 10], [7, 7, 5, 2, 0])
        notes.append(f'20일선 이격 {gap:+.1f}%')
        items.append(('추세/이동평균', f'{gap:+.1f}%', pts, 20, ', '.join(notes)))
    else:
        items.append(('추세/이동평균', '-', 10, 20, '데이터 부족 (중립 처리)'))

    # 스토캐스틱 (10점)
    k, d = last.get('STOCH_K'), last.get('STOCH_D')
    if _valid(k) and _valid(d):
        pts = _interp(k, [10, 20, 50, 80, 90], [8, 7, 4, 1, 0])
        note = '과매도' if k < 20 else ('과매수' if k > 80 else '중립')
        if k > d and k < 50:
            pts += 2
            note += ' + %K 상향 돌파'
        items.append(('스토캐스틱 %K', f'{k:.1f}', min(pts, 10), 10, note))
    else:
        items.append(('스토캐스틱 %K', '-', 5, 10, '데이터 부족 (중립 처리)'))

    total = sum(i[2] for i in items)
    return round(total, 1), items


# ---------------------------------------------------------------------------
# 3. 펀더멘털/실적/전망 점수 (100점 만점)
# ---------------------------------------------------------------------------
def fundamental_score(info, current_price, eps_growth_next_year=None):
    """yfinance info dict 기반 점수. 데이터가 없으면 None 반환(ETF, 코인 등)."""
    info = info or {}
    items = []

    def get(key):
        v = info.get(key)
        return v if isinstance(v, (int, float)) and not np.isnan(v) else None

    # --- 밸류에이션 (30점) ---
    fpe, tpe, peg = get('forwardPE'), get('trailingPE'), get('trailingPegRatio') or get('pegRatio')
    if fpe is not None and fpe > 0:
        pts = _interp(fpe, [8, 15, 25, 40, 60], [15, 12, 8, 3, 0])
        note = '저평가' if fpe < 15 else ('적정' if fpe < 25 else '고평가 부담')
        if tpe and tpe > fpe:
            note += ' / 이익 증가 예상(선행PER < 현재PER)'
        items.append(('선행 PER', f'{fpe:.1f}', pts, 15, note))
    elif tpe is not None and tpe > 0:
        pts = _interp(tpe, [8, 15, 25, 40, 60], [15, 12, 8, 3, 0])
        items.append(('PER', f'{tpe:.1f}', pts, 15, '선행 PER 없음 – 현재 PER로 평가'))
    else:
        items.append(('PER', '-', None, 15, '데이터 없음/적자'))

    if peg is not None and peg > 0:
        pts = _interp(peg, [0.5, 1, 2, 3], [15, 12, 6, 0])
        note = '성장 대비 저평가' if peg < 1 else ('적정' if peg < 2 else '성장 대비 고평가')
        items.append(('PEG', f'{peg:.2f}', pts, 15, note))
    else:
        pbr = get('priceToBook')
        if pbr is not None and pbr > 0:
            pts = _interp(pbr, [0.5, 1, 2, 4, 8], [15, 12, 8, 3, 0])
            items.append(('PBR', f'{pbr:.2f}', pts, 15, 'PEG 없음 – PBR로 평가'))
        else:
            items.append(('PEG/PBR', '-', None, 15, '데이터 없음'))

    # --- 실적 성장성 (25점) ---
    for key, label, max_pts in (('revenueGrowth', '매출 성장률(YoY)', 12.5),
                                ('earningsGrowth', '이익 성장률(YoY)', 12.5)):
        g = get(key)
        if g is not None:
            pts = _interp(g * 100, [-20, 0, 10, 25], [0, max_pts * 0.35, max_pts * 0.75, max_pts])
            note = '고성장' if g > 0.2 else ('성장' if g > 0 else '역성장')
            items.append((label, f'{g * 100:+.1f}%', pts, max_pts, note))
        else:
            items.append((label, '-', None, max_pts, '데이터 없음'))

    # --- 수익성/재무건전성 (20점) ---
    roe = get('returnOnEquity')
    if roe is not None:
        pts = _interp(roe * 100, [0, 8, 15, 25], [0, 5, 8, 10])
        items.append(('ROE', f'{roe * 100:.1f}%', pts, 10,
                      '우수' if roe > 0.15 else ('보통' if roe > 0.08 else '저조')))
    else:
        items.append(('ROE', '-', None, 10, '데이터 없음'))

    de = get('debtToEquity')
    if de is not None:
        pts = _interp(de, [30, 100, 200], [5, 3, 0])
        items.append(('부채비율(D/E)', f'{de:.0f}%', pts, 5,
                      '안정' if de < 100 else '부채 부담'))
    else:
        items.append(('부채비율(D/E)', '-', None, 5, '데이터 없음'))

    margin = get('profitMargins')
    if margin is not None:
        pts = _interp(margin * 100, [0, 5, 15, 25], [0, 2, 4, 5])
        items.append(('순이익률', f'{margin * 100:.1f}%', pts, 5,
                      '고마진' if margin > 0.15 else ('보통' if margin > 0.05 else '저마진')))
    else:
        items.append(('순이익률', '-', None, 5, '데이터 없음'))

    # --- 애널리스트 전망/향후 예상치 (25점) ---
    target = get('targetMeanPrice')
    if target and current_price:
        upside = (target / current_price - 1) * 100
        pts = _interp(upside, [-10, 0, 10, 20, 35], [0, 2, 6, 9, 12])
        n = info.get('numberOfAnalystOpinions')
        note = f'평균 목표가 {target:,.2f}' + (f' (애널리스트 {n}명)' if n else '')
        items.append(('목표주가 상승여력', f'{upside:+.1f}%', pts, 12, note))
    else:
        items.append(('목표주가 상승여력', '-', None, 12, '데이터 없음'))

    rec = get('recommendationMean')
    if rec is not None:
        pts = _interp(rec, [1.5, 2.0, 2.5, 3.0, 3.5], [8, 7, 5, 2, 0])
        key = info.get('recommendationKey', '')
        items.append(('투자의견(1=강력매수~5=매도)', f'{rec:.2f}', pts, 8, key or '-'))
    else:
        items.append(('투자의견', '-', None, 8, '데이터 없음'))

    if eps_growth_next_year is not None and not np.isnan(eps_growth_next_year):
        g = eps_growth_next_year * 100
        pts = _interp(g, [-10, 0, 10, 20], [0, 1.5, 3.5, 5])
        items.append(('내년 EPS 성장 예상치', f'{g:+.1f}%', pts, 5, '컨센서스 기준'))
    else:
        items.append(('내년 EPS 성장 예상치', '-', None, 5, '데이터 없음'))

    available = [i for i in items if i[2] is not None]
    if len(available) < 3:
        return None, items  # 펀더멘털 평가 불가 (ETF, 코인, 원자재 등)

    # 데이터가 없는 항목은 제외하고 나머지 배점 기준으로 100점 환산
    got = sum(i[2] for i in available)
    possible = sum(i[3] for i in available)
    return round(got / possible * 100, 1), items


def get_eps_growth_next_year(stock_obj):
    """yfinance earnings_estimate에서 내년(+1y) EPS 성장 예상치를 추출."""
    try:
        est = stock_obj.earnings_estimate
        if est is not None and not est.empty and '+1y' in est.index and 'growth' in est.columns:
            v = est.loc['+1y', 'growth']
            return float(v) if v is not None else None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 4. 뉴스 심리 점수 (AI 감성 분석)
# ---------------------------------------------------------------------------
def sentiment_prompt(name, headlines):
    joined = '\n'.join(f'- {h}' for h in headlines)
    return f"""당신은 주식 뉴스 감성 분석가입니다.
아래는 '{name}' 관련 최신 뉴스 헤드라인입니다.

{joined}

주가에 미칠 영향을 기준으로 매수 관점의 뉴스 심리 점수를 0~100 사이 정수로 매기세요.
(0=매우 부정, 50=중립, 100=매우 긍정). 실적 발표, 가이던스, 수주, 규제, 소송 등을 중점 고려하세요.
반드시 아래 JSON 형식만 출력하세요:
{{"score": 정수, "positive": ["긍정 요인"], "negative": ["부정 요인"], "summary": "한 줄 요약"}}"""


def parse_sentiment(text):
    """AI 응답에서 JSON을 추출. 실패 시 None."""
    if not text:
        return None
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        data['score'] = max(0, min(100, int(data.get('score', 50))))
        data.setdefault('positive', [])
        data.setdefault('negative', [])
        data.setdefault('summary', '')
        return data
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 5. 종합 점수
# ---------------------------------------------------------------------------
def combine_scores(tech, fund, senti, weights):
    """가중 평균. 값이 None인 영역은 제외하고 나머지 가중치로 재분배."""
    parts = {'기술적 분석': (tech, weights['tech']),
             '펀더멘털/전망': (fund, weights['fund']),
             '뉴스 심리': (senti, weights['senti'])}
    used = {k: (s, w) for k, (s, w) in parts.items() if s is not None and w > 0}
    total_w = sum(w for _, w in used.values())
    if total_w == 0:
        return None, {}
    score = sum(s * w for s, w in used.values()) / total_w
    eff = {k: w / total_w for k, (_, w) in used.items()}
    return round(score, 1), eff


def verdict(score):
    """(등급, 설명, 색상)"""
    if score >= 75:
        return '강력 매수 타이밍', '지표·실적·심리가 모두 우호적입니다. 분할 매수 진입을 적극 고려할 만합니다.', '#16A34A'
    if score >= 60:
        return '분할 매수 고려', '전반적으로 긍정적입니다. 일부 비중으로 나눠서 진입하는 전략이 유효합니다.', '#65A30D'
    if score >= 45:
        return '관망', '뚜렷한 매수 신호가 없습니다. 지지선 확인이나 추가 조정을 기다리세요.', '#CA8A04'
    if score >= 30:
        return '매수 보류', '부정적 신호가 우세합니다. 신규 진입은 보류하는 것이 좋습니다.', '#EA580C'
    return '매수 회피', '기술적·펀더멘털 모두 약세입니다. 리스크 관리가 우선입니다.', '#DC2626'
