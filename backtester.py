import yfinance as yf
import pandas as pd
import ssl
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time  # for simulating delay

# SSL 인증서 검증 비활성화
ssl._create_default_https_context = ssl._create_unverified_context

# Streamlit UI 설정
st.title('VIX 전략 백테스트')
st.sidebar.header('파라미터')

# 전략 설명 페이지
st.markdown("""
## 전략 설명

이 전략은 **VIX 40 하향 돌파 후 30일 뒤 매수하고 1년 동안 보유**하는 전략입니다.

### 전략 흐름:
1. **VIX 하향 돌파**: VIX가 40을 하향 돌파하면 매수 신호가 발생합니다.
2. **30일 뒤 매수**: VIX가 하향 돌파한 지 30일 뒤 해당 ETF를 매수합니다.
3. **1년 보유**: 매수 후 1년 동안 해당 ETF를 보유합니다.
4. **손절**: 만약 매수 후 주가가 25% 이상 하락하면 손절합니다.

### 전략의 목적:
- VIX 지수가 높은 시점에서 투자하는 대신, VIX가 하락하기 시작한 후 상승할 때를 포착하려는 전략입니다.
- ETF 티커는 QQQ, QLD, TQQQ 중 하나를 선택할 수 있습니다.

### 지금까지 최고 전략:
- QLD 매수, 20% 손절
""")

# 사용자 입력 받기
ticker = st.sidebar.selectbox('ETF 티커 선택', ['QQQ', 'QLD', 'TQQQ'], index=1)
start_date = st.sidebar.date_input('시작일', pd.to_datetime('2000-01-01'))
end_date = pd.to_datetime('today')  # 종료일을 오늘 날짜로 설정

# 손절 비율을 사용자로부터 입력 받기 (0.05 단위)
stop_loss = st.sidebar.number_input('손절 비율 (0과 1 사이, 예: 0.20)', min_value=0.0, max_value=1.0, value=0.20, step=0.05)

# 버튼 클릭 시 백테스트 실행
if st.sidebar.button('백테스트 하기'):
    with st.spinner('백테스트 중입니다... 다소 시간이 걸릴 수 있습니다.'):

        # 데이터 다운로드
        vix = yf.download('^VIX', start=start_date, end=end_date)
        qqq = yf.download(ticker, start=start_date, end=end_date)

        # 데이터 정리
        vix['Daily Return'] = vix['Close'].pct_change()
        qqq['Daily Return'] = qqq['Close'].pct_change()

        # VIX 하향 돌파 후 1개월 뒤 매수 전략
        def vix_cross_strategy(vix_data, qqq_data, threshold=40, hold_period=252, stop_loss=0.25):
            # 매수/매도 신호 초기화
            signals = pd.Series(0, index=vix_data.index, dtype=int)
            positions = pd.Series(0, index=qqq_data.index, dtype=int)
            cross_dates = []  # VIX 40 하향 돌파 날짜 기록

            in_position = False  # 포지션 보유 여부
            last_buy_date = None  # 마지막 매수 날짜
            last_buy_price = None  # 매수 당시 가격

            for i in range(1, len(vix_data)):
                # VIX가 40을 하향 돌파한 경우
                prev_close = vix_data['Close'].iloc[i - 1].item()
                current_close = vix_data['Close'].iloc[i].item()
                if not in_position and prev_close > threshold and current_close < threshold:
                    cross_dates.append(vix_data.index[i])  # VIX 40 하향 돌파 날짜 기록

                    # 매수 가능 조건 확인
                    if last_buy_date is None or (vix_data.index[i] - last_buy_date).days > hold_period:
                        buy_date = vix_data.index[i] + pd.Timedelta(days=30)  # VIX 40 하향 돌파 후 30일 후 매수
                        if buy_date in qqq_data.index:  # 매수 가능한 날짜 확인
                            signals.loc[buy_date] = 1
                            last_buy_price = qqq_data.loc[buy_date, 'Close'].item()
                            in_position = True
                            sell_date = buy_date + pd.Timedelta(days=hold_period)  # 기본 보유 기간

                            # 손절 조건 확인
                            for date in pd.date_range(start=buy_date, end=sell_date, freq='B'):
                                if date in qqq_data.index:
                                    current_price = qqq_data.loc[date, 'Close'].item()
                                    # 손절 조건 충족 시 매도
                                    if current_price < last_buy_price * (1 - stop_loss):
                                        sell_date = date
                                        break

                            # 매수-매도 기간 동안 포지션 보유
                            valid_dates = pd.date_range(start=buy_date, end=sell_date, freq='B')
                            valid_dates = valid_dates.intersection(positions.index)
                            positions.loc[valid_dates] = 1
                            last_buy_date = buy_date
                            in_position = False  # 포지션 종료

            return signals, positions, cross_dates


        # VIX 하향 돌파 전략 적용
        signals, positions, cross_dates = vix_cross_strategy(vix, qqq, stop_loss=stop_loss)

        # 포트폴리오 수익률 계산
        portfolio_returns = positions.shift(1) * qqq['Daily Return']  # 1일 지연된 매매
        portfolio_value = (1 + portfolio_returns).cumprod()  # 누적 수익률을 복리로 계산
        portfolio_value = portfolio_value.fillna(1)  # NaN 값 처리

        # 누적 수익률 계산
        cumulative_return = portfolio_value.iloc[-1] / portfolio_value.iloc[0] - 1  # 100% 기준으로 계산

        # 기대수익률 계산
        average_daily_return = portfolio_returns.mean()  # 일일 평균 수익률
        expected_annual_return = average_daily_return * 252  # 연간 기대 수익률 (252 거래일 기준)

        # 백테스트 결과 표
        trade_results = []
        # 가장 낮은 Drawdown과 관련 정보 초기화
        lowest_trade_drawdown = 0
        lowest_drawdown_buy_date = None
        lowest_drawdown_sell_date = None

        for i in range(1, len(signals)):
            if signals.iloc[i] == 1:  # 매수 신호
                buy_date = signals.index[i]
                sell_date = buy_date + pd.Timedelta(days=252)  # 기본 보유 기간
                if sell_date in portfolio_value.index:
                    sell_value = portfolio_value[sell_date]
                    buy_value = portfolio_value[buy_date]
                    trade_return = (sell_value - buy_value) / buy_value * 100  # 수익률

                    # 해당 기간 MDD 계산
                    trade_rolling_max = portfolio_value.loc[buy_date:sell_date].cummax()
                    trade_drawdowns = (portfolio_value.loc[buy_date:sell_date] - trade_rolling_max) / trade_rolling_max
                    trade_max_drawdown = trade_drawdowns.min()

                    # 가장 낮은 Drawdown 업데이트
                    if trade_max_drawdown < lowest_trade_drawdown:
                        lowest_trade_drawdown = trade_max_drawdown
                        lowest_drawdown_buy_date = buy_date
                        lowest_drawdown_sell_date = sell_date

                    # 결과 추가: 매수일, 매도일, 수익률, MDD
                    trade_results.append({
                        "매수일": buy_date.date(),
                        "매도일": sell_date.date(),
                        "수익률 (%)": trade_return,  # float 값으로 저장
                        "MDD (%)": trade_max_drawdown * 100  # MDD도 float로 저장
                    })

        # 최종 결과 표
        trade_df = pd.DataFrame(trade_results)

        # 수익률 컬럼을 float으로 변환
        trade_df['수익률 (%)'] = trade_df['수익률 (%)'].astype(float)
        trade_df['MDD (%)'] = trade_df['MDD (%)'].astype(float)

        # 수익률과 MDD 컬럼을 0.00 형식으로 표시
        trade_df['수익률 (%)'] = trade_df['수익률 (%)'].map(lambda x: f"{x:0.2f}")
        trade_df['MDD (%)'] = trade_df['MDD (%)'].map(lambda x: f"{x:0.2f}")

        # index를 1부터 시작하도록 설정
        trade_df.index = range(1, len(trade_df) + 1)

        # 수익률과 MDD 컬럼에 색상 적용
        def colorize(val, mdd_val):
            try:
                val = float(val) / 100  # 문자열을 숫자로 변환 시도
            except ValueError:
                return ''  # 값이 숫자가 아니면 기본값 반환

            # MDD의 절댓값에 따라 빨간색 강도 조정
            mdd_intensity = min(abs(mdd_val) // 5, 51)  # MDD가 클수록 빨간색을 더 진하게 만들기

            # 5% 단위로 색상 강도 계산
            if val >= 0:  # 양수 수익률에 대해서
                # 색상 강도 계산 (5% 단위로 변화)
                intensity_level = min(int(val // 0.05), 51)  # 5% 단위로 강도를 나누고 최대 51까지 제한

                # 기본 색상 #345342에서 진해지는 방식으로 계산
                r = 52 - intensity_level * 5  # R 값을 진하게 만들기
                g = 83 - intensity_level * 5  # G 값을 진하게 만들기
                b = 66 - intensity_level * 5  # B 값을 진하게 만들기

                color = f'rgb({r}, {g}, {b})'  # 색상 값 설정
                # text_color = 'white'  # 양수 수익률일 때 텍스트 색상은 흰색
            else:  # 음수 수익률에 대해서
                # 5% 단위로 음수 수익률에 대해서 색상 강도 계산
                intensity_level = min(int(abs(val) // 0.05), 51)  # 음수 수익률의 경우도 5% 단위로 강도 설정

                # 빨간색 #DB4455(219, 68, 85)을 기준으로 진해지는 방식
                r = 219 - intensity_level * 10 # R 값을 진하게 만들기
                g = 68 - intensity_level * 10  # G 값을 진하게 만들기
                b = 85 - intensity_level * 10  # B 값을 진하게 만들기

                color = f'rgb({r}, {g}, {b})'  # 빨간색 강도 증가

                # text_color = 'black'  # 음수 수익률일 때 텍스트 색상은 검은색

            return f'background-color: {color}; color: white'  # 배경색과 텍스트 색상 설정

        # 스타일 적용
        def style_func(val, mdd_val):
            return colorize(val, mdd_val)

        # 가장 낮은 MDD와 그에 대응하는 MDD 날짜
        lowest_mdd_date = lowest_drawdown_buy_date if lowest_drawdown_buy_date else pd.NaT

        # 최종 결과 테이블에 스타일 적용
        trade_df_styled = trade_df.style.applymap(lambda val: style_func(val, lowest_trade_drawdown), subset=["수익률 (%)", "MDD (%)"])

        # 스타일이 적용된 테이블 출력
        st.subheader('백테스트 결과')
        st.write(f"누적 수익률: {cumulative_return * 100:0.2f}%")
        st.write(f"최대 MDD: {lowest_trade_drawdown * 100:0.2f}%")
        st.write(f"기대 수익률: {expected_annual_return * 100:0.2f}%")
        # 최대 MDD 발생 날짜를 YYYY-MM-DD 형식으로 변환
        if pd.isna(lowest_mdd_date):
            formatted_date = "N/A"  # NaT인 경우 'N/A'로 표시
        else:
            formatted_date = lowest_mdd_date.strftime('%Y-%m-%d')
        # Streamlit에 출력
        st.write(f"최대 MDD 발생 날짜: {formatted_date}")
        st.write(trade_df_styled)

        # 그래프 그리기
        fig = make_subplots(rows=1, cols=1)

        # portfolio_value를 누적 수익률로 사용
        fig.add_trace(go.Scatter(x=portfolio_value.index, y=portfolio_value.values, mode='lines', name="순자산"))

        fig.update_layout(
            title='VIX 전략 백테스트',
            xaxis_title='날짜',
            yaxis_title='누적 수익률',
            template="plotly_dark"
        )

        # 그래프 출력
        st.plotly_chart(fig)