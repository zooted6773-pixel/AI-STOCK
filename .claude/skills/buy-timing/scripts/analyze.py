"""매수 타이밍 평가표 계산기 (스킬용 CLI)

사용법
  1) 시세 자동 조회 (yfinance 접속 가능할 때)
       python analyze.py NVDA [--sentiment 65]
  2) 웹에서 직접 찾은 값으로 채점
       python analyze.py --values values.json      (또는 --values - 로 표준입력)

values.json 형식 (모르는 값은 빼면 중립/제외 처리)
{
  "name": "삼성전자", "ticker": "005930.KS",
  "technical": {"close": 61000, "rsi": 38.2, "bb_pctb": 0.15, "macd_hist": -120, "macd_hist_prev": -180,
                "macd_recent_cross": false, "ma20": 62500, "ma60": 64000, "ma120": 60000,
                "stoch_k": 22, "stoch_d": 18},
  "fundamental": {"forwardPE": 11.2, "trailingPE": 14.5, "pegRatio": 0.8, "priceToBook": 1.1,
                  "revenueGrowth": 0.12, "earningsGrowth": 0.45, "returnOnEquity": 0.09,
                  "debtToEquity": 30, "profitMargins": 0.11, "targetMeanPrice": 80000,
                  "recommendationMean": 1.6, "numberOfAnalystOpinions": 25},
  "eps_growth_next_year": 0.25,
  "sentiment": 62,
  "weights": {"tech": 40, "fund": 40, "senti": 20}
}
성장률·ROE·이익률은 소수(12% → 0.12), 부채비율(D/E)은 % 숫자(30% → 30)로 넣는다.
결과는 JSON으로 출력된다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scorecard as sc  # noqa: E402

DEFAULT_WEIGHTS = {'tech': 40, 'fund': 40, 'senti': 20}


def fetch_values(ticker):
    import yfinance as yf
    t = yf.Ticker(ticker)
    hist = t.history(period='1y')
    if hist.empty:
        raise RuntimeError(f'{ticker} 시세 데이터 없음')
    tech = sc.latest_values(sc.add_indicators(hist))
    try:
        info = t.info or {}
    except Exception:
        info = {}
    return {'name': info.get('shortName', ticker), 'ticker': ticker, 'technical': tech,
            'fundamental': info, 'eps_growth_next_year': sc.get_eps_growth_next_year(t)}


def build_report(v, sentiment=None):
    tech_vals = v.get('technical') or {}
    tech_score, tech_items = sc.technical_score_from_values(tech_vals)
    fund_score, fund_items = sc.fundamental_score(v.get('fundamental') or {}, tech_vals.get('close'),
                                                  v.get('eps_growth_next_year'))
    senti = sentiment if sentiment is not None else v.get('sentiment')
    total, eff = sc.combine_scores(tech_score, fund_score, senti, v.get('weights') or DEFAULT_WEIGHTS)
    grade, desc, _ = sc.verdict(total) if total is not None else ('-', '-', None)

    def rows(items):
        return [{'항목': n, '현재값': val, '점수': None if p is None else round(p, 1), '배점': m, '해석': note}
                for n, val, p, m, note in items]

    t = tech_vals
    levels = {k: t.get(k) for k in ('close', 'ma20', 'ma60', 'ma120') if t.get(k) is not None}
    return {
        'name': v.get('name'), 'ticker': v.get('ticker'),
        '종합점수': total, '등급': grade, '설명': desc,
        '적용가중치': {k: round(w * 100) for k, w in eff.items()},
        '기술적분석': {'점수': tech_score, '항목': rows(tech_items)},
        '펀더멘털': {'점수': fund_score, '항목': rows(fund_items)},
        '뉴스심리': {'점수': senti},
        '참고가격': levels,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('ticker', nargs='?')
    p.add_argument('--values')
    p.add_argument('--sentiment', type=int)
    a = p.parse_args()
    if a.values:
        f = sys.stdin if a.values == '-' else open(a.values, encoding='utf-8')
        values = json.load(f)
    elif a.ticker:
        try:
            values = fetch_values(a.ticker)
        except Exception as e:
            print(json.dumps({'error': f'자동 조회 실패: {type(e).__name__}: {e}',
                              'hint': '웹 검색으로 값을 모아 --values 모드로 실행하세요.'}, ensure_ascii=False))
            sys.exit(2)
    else:
        p.error('티커 또는 --values 가 필요합니다')
    print(json.dumps(build_report(values, a.sentiment), ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
