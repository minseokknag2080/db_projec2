import streamlit as st
import numpy as np
from supabase import create_client, Client

# 1. Supabase 접속 설정
# 테스트 단계에서는 문자열을 직접 넣으셔도 되고, 나중에 .streamlit/secrets.toml에 숨기셔도 됩니다.
SUPABASE_URL = "https://gyvvqjngobgddlihmtlz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5dnZxam5nb2JnZGRsaWhtdGx6Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDMwODQ3MiwiZXhwIjoyMDk1ODg0NDcyfQ.EhuItbhoF_oO4c0vWSXtDCF4P2x4iN4t64I0DU9fPHk"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

st.title("🌲 원주 지역 임도 방재 성능 시뮬레이터")

# 2. Supabase DB에서 79,695개 격자 데이터를 고속 Batch Loading하여 NumPy 배열로 복원
@st.cache_data
def fetch_and_build_matrices():
    # 데이터 양이 많으므로 필요한 컬럼만 정확히 select
    response = supabase.table("grid_master").select("row_index, col_index, elevation, is_road").execute()
    data = response.data
    
    # 민석 님의 실제 전처리 파이프라인 규격(315 x 253)으로 빈 행렬 선언
    terrain_matrix = np.zeros((315, 253))
    road_matrix = np.zeros((315, 253), dtype=bool)
    
    # DB의 행/열 인덱스를 매핑 좌표 삼아 데이터 고속 복원
    for item in data:
        r = item['row_index']
        c = item['col_index']
        terrain_matrix[r, c] = item['elevation']
        road_matrix[r, c] = item['is_road']
        
    return terrain_matrix, road_matrix

with st.spinner("Supabase 데이터베이스에서 원주 정밀 격자 데이터를 로드하는 중..."):
    terrain_np, road_np = fetch_and_build_matrices()
st.success(f"✅ 데이터베이스 연동 성공! 지형 행렬 크기: {terrain_np.shape} 복원 완료")

# 3. 로드된 데이터 요약 통계 출력
st.write("### 📊 수집된 지형 공간 레이어 통계")
col1, col2 = st.columns(2)
with col1:
    st.metric(label="⛰️ 최고 고도", value=f"{np.max(terrain_np):.2f} m")
    st.metric(label="📉 최저 고도", value=f"{np.min(terrain_np):.2f} m")
with col2:
    st.metric(label="🧩 총 격자 해상도", value=f"{terrain_np.size:,} 개")
    st.metric(label="🛣️ 활성 임도 격자 수", value=f"{np.sum(road_np):,} 개")

st.write("---")

# 4. 시뮬레이션 발화점 선택 인터페이스
st.write("### 📍 산불 발화점(화원) 지정")
selected_row = st.number_input("발화점 Row 인덱스 (0~314)", min_value=0, max_value=314, value=150)
selected_col = st.number_input("발화점 Col 인덱스 (0~252)", min_value=0, max_value=252, value=120)

if st.button("🔥 동기식 산불 시뮬레이션 가동"):
    with st.spinner("물리 엔진 알고리즘 연산 및 애니메이션 렌더링 중..."):
        
        # ---------------------------------------------------------
        # [알고리즘 구현부 확장 영역]
        # TODO: 민석 님의 Modified Rothermel 및 Spotting Engine 구동
        # ---------------------------------------------------------
        
        # 가상의 결과 데이터 처리 프로세스
        simulated_cells = int(np.random.randint(50, 500))
        calculated_area = simulated_cells * 90 * 90  # 90m 격자 기준 면적 계산
        dummy_video_url = "https://www.w3schools.com/html/mov_bbb.mp4" # 테스트용 샘플 스트리밍 영상
        
        # 5. 시뮬레이션 결과를 DB 로그 테이블에 기록 (INSERT)
        log_data = {
            "ignition_row": selected_row,
            "ignition_col": selected_col,
            "burned_area": calculated_area,
            "video_url": dummy_video_url
        }
        supabase.table("simulation_logs").insert(log_data).execute()
        
    st.success("🎉 시뮬레이션 연산 및 DB 로그 기록이 완료되었습니다!")
    
    # 6. 최종 화면 리포트 드로잉
    st.write("### 📊 시뮬레이션 결과 리포트")
    st.metric(label="총 소실 면적", value=f"{calculated_area:,} m²")
    st.write(f"**지정 화원 좌표:** [{selected_row}, {selected_col}]")
    
    st.write("### 🎬 산불 확산 애니메이션")
    st.video(dummy_video_url)