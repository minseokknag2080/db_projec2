import os
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterio import features
from shapely.geometry import box
import matplotlib.pyplot as plt

def run_integrated_preprocessing_pipeline(shp_path, large_dem_path, output_dir='data/processed'):
    print("🚀 [Pipeline] Codespace 클라우드 환경 정밀 전처리 엔진 가동...")
    os.makedirs(output_dir, exist_ok=True)
    
    # 클라우드 리눅스 호환 상대 경로 정의
    terrain_npy_path = os.path.join(output_dir, 'terrain_data.npy')
    road_npy_path = os.path.join(output_dir, 'road_data.npy')
    validation_png_path = os.path.join(output_dir, 'pipeline_validation.png')

    # 1. 데이터 로드 및 CRS 동기화
    roads = gpd.read_file(shp_path)
    with rasterio.open(large_dem_path) as src:
        if roads.crs != src.crs:
            roads = roads.to_crs(src.crs)
        
        # 임도의 실제 미터 영역을 정확하게 사각형 객체로 생성
        road_bounds = roads.total_bounds  # [minx, miny, maxx, maxy]
        
        # 거대 DEM의 전체 수학적 변환 행렬 및 경계 정보 저장
        large_transform = src.transform
        large_bounds = src.bounds

        # 2. 🛡️ [방법 A] 거대 DEM 전체 경계를 넘어서는 임도 선 제거 (공간 클리핑)
        dem_boundary_poly = box(large_bounds.left, large_bounds.bottom, large_bounds.right, large_bounds.top)
        roads_strictly_clipped = gpd.clip(roads, dem_boundary_poly)

        # 3. 💡 [Y축 왜곡 보정] 실제 미터 좌표를 기준으로 거대 DEM에서 정확한 인덱스 픽셀 범위 계산
        row_top, col_left = src.index(road_bounds[0], road_bounds[3])     # 왼쪽 위 (MinX, MaxY)
        row_bottom, col_right = src.index(road_bounds[2], road_bounds[1]) # 오른쪽 아래 (MaxX, MinY)

        # 인덱스 순서 정렬
        r_start, r_end = min(row_top, row_bottom), max(row_top, row_bottom)
        c_start, c_end = min(col_left, col_right), max(col_left, col_right)

        # 4. 🎯 진짜 용수골 계곡 위치의 고도 데이터 행렬 슬라이싱 크롭
        large_dem_array = src.read(1)
        terrain_array = large_dem_array[r_start:r_end, c_start:c_end]
        
        # 잘려진 구역에 최적화된 새로운 공간 변환 행렬(Transform) 생성
        clipped_transform = rasterio.windows.transform(
            rasterio.windows.Window(c_start, r_start, (c_end - c_start), (r_end - r_start)), 
            large_transform
        )

    # 5. 지형 데이터 고도 무결성 처리
    if np.any(terrain_array == src.nodata):
        terrain_array[terrain_array == src.nodata] = np.min(terrain_array[terrain_array != src.nodata])
        
    np.save(terrain_npy_path, terrain_array.astype(np.float32))
    height, width = terrain_array.shape
    print(f"✅ [수정 완료] 진짜 지형 도려내기 성공 -> 행렬 규격: {width} x {height}")
    print(f"💾 지형 고도 배열 저장 성공: {terrain_npy_path}")

    # 6. 임도 선 데이터 래스터화 (새로운 정밀 변환 행렬 기준)
    shapes = ((geom, 1) for geom in roads_strictly_clipped.geometry)
    road_grid = features.rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=clipped_transform,
        fill=0,
        all_touched=True
    )
    
    np.save(road_npy_path, road_grid.astype(np.uint8))
    print(f"💾 임도 네트워크 배열 저장 성공: {road_npy_path}")
    print(f"🔥 총 {road_grid.size}개 셀 중 임도가 매핑된 활성 격자 수: {np.sum(road_grid)}개")

    # 7. 최종 시각화 검증 맵 생성 (Inverted Y-axis 보정 적용)
    extent = [road_bounds[0], road_bounds[2], road_bounds[1], road_bounds[3]]
    fig, ax = plt.subplots(figsize=(10, 10))
    
    # origin='upper' 설정을 적용하여 국가 지형 사이트와 고도 메커니즘 일치
    im = ax.imshow(terrain_array, cmap='terrain', extent=extent, origin='upper', alpha=0.8)
    fig.colorbar(im, ax=ax, label='Elevation (m)')
    
    roads_strictly_clipped.plot(ax=ax, color='red', linewidth=3, label='Forest Road (Strictly Clipped)')
    
    ax.set_title(f'Fixed Precision Overlay Validation ({width}x{height} Grid)', fontsize=14)
    ax.set_xlabel('X Coordinate (UTM-K / m)')
    ax.set_ylabel('Y Coordinate (UTM-K / m)')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(loc='upper right')
    ax.set_xlim(road_bounds[0], road_bounds[2])
    ax.set_ylim(road_bounds[1], road_bounds[3])
    
    # 💡 Codespace(클라우드 리눅스) 환경이므로 팝업창(plt.show()) 대신 PNG 이미지 저장을 수행합니다.
    plt.savefig(validation_png_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"🖼️  최종 정밀 검증 맵 이미지 내보내기 완료: {validation_png_path}")
    print("\n🎉 Codespace 데이터 전처리 완료! 이제 이 무결한 npy 파일들을 메인 엔진에 연동할 수 있습니다.")

if __name__ == "__main__":
    # 💡 민석 님의 Codespace 파일 탐색기 구조를 완벽하게 반영한 리눅스 상대 경로 세팅
    RAW_SHP_PATH = 'data/37712098/37712098.shp'
    RAW_LARGE_DEM_PATH = 'data/37712_dem.img'
    
    run_integrated_preprocessing_pipeline(RAW_SHP_PATH, RAW_LARGE_DEM_PATH)