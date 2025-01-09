import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import ssl

# SSL 인증서 검증을 비활성화
ssl._create_default_https_context = ssl._create_unverified_context

# 데이터 다운로드
vix = yf.download('^VIX', start='2010-01-01', end='2025-01-01')
qqq = yf.download('QQQ', start='2010-01-01', end='2025-01-01')

# 데이터 정리
vix['Daily Return'] = vix['Adj Close'].pct_change()
qqq['Daily Return'] = qqq['Adj Close'].pct_change()


# VIX 상향 돌파 및 하향 돌파 감지
def vix_cross_strategy(vix_data, qqq_data, threshold=40, hold_period=252):
    signals = pd.Series(index=vix_data.index, dtype=int)
    positions = pd.Series(index=qqq_data.index, dtype=int)

    for i in range(1, len(vix_data)):
        if vix_data['Adj Close'].iloc[i - 1] < threshold and vix_data['Adj Close'].iloc[i] > threshold:  # 상향 돌파
            signals.iloc[i] = 1  # 매수 신호
        elif vix_data['Adj Close'].iloc[i - 1] > threshold and vix_data['Adj Close'].iloc[i] < threshold:  # 하향 돌파
            signals.iloc[i] = -1  # 매도 신호

    # 매수 시점에서 1년 후 매도
    for i in range(len(signals)):
        if signals.iloc[i] == 1:  # 매수 신호가 발생한 지점
            buy_date = signals.index[i]
            sell_date = buy_date + pd.Timedelta(days=hold_period)  # 1년 뒤
            if sell_date in qqq_data.index:
                positions.loc[buy_date:sell_date] = 1  # 매수한 날짜부터 1년 동안 보유

    return positions


# VIX 상향돌파 및 하향돌파 전략 적용
positions = vix_cross_strategy(vix, qqq)

# 포트폴리오 수익률 계산
portfolio_returns = positions.shift(1) * qqq['Daily Return']  # 1일 지연된 매매
portfolio_value = (1 + portfolio_returns).cumprod()  # 누적 수익률

# MDD (최대 낙폭) 계산
rolling_max = portfolio_value.cummax()
drawdowns = (portfolio_value - rolling_max) / rolling_max
max_drawdown = drawdowns.min()

# CAGR (연평균 성장률) 계산
years = (portfolio_value.index[-1] - portfolio_value.index[0]).days / 365.25
cagr = (portfolio_value.iloc[-1] / portfolio_value.iloc[0]) ** (1 / years) - 1

# 결과 출력
print(f'Max Drawdown: {max_drawdown * 100:.2f}%')
print(f'CAGR: {cagr * 100:.2f}%')

# 포트폴리오 수익률 시각화
plt.figure(figsize=(10, 6))
plt.plot(portfolio_value, label='Portfolio Value')
plt.title('Portfolio Performance')
plt.xlabel('Date')
plt.ylabel('Portfolio Value')
plt.legend()
plt.show()
