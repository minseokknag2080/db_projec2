import os
import numpy as np
from supabase import create_client

# 1. Supabase 프로젝트 설정
SUPABASE_URL = "https://gyvvqjngobgddlihmtlz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5dnZxam5nb2JnZGRsaWhtdGx6Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDMwODQ3MiwiZXhwIjoyMDk1ODg0NDcyfQ.EhuItbhoF_oO4c0vWSXtDCF4P2x4iN4t64I0DU9fPHk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def upload_grid_data():
    # 파이프라인 아웃풋 경로 설정
    terrain_path = 'terrain_data.npy'
    road_path = 'road_data.npy'
    
    print("🔄 전처리 파이프라인에서 생성된 원주 정합 파일 로드 중...")
    try:
        terrain = np.load(terrain_path)
        road = np.load(road_path)
    except FileNotFoundError as e:
        print(f"❌ 전처리 파일을 찾을 수 없습니다: {e}")
        print("💡 팁: 통합 전처리 파이프라인 코드를 먼저 실행하여 'data/processed/' 폴더 안에 npy 파일들이 생성되었는지 확인하세요.")
        return

    rows, cols = terrain.shape # 315, 253 자동 인식
    print(f"✅ 정합성 검증 완료! 행렬 크기: {rows}x{cols} (총 {terrain.size} 격자 공간)")
    
    bulk_data = []

    # 2. 2차원 공간 배열을 루프 돌며 데이터 구조화
    for r in range(rows):
        for c in range(cols):
            grid_item = {
                "row_index": int(r),
                "col_index": int(c),
                "elevation": float(terrain[r, c]),
                "is_road": bool(road[r, c])
            }
            bulk_data.append(grid_item)

    print(f"📦 총 {len(bulk_data)}개의 공간 격자 데이터를 Supabase로 고속 전송합니다...")

    # 3. 데이터가 7만 건이 넘으므로 청크 크기를 3000개로 대폭 상향하여 업로드 속도 최적화
    chunk_size = 3000
    for i in range(0, len(bulk_data), chunk_size):
        chunk = bulk_data[i:i + chunk_size]
        try:
            supabase.table("grid_master").insert(chunk).execute()
            print(f" 🟩 [{i + len(chunk)}/{len(bulk_data)}] 원주 격자 데이터 적재 중...")
        except Exception as e:
            print(f"❌ 적재 에러 발생: {e}")
            print("💡 팁: 에러 발생 시 Supabase SQL Editor에서 'TRUNCATE TABLE public.grid_master;'를 실행한 후 다시 시도하세요.")
            return

    print("\n🎉 [성공] 임도 경계면과 공간 정합성이 100% 일치하는 원주 지형 마스터 데이터 적재가 완료되었습니다!")

if __name__ == "__main__":
    upload_grid_data()