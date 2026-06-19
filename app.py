# app.py
import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from supabase import create_client, Client
import time
import io  # 차트를 메모리 이미지 버퍼로 변환하기 위해 필요합니다.

# 우리가 새로 만든 시뮬레이션 모듈의 함수를 가져옵니다!
from simulation_engine import run_wildfire_simulation

# 1. Supabase 접속 설정
SUPABASE_URL = "https://gyvvqjngobgddlihmtlz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5dnZxam5nb2JnZGRsaWhtdGx6Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDMwODQ3MiwiZXhwIjoyMDk1ODg0NDcyfQ.EhuItbhoF_oO4c0vWSXtDCF4P2x4iN4t64I0DU9fPHk"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

st.set_page_config(page_title="원주 산불 방재 시뮬레이터", layout="wide")
st.title("🌲 원주 지역 임도 기반 산불 확산 MVP 시뮬레이터 (엔진 분리형)")

# 🔥 [CSS 고도화] 브라우저 확대/축소(Ctrl+휠) 시 주변 웹 요소들이 지도를 밀어내지 못하도록 레이아웃 붕괴 방지
st.markdown(
    """
    <style>
    /* 1. 메인 본문 컨테이너가 무분별하게 압착되는 것을 방지 */
    .block-container {
        max-width: 1200px !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        margin: 0 auto !important;
    }
    
    /* 💡 지도 이미지의 크기를 가로 800px로 딱 고정합니다. */
    /* 이렇게 하면 브라우저를 확대했을 때 글자처럼 이미지도 돋보기 댄 것처럼 같이 커집니다! */
    .stImage img {
        width: 800px !important;
        height: auto !important; 
        object-fit: contain !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 2. Supabase DB에서 데이터 전량 고속 로드
@st.cache_data 
def fetch_and_build_matrices():
    data = []
    start_index = 0
    page_size = 1000    #서버 규격에 맞게 1000개씩 쪼개서 요청 

    while True:
        #대용량 리미트 해재: .range(0,85000)을 붙여 7만 9천 개 데이터를 끊김 없이 통째로 가져옴
        response = (
            supabase.table("grid_master")
            .select("row_index, col_index, elevation, is_road")
            .range(start_index, start_index + page_size -1)
            .execute()
        )

        chunk = response.data
        if not chunk: # 더 이상 가져올 데이터 없음
            break
            
        data.extend(chunk)
        start_index += page_size
        
        #데이터가 어무 많으므로 85,000개가 넘어가면 무한루프 방지를 위해 브레이크
        if start_index > 85000:
            break


    #디버깅 포인트 1 - db에서 넘어온 데이터 행의 총 개수를 사이드 바에 출력 
    st.sidebar.info(f"db에서 가져온 레코드 수: {len(data):,}개")

    terrain_matrix = np.zeros((315, 253))
    road_matrix = np.zeros((315, 253), dtype=bool)
    
    #데이터 행렬 매핑 시작 
    for item in data:
        r = item['row_index']
        c = item['col_index']
        terrain_matrix[r, c] = item['elevation']
        road_matrix[r, c] = item['is_road']
        #문자열이나 숫자로 들어와도 bool로 강제 변환
        road_matrix[r,c] = bool(item['is_road'])

    return terrain_matrix, road_matrix

with st.spinner("Supabase DB에서 원주 정밀 격자 데이터를 동기화하는 중..."):
    terrain_np, road_np = fetch_and_build_matrices()
st.success(f"✅ 원주 격자 공간 데이터베이스 로드 완료! (규격: {terrain_np.shape})")

# #디버깅 코드 추가  - 추가로 데이터가 어떤 모양으로 들어오는지 상단에 출력 (3개만 임시 조회)
# try:
#     sample_res = supabase.table("grid_master").select("row_index, col_index, elevation, is_road"). limit(3).execute()
#     st.sidebar.write("db 데이터 샘플(3개) :")
#     st.sidebar.json(sample_res.data)
# except Exception as e:
#     st.sidebar.error(f"샘플 로드 실패: {e}")

#디버깅 코드 추가 - 터미널이나 화면에 실제 고도 수치가 유효한지 출력
st.sidebar.write(" 데이터베이스 정합성 실시간 검증 : ")
st.sidebar.write(f"- 고도 최솟값: {terrain_np.min() : .2f} m")
st.sidebar.write(f"- 고도 최댓값: {terrain_np.max() : .2f} m")
st.sidebar.write(f"- 활성 임도 격자 수: {np.sum(road_np)} 개")

# 사이드바 설정
st.sidebar.header("⚙️ 시뮬레이션 제어 변수")
base_spread_prob = st.sidebar.slider("기본 산불 확산 확률", 0.1, 1.0, 0.4, 0.05)
slope_coefficient = st.sidebar.slider("경도(고도 차이) 가중치 반사율", 0.01, 0.10, 0.03, 0.01)
max_steps = st.sidebar.slider("최대 시뮬레이션 타임스텝(Steps)", 5, 50, 20, 5)

st.write("---")

st.write("### 📍 산불 발화점(화원) 및 환경 지정")
col_ui1, col_ui2 = st.columns(2)
with col_ui1:
    selected_row = st.number_input("발화점 Row 위치 (0~314)", min_value=0, max_value=314, value=150)
with col_ui2:
    selected_col = st.number_input("발화점 Col 위치 (0~252)", min_value=0, max_value=252, value=120)

if st.button("🔥 산불 시뮬레이션 시작"):
    
    plot_spot = st.empty()
    status_text = st.empty()
    
    start_time = time.time()
    
    # 3. 분리된 외부 엔진 모듈을 호출하여 연산 결과(History 리스트)를 통째로 받아옵니다!
    with st.spinner("simulation_engine에서 물리 알고리즘을 계산하는 중..."):
        history = run_wildfire_simulation(
            terrain_np=terrain_np,
            road_np=road_np,
            start_row=selected_row,
            start_col=selected_col,
            base_spread_prob=base_spread_prob,
            slope_coefficient=slope_coefficient,
            max_steps=max_steps
        )
    
    # 4. 연산된 히스토리를 한 루프씩 돌며 화면에 루프 드로잉 (애니메이션 렌더링)
    for step, status_matrix in enumerate(history):
        status_text.text(f"⏳ 화면 렌더링 중... Step: {step}/{len(history)-1}")
        
        # 💡 [변경] 도화지의 물리적 크기를 약간 키우고 여백 자동 정렬 셋업 유지
        fig, ax = plt.subplots(figsize=(8.5, 6), tight_layout=True)
        ax.imshow(terrain_np, cmap="gist_earth", origin="upper", alpha=0.6)
        
        if np.sum(road_np) > 0:
            ax.imshow(np.ma.masked_where(~road_np, road_np), cmap="Blues_r", origin="upper", alpha=0.9)
            
        fire_mask = (status_matrix == 1) | (status_matrix == 2)
        if np.sum(fire_mask) > 0:
            ax.imshow(np.ma.masked_where(~fire_mask, status_matrix), cmap="Reds", origin="upper", alpha=0.8)
            
        ax.set_title(f"Simulation Step: {step}")
        ax.axis("off")
        
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=140)
        buf.seek(0)
        
        #use_container_width를 False로 변경 -> 창 크기에 반응하지 않고
        #위에서 CSS로 설정한 800px 고정 크기를 그대로 유지하게 만듦
        plot_spot.image(buf, use_container_width=False)
        
        plt.close(fig)
        time.sleep(0.08)
        
    execution_time = time.time() - start_time
    status_text.success(f"🎉 시뮬레이션 완료! (연산 및 시각화 소요 시간: {execution_time:.2f}초)")
    
    # 5. 최종 결과 통계 및 DB 로그 저장
    final_matrix = history[-1]
    final_burned_cells = np.sum(final_matrix == 2) + np.sum(final_matrix == 1)
    calculated_area = final_burned_cells * 90 * 90
    
    st.write("### 📊 최종 결과 요약 리포트")
    col_res1, col_res2 = st.columns(2)
    with col_res1:
        st.metric(label="🔥 소실된 총 격자 수", value=f"{final_burned_cells:,} 개")
    with col_res2:
        st.metric(label="📐 계산된 최종 소실 면적", value=f"{calculated_area:,} m²")
        
    try:
        log_data = {
            "ignition_row": int(selected_row),
            "ignition_col": int(selected_col),
            "burned_area": float(calculated_area),
            "video_url": "MODULAR_ENGINE_RENDER"
        }
        supabase.table("simulation_logs").insert(log_data).execute()
        st.success("💾 시뮬레이션 실행 이력이 Supabase 로그 테이블에 정상적으로 저장되었습니다.")
    except Exception as e:
        st.warning(f"⚠️ 로그 데이터 기록 중 오류 발생: {e}")