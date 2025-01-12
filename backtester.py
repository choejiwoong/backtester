import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import ssl

# SSL 인증서 검증 비활성화
ssl._create_default_https_context = ssl._create_unverified_context

# 데이터 다운로드
vix = yf.download('^VIX', start='2007-01-01', end='2025-01-01')
qqq = yf.download('QLD', start='2007-01-01', end='2025-01-01')
# ^KS11: 코스피

# 데이터 정리
vix['Daily Return'] = vix['Close'].pct_change()
qqq['Daily Return'] = qqq['Close'].pct_change()

# VIX 하향 돌파 후 1개월 뒤 매수 전략
def vix_cross_strategy(vix_data, qqq_data, threshold=40, hold_period=252):
    # 매수/매도 신호 초기화
    signals = pd.Series(0, index=vix_data.index, dtype=int)
    positions = pd.Series(0, index=qqq_data.index, dtype=int)
    in_position = False  # 매수 후 포지션을 보유 중인지 여부를 추적
    last_buy_date = None  # 마지막 매수 날짜 초기화
    buy_date = None  # 매수 날짜 초기화
    cross_dates = []  # VIX 40 하향 돌파 날짜 기록

    for i in range(1, len(vix_data)):
        # VIX가 40을 하향 돌파하면 한 달 후 매수
        if not in_position and (vix_data['Close'].iloc[i - 1] > threshold).any() and (vix_data['Close'].iloc[i] < threshold).any():
            # VIX 40 하향 돌파 시점을 기록
            cross_dates.append(vix_data.index[i])

            # 매수 후 1년 이내에는 추가 매수하지 않도록 방지
            if last_buy_date is None or (vix_data.index[i] - last_buy_date).days > hold_period:
                # VIX 40 하향 돌파 후 한 달 뒤 매수
                buy_date = vix_data.index[i] + pd.Timedelta(days=30)  # 하향 돌파 후 한 달 뒤
                if buy_date < vix_data.index[-1]:  # 마지막 데이터보다 이후일 경우에만 매수 가능
                    signals.loc[buy_date] = 1  # 매수 신호
                    in_position = True
                    sell_date = buy_date + pd.Timedelta(days=hold_period)  # 1년 뒤

                    # sell_date를 포함하여 valid_dates를 설정
                    valid_dates = pd.date_range(start=buy_date, end=sell_date, freq='B')  # 'B'는 영업일 기준
                    valid_dates = valid_dates.intersection(positions.index)  # positions의 인덱스와 일치하는 날짜만 선택
                    positions.loc[valid_dates] = 1
                    last_buy_date = buy_date  # 마지막 매수 날짜 업데이트

        # 1년 후 매도
        if in_position and (vix_data.index[i] - buy_date).days >= hold_period:
            sell_date = buy_date + pd.Timedelta(days=hold_period)
            if sell_date in positions.index:  # sell_date가 유효한지 확인
                positions.loc[sell_date] = 0  # 포지션 종료
                in_position = False  # 포지션 종료
                last_buy_date = None  # 매수 날짜 초기화

    return signals, positions, cross_dates


# VIX 하향 돌파 전략 적용
signals, positions, cross_dates = vix_cross_strategy(vix, qqq)

# 포트폴리오 수익률 계산
portfolio_returns = positions.shift(1) * qqq['Daily Return']  # 1일 지연된 매매
portfolio_value = (1 + portfolio_returns).cumprod()  # 누적 수익률

# NaN 값 처리: NaN을 0으로 대체
portfolio_value = portfolio_value.fillna(1)

# MDD (최대 낙폭) 계산
max_mdd = 0  # 최대 MDD 저장

# 매수/매도 시점마다 MDD 계산
for i in range(1, len(signals)):
    if signals.iloc[i] == 1:  # 매수 신호 발생
        buy_date = signals.index[i]
        sell_date = buy_date + pd.Timedelta(days=252)  # 1년 뒤
        if sell_date in portfolio_value.index:
            # 매매 구간 MDD 계산
            trade_rolling_max = portfolio_value.loc[buy_date:sell_date].cummax()
            trade_drawdowns = (portfolio_value.loc[buy_date:sell_date] - trade_rolling_max) / trade_rolling_max
            trade_max_drawdown = trade_drawdowns.min()

            # 최대 MDD 갱신
            if trade_max_drawdown < max_mdd:
                max_mdd = trade_max_drawdown

# 누적 수익률 계산
cumulative_return = portfolio_value.iloc[-1] / portfolio_value.iloc[0] - 1

# 매수/매도 시점마다 수익률과 MDD 출력
for i in range(1, len(signals)):
    if signals.iloc[i] == 1:  # 매수 신호 발생
        buy_date = signals.index[i]
        sell_date = buy_date + pd.Timedelta(days=252)  # 1년 뒤
        if sell_date in portfolio_value.index:
            sell_value = portfolio_value[sell_date]
            buy_value = portfolio_value[buy_date]
            trade_return = (sell_value - buy_value) / buy_value * 100  # 수익률

            # 매매 구간 MDD 계산
            trade_rolling_max = portfolio_value.loc[buy_date:sell_date].cummax()
            trade_drawdowns = (portfolio_value.loc[buy_date:sell_date] - trade_rolling_max) / trade_rolling_max
            trade_max_drawdown = trade_drawdowns.min()

            print(f"Trade from {buy_date.date()} to {sell_date.date()}:")
            print(f"  - Return: {trade_return:.2f}%")
            print(f"  - Max Drawdown: {trade_max_drawdown * 100:.2f}%")
            print("-" * 50)

# 결과를 맨 마지막에 출력
print(f'Cumulative Return: {cumulative_return * 100:.2f}%')
print(f'\nMaximum MDD: {max_mdd * 100:.2f}%')

# 포트폴리오 수익률 시각화
plt.figure(figsize=(10, 6))
plt.plot(portfolio_value, label='Portfolio Value', color='blue')
plt.title('Portfolio Performance')
plt.xlabel('Date')
plt.ylabel('Portfolio Value')
plt.legend()
plt.grid(True)
plt.show()

