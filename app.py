import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from supabase import create_client, Client
import time
import io
import imageio  # MP4 인코딩용

# 고도화된 물리 시뮬레이션 모듈 호출
from simulation_engine import run_wildfire_simulation

# Supabase 접속 설정
SUPABASE_URL = "https://gyvvqjngobgddlihmtlz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5dnZxam5nb2JnZGRsaWhtdGx6Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDMwODQ3MiwiZXhwIjoyMDk1ODg0NDcyfQ.EhuItbhoF_oO4c0vWSXtDCF4P2x4iN4t64I0DU9fPHk"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

st.set_page_config(page_title="산불 방재 시뮬레이터", layout="wide")
st.title("산불 실시간 시뮬레이터 & MP4 다운로더 (v5.2)")

# [CSS 고도화] 레이아웃 붕괴 방지
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
        border-radius: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Supabase DB에서 데이터 동적 로드
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

    max_r = max(item['row_index'] for item in data)
    max_c = max(item['col_index'] for item in data)
    
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
st.success(f"✅ 원주 격자 공간 데이터베이스 로드 완료! (동적 규격: {rows}x{cols})")

# 💡 [사이드바 설계 고도화] 학술 기준 가이드라인 캡션 심기
st.sidebar.header("⚙️ 시뮬레이션 제어 변수")

# 1. 기본 산불 확산 확률 및 기준 가이드
base_spread_prob = st.sidebar.slider("기본 산불 확산 확률", 0.1, 1.0, 0.45, 0.05)
st.sidebar.caption(
    "💡 **확산 확률 가이드라인 (국내 산림 기준)**\n"
    "- 🟢 **0.25 ~ 0.35**: 여름/가을철 (습한 수리적 환경)\n"
    "- 🔵 **0.45**: **연간 평균 범용 기준값** (디폴트 추천)\n"
    "- 🔴 **0.65 ~ 0.80**: **봄철 대형산불 조심기간** (양간지풍 및 극도 건조)"
)
st.sidebar.write("")

# 2. 경도 가중치 반영 비율 및 기준 가이드
slope_coefficient = st.sidebar.slider("경도(고도 차이) 가중치", 0.01, 0.10, 0.03, 0.01)
st.sidebar.caption(
    "💡 **경도 가중치 (Rothermel 화선 공식 기반)**\n"
)
st.sidebar.write("---")

# 3. 실시간 기상 환경 세팅
st.sidebar.header("💨 실시간 기상 환경 세팅")
wind_speed = st.sidebar.slider("풍속 (Wind Speed, m/s)", 0.0, 15.0, 3.0, 0.5)
st.sidebar.caption(
    "💡 **풍속 기준**: 3.0m/s (평균 풍속) | 8.0m/s 이상 (산불 경보)"
)
wind_direction = st.sidebar.selectbox("풍향 (Wind Direction)", ["N", "NE", "E", "SE", "S", "SW", "W", "NW"], index=6)

max_steps = st.sidebar.slider("최대 시뮬레이션 타임스텝", 10, 200, 100, 10)

st.write("---")

st.write("### 📍 산불 발화점 및 환경 지정")
col_ui1, col_ui2 = st.columns(2)
with col_ui1:
    selected_row = st.number_input(f"발화점 Row 위치 (0~{rows-1})", min_value=0, max_value=rows-1, value=min(140, rows-1))
with col_ui2:
    selected_col = st.number_input(f"발화점 Col 위치 (0~{cols-1})", min_value=0, max_value=cols-1, value=min(110, cols-1))

# 세션 상태 테이블 관리
if "download_mp4_bytes" not in st.session_state:
    st.session_state.download_mp4_bytes = None
if "final_stats" not in st.session_state:
    st.session_state.final_stats = None

if st.button("🔥 산불 실시간 시뮬레이션 가동"):
    st.session_state.download_mp4_bytes = None  # 리셋
    
    plot_spot = st.empty()  # 라이브 드로잉 공간
    status_text = st.empty()
    
    start_time = time.time()
    
    with st.spinner("물리 엔진 수치 연산 작동 중..."):
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
    
    video_frames = []
    
    for step, status_matrix in enumerate(history):
        status_text.text(f"⏳ 실시간 산불 확산 진행 중... Step: {step}/{len(history)-1}")
        
        fig, ax = plt.subplots(figsize=(9.5, 6), tight_layout=True)
        extent_m = [0, cols * 90, rows * 90, 0]
        
        im = ax.imshow(terrain_np, cmap="gist_earth", origin="upper", alpha=0.6, extent=extent_m)
        
        if np.sum(road_np) > 0:
            ax.imshow(np.ma.masked_where(~road_np, road_np), cmap="Blues_r", origin="upper", alpha=0.9, extent=extent_m)
            
        fire_mask = (status_matrix == 1) | (status_matrix == 2)
        if np.sum(fire_mask) > 0:
            ax.imshow(np.ma.masked_where(~fire_mask, status_matrix), cmap="Reds", origin="upper", alpha=0.8, extent=extent_m)
            
        fig.colorbar(im, ax=ax, shrink=0.85, pad=0.03).set_label("Elevation (m)", fontsize=10, weight='bold')
        ax.set_xlabel("Horizontal Distance (m)", weight='bold')
        ax.set_ylabel("Vertical Distance (m)", weight='bold')
        ax.set_title(f"Simulation Step: {step} | Wind: {wind_direction} ({wind_speed} m/s)", fontsize=12, weight='bold')
        ax.grid(True, color='gray', linestyle='--', alpha=0.3)
        
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
        buf.seek(0)
        
        # 1. 라이브 드로잉 출력
        img_bytes = buf.getvalue()
        plot_spot.image(img_bytes, use_container_width=False)
        
        # 2. 영상 인코딩용 프레임 수집
        frame_img = imageio.v3.imread(buf, extension='.png')
        video_frames.append(frame_img)
        
        plt.close(fig)
        time.sleep(0.02)  
        
    with st.spinner("🎞️ 백엔드에서 소장용 고화질 MP4 비디오 파일 생성 중..."):
        mp4_buf = io.BytesIO()
        imageio.v3.imwrite(mp4_buf, video_frames, extension='.mp4', plugin='FFMPEG', fps=12)
        st.session_state.download_mp4_bytes = mp4_buf.getvalue()

    execution_time = time.time() - start_time
    status_text.success(f"🎉 시뮬레이션 완료 및 비디오 빌드 완료! (소요 시간: {execution_time:.2f}초)")
    
    # 통계 계산 및 저장
    final_matrix = history[-1]
    final_burned_cells = int(np.sum(final_matrix == 2) + np.sum(final_matrix == 1))
    calculated_area = float(final_burned_cells * 90 * 90)
    st.session_state.final_stats = {"cells": final_burned_cells, "area": calculated_area}
    
    try:
        supabase.table("simulation_logs").insert({
            "ignition_row": int(selected_row), "ignition_col": int(selected_col),
            "burned_area": calculated_area, "video_url": f"METRIC_GUIDE_V5"
        }).execute()
    except Exception as e:
        st.sidebar.error(f"DB 로깅 실패: {e}")

st.write("---")

if st.session_state.download_mp4_bytes is not None:
    stats = st.session_state.final_stats
    
    st.write("### 📊 시뮬레이션 결과 요약 및 영상 내보내기")
    col_res1, col_res2 = st.columns(2)
    with col_res1:
        st.metric(label="🔥 소실된 총 격자 수 (10m)", value=f"{stats['cells']:,} 개")
    with col_res2:
        st.metric(label="📐 계산된 최종 피해 면적", value=f"{stats['area']:,} m²")
        
    st.write("")
    st.download_button(
        label="📥 시뮬레이션 실행 영상(MP4) 내보내기 및 다운로드",
        data=st.session_state.download_mp4_bytes,
        file_name=f"wildfire_sim_guided_{wind_direction}.mp4",
        mime="video/mp4",
        use_container_width=True
    )