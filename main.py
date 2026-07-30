import calendar
from datetime import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from zoneinfo import ZoneInfo

st.set_page_config(page_title="박스오피스 대시보드", layout="wide")
st.title("🎬 월간 박스오피스 TOP5 변화")

# 비밀 금고에서 인증키 꺼내기 (코드에는 키를 적지 않는다)
KOBIS_KEY = st.secrets["KOBIS_KEY"]
URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# ---------------------------------------------------------------
# 1) 월 선택 드롭박스 (2020년 1월 ~ 2026년 7월)
# ---------------------------------------------------------------
def build_month_list(start=(2020, 1), end=(2026, 7)):
    months = []
    y, m = start
    while (y, m) <= end:
        months.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def label(ym: str) -> str:
    return f"{ym[:4]}년 {int(ym[4:]):02d}월"


month_options = build_month_list()
month_options.reverse()  # 최신 월이 목록 위쪽에 오도록

selected = st.selectbox(
    "조회할 월을 선택하세요",
    month_options,
    format_func=label,
    index=0,
)

year, month = int(selected[:4]), int(selected[4:6])
days_in_month = calendar.monthrange(year, month)[1]
today = datetime.now(ZoneInfo("Asia/Seoul")).date()


# ---------------------------------------------------------------
# 2) 하루치 박스오피스 자료 요청 (자료는 하루 단위로만 제공되므로
#    선택한 달의 날짜 수만큼 반복 호출한다. 같은 날짜는 캐시로 재사용)
# ---------------------------------------------------------------
@st.cache_data(show_spinner=False)
def fetch_day(target_dt: str):
    try:
        res = requests.get(URL, params={"key": KOBIS_KEY, "targetDt": target_dt}, timeout=10)
    except requests.exceptions.RequestException:
        return None
    if res.status_code != 200:
        return None
    data = res.json()
    # KOBIS는 키가 틀려도 상태코드 200을 준다. 대신 faultInfo 상자가 온다.
    if "faultInfo" in data:
        return "AUTH_ERROR"
    return data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])


records = []
auth_error = False
progress = st.progress(0, text="일별 자료를 불러오는 중...")

for day in range(1, days_in_month + 1):
    day_date = datetime(year, month, day).date()
    if day_date > today:
        break  # 미래 날짜는 자료가 없으므로 건너뛴다

    box_list = fetch_day(day_date.strftime("%Y%m%d"))
    if box_list == "AUTH_ERROR":
        auth_error = True
        break
    if box_list:
        for row in box_list:
            if int(row["rank"]) <= 5:
                records.append(
                    {
                        "date": day_date,
                        "rank": int(row["rank"]),
                        "movieNm": row["movieNm"],
                        "audiCnt": int(row["audiCnt"]),
                    }
                )
    progress.progress(day / days_in_month, text=f"{day_date} 자료 불러오는 중...")

progress.empty()

if auth_error:
    st.error("인증키가 올바르지 않습니다. 금고(Secrets)의 KOBIS_KEY를 확인해 주세요.")
    st.stop()

if not records:
    st.warning("선택한 월에는 조회 가능한 자료가 없습니다. 다른 달을 선택해 보세요.")
    st.stop()

df = pd.DataFrame(records)
df["date_str"] = df["date"].astype(str)

# ---------------------------------------------------------------
# 3) 일별 TOP5 변화 그래프 (바 차트 레이스)
# ---------------------------------------------------------------
st.subheader(f"📊 {label(selected)} 일별 박스오피스 TOP5 변화")

fig = px.bar(
    df.sort_values(["date", "rank"]),
    x="audiCnt",
    y="movieNm",
    color="movieNm",
    orientation="h",
    animation_frame="date_str",
    range_x=[0, df["audiCnt"].max() * 1.1],
    labels={"audiCnt": "관객수", "movieNm": "영화명", "date_str": "날짜"},
    text="audiCnt",
)
fig.update_traces(texttemplate="%{text:,}", textposition="outside")
fig.update_layout(
    yaxis={"categoryorder": "total ascending"},
    showlegend=False,
    height=550,
    xaxis_title="관객수(명)",
    yaxis_title="",
)
# 재생 속도를 조금 늦춰서 변화를 눈으로 따라가기 쉽게 한다
if fig.layout.updatemenus:
    fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 600

st.plotly_chart(fig, use_container_width=True)
st.caption("▶ 버튼을 누르면 하루씩 순위가 바뀌는 과정을 애니메이션으로 볼 수 있습니다.")

# ---------------------------------------------------------------
# 4) 참고용 보조 그래프 · 표
# ---------------------------------------------------------------
st.subheader("📈 일별 1위 영화 관객수 추이")
top1_daily = df[df["rank"] == 1][["date", "movieNm", "audiCnt"]].sort_values("date")
st.line_chart(top1_daily.set_index("date")["audiCnt"])

st.subheader("📋 일별 TOP5 원본 표")
table = df.sort_values(["date", "rank"])[["date", "rank", "movieNm", "audiCnt"]].copy()
table.columns = ["날짜", "순위", "영화명", "관객수"]
st.dataframe(table, use_container_width=True)
