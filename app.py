import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from supabase import create_client, Client
import time
import io

# 1. 고도화된 물리 시뮬레이션 모듈의 함수를 가져옵니다.
from simulation_engine import run_wildfire_simulation

# Supabase 접속 설정
SUPABASE_URL = "https://gyvvqjngobgddlihmtlz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5dnZxam5nb2JnZGRsaWhtdGx6Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDMwODQ3MiwiZXhwIjoyMDk1ODg0NDcyfQ.EhuItbhoF_oO4c0vWSXtDCF4P2x4iN4t64I0DU9fPHk"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

st.set_page_config(page_title="원주 산불 방재 시뮬레이터", layout="wide")
st.title("🌲 원주 용수골 임도 기반 산불 확산 물리 시뮬레이터 (v2.0)")

# [CSS 고도화] 레이아웃 붕괴 방지 유지
st.markdown(
    """
    <style>
    .block-container {
        max-width: 1200px !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        margin: 0 auto !important;
    }
    .stImage img {
        width: 800px !important;
        height: auto !important; 
        object-fit: contain !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 2. Supabase DB에서 데이터 전량 고속 로드 및 동적 행렬 빌드
@st.cache_data 
def fetch_and_build_matrices():
    data = []
    start_index = 0
    page_size = 1000 

    while True:
        response = (
            supabase.table("grid_master")
            .select("row_index, col_index, elevation, is_road")
            .range(start_index, start_index + page_size - 1)
            .execute()
        )
        chunk = response.data
        if not chunk:
            break
        data.extend(chunk)
        start_index += page_size
        if start_index > 85000:
            break

    st.sidebar.info(f"📊 DB 동기화 레코드 수: {len(data):,}개")

    # 💡 [버그 수정] 고정 크기(315x253) 대신 DB 레코드의 맥스 인덱스를 찾아 크기를 동적으로 빌드
    max_r = max(item['row_index'] for item in data)
    max_c = max(item['col_index'] for item in data)
    
    # 0번 인덱스 포함이므로 +1 크기로 할당 (31x25 가변 완벽 대응)
    terrain_matrix = np.zeros((max_r + 1, max_c + 1))
    road_matrix = np.zeros((max_r + 1, max_c + 1), dtype=bool)
    
    for item in data:
        r = item['row_index']
        c = item['col_index']
        terrain_matrix[r, c] = float(item['elevation'])
        road_matrix[r, c] = bool(item['is_road'])

    return terrain_matrix, road_matrix

with st.spinner("Supabase DB에서 원주 정밀 격자 데이터를 동기화하는 중..."):
    terrain_np, road_np = fetch_and_build_matrices()

rows, cols = terrain_np.shape
st.success(f"✅ 원주 격자 공간 데이터베이스 로드 완료! (실제 동적 규격: {rows}x{cols})")

# 데이터베이스 정합성 실시간 검증 사이드바
st.sidebar.write("🔍 데이터베이스 정합성 검증:")
st.sidebar.write(f"- 고도 범위: {terrain_np.min():.2f}m ~ {terrain_np.max():.2f}m")
st.sidebar.write(f"- 활성 임도 격자 수: {np.sum(road_np)} 개")

# 사이드바 설정 (물리 제어 변수)
st.sidebar.header("⚙️ 시뮬레이션 제어 변수")
base_spread_prob = st.sidebar.slider("기본 산불 확산 확률", 0.1, 1.0, 0.4, 0.05)
slope_coefficient = st.sidebar.slider("경도(고도 차이) 가중치", 0.01, 0.10, 0.03, 0.01)

# 💡 [바람 물리 UI 엔진 파라미터 추가]
st.sidebar.header("💨 실시간 기상 환경 세팅")
wind_speed = st.sidebar.slider("풍속 (Wind Speed, m/s)", 0.0, 15.0, 3.0, 0.5)
wind_direction = st.sidebar.selectbox("풍향 (Wind Direction)", ["N", "NE", "E", "SE", "S", "SW", "W", "NW"], index=6) # 디폴트 서풍(W)

max_steps = st.sidebar.slider("최대 시뮬레이션 타임스텝", 5, 50, 20, 5)

st.write("---")

st.write("### 📍 산불 발화점(화원) 및 환경 지정")
col_ui1, col_ui2 = st.columns(2)
with col_ui1:
    selected_row = st.number_input(f"발화점 Row 위치 (0~{rows-1})", min_value=0, max_value=rows-1, value=min(15, rows-1))
with col_ui2:
    selected_col = st.number_input(f"발화점 Col 위치 (0~{cols-1})", min_value=0, max_value=cols-1, value=min(12, cols-1))

if st.button("🔥 산불 시뮬레이션 가동"):
    plot_spot = st.empty()
    status_text = st.empty()
    
    start_time = time.time()
    
    # 3. 고도화된 외부 물리 엔진 모듈 호출 (바람 파라미터 주입으로 아규먼트 일치 완료)
    with st.spinner("simulation_engine에서 물리 알고리즘을 계산하는 중..."):
        history = run_wildfire_simulation(
            terrain_np=terrain_np,
            road_np=road_np,
            start_row=int(selected_row),
            start_col=int(selected_col),
            base_spread_prob=base_spread_prob,
            slope_coefficient=slope_coefficient,
            wind_speed=wind_speed,
            wind_direction=wind_direction,
            max_steps=max_steps
        )
    
    # 4. 애니메이션 실시간 렌더링
    for step, status_matrix in enumerate(history):
        status_text.text(f"⏳ 화면 렌더링 중... Step: {step}/{len(history)-1}")
        
        fig, ax = plt.subplots(figsize=(8.5, 6), tight_layout=True)
        ax.imshow(terrain_np, cmap="gist_earth", origin="upper", alpha=0.6)
        
        if np.sum(road_np) > 0:
            ax.imshow(np.ma.masked_where(~road_np, road_np), cmap="Blues_r", origin="upper", alpha=0.9)
            
        fire_mask = (status_matrix == 1) | (status_matrix == 2)
        if np.sum(fire_mask) > 0:
            ax.imshow(np.ma.masked_where(~fire_mask, status_matrix), cmap="Reds", origin="upper", alpha=0.8)
            
        ax.set_title(f"Simulation Step: {step} | Wind: {wind_direction} ({wind_speed} m/s)")
        ax.axis("off")
        
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=140)
        buf.seek(0)
        
        plot_spot.image(buf, use_container_width=False)
        plt.close(fig)
        time.sleep(0.08)
        
    execution_time = time.time() - start_time
    status_text.success(f"🎉 시뮬레이션 완료! (연산 및 시각화 소요 시간: {execution_time:.2f}초)")
    
    # 5. 최종 결과 통계 산출
    final_matrix = history[-1]
    final_burned_cells = int(np.sum(final_matrix == 2) + np.sum(final_matrix == 1))
    calculated_area = float(final_burned_cells * 90 * 90) # 격자당 해상도 면적 반영
    
    st.write("### 📊 최종 결과 요약 리포트")
    col_res1, col_res2 = st.columns(2)
    with col_res1:
        st.metric(label="🔥 소실된 총 격자 수", value=f"{final_burned_cells:,} 개")
    with col_res2:
        st.metric(label="📐 계산된 최종 소실 면적", value=f"{calculated_area:,} m²")
        
    # 6. 🔗 [DB 연동 이중화] simulation_logs 및 simulation_results 통합 저장
    try:
        # 로그 테이블 저장
        log_data = {
            "ignition_row": int(selected_row),
            "ignition_col": int(selected_col),
            "burned_area": float(calculated_area),
            "video_url": f"WIND_{wind_direction}_{wind_speed}m/s"
        }
        supabase.table("simulation_logs").insert(log_data).execute()
        
        # 결과 덤프 데이터베이스 테이블 동시 저장 (스키마 DDL 규칙 반영)
        result_data = {
            "region_name": "원주 용수골 계곡",
            "wind_speed": float(wind_speed),
            "wind_direction": str(wind_direction),
            "ignition_x": int(selected_col),
            "ignition_y": int(selected_row),
            "video_url": f"COMPLETED_STEPS_{len(history)-1}"
        }
        supabase.table("simulation_results").insert(result_data).execute()
        
        st.success("💾 시뮬레이션 결과 및 기상 이력이 Supabase 데이터베이스에 안전하게 동기화되었습니다.")
    except Exception as e:
        st.warning(f"⚠️ 데이터베이스 트랜잭션 기록 중 일부 오류 발생: {e}")