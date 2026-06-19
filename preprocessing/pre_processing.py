import os
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.enums import Resampling
from rasterio import features
from shapely.geometry import box
import matplotlib.pyplot as plt

def run_high_res_preprocessing_pipeline(shp_path, large_dem_path, output_dir='data/processed'):
    print("🚀 [Pipeline] 10m 고해상도 정밀 물리 엔진 가동 (Target: Exactly 10m Grid)...")
    os.makedirs(output_dir, exist_ok=True)
    
    terrain_npy_path = os.path.join(output_dir, 'terrain_data.npy')
    road_npy_path = os.path.join(output_dir, 'road_data.npy')
    validation_png_path = os.path.join(output_dir, 'pipeline_validation.png')

    # 1. 데이터 로드 및 좌표계 강제 동기화
    roads = gpd.read_file(shp_path)
    if roads.crs is None:
        roads.crs = "EPSG:5179"
        
    with rasterio.open(large_dem_path) as src:
        if roads.crs != src.crs:
            roads = roads.to_crs(src.crs)
        
        # 임도의 실제 미터 영역 확보 [minx, miny, maxx, maxy]
        road_bounds = roads.total_bounds  
        
        # 💡 [핵심 수정] 실제 미터 거리를 기반으로 정확한 10m 규격의 격자 크기 산출
        # 가로 2,250m -> 225칸 / 세로 2,790m -> 279칸
        target_res = 10.0
        new_width = int(np.ceil((road_bounds[2] - road_bounds[0]) / target_res))
        new_height = int(np.ceil((road_bounds[3] - road_bounds[1]) / target_res))
        
        # 거대 DEM과의 경계면 클리핑
        large_bounds = src.bounds
        dem_boundary_poly = box(large_bounds.left, large_bounds.bottom, large_bounds.right, large_bounds.top)
        roads_strictly_clipped = gpd.clip(roads, dem_boundary_poly)

        # 실제 미터 기준 거대 DEM 원본 픽셀 위치 인덱싱
        row_top, col_left = src.index(road_bounds[0], road_bounds[3])     
        row_bottom, col_right = src.index(road_bounds[2], road_bounds[1]) 

        r_start, r_end = min(row_top, row_bottom), max(row_top, row_bottom)
        c_start, c_end = min(col_left, col_right), max(col_left, col_right)
        window = rasterio.windows.Window(c_start, r_start, (c_end - c_start), (r_end - r_start))
        
        # 💡 10m 격자에 완벽하게 대응하는 공간 변환 행렬(Transform) 새로 구축
        dst_transform = rasterio.transform.from_bounds(
            road_bounds[0], road_bounds[1], road_bounds[2], road_bounds[3], new_width, new_height
        )
        
        # Bilinear 보간법으로 정확하게 Target 10m 크기로 리샘플링하여 지형 컷팅
        terrain_array = src.read(
            1,
            window=window,
            out_shape=(new_height, new_width),
            resampling=Resampling.bilinear
        )

    # 2. 고도 데이터 무결성 보정
    if np.any(terrain_array == src.nodata):
        terrain_array[terrain_array == src.nodata] = np.min(terrain_array[terrain_array != src.nodata])
        
    np.save(terrain_npy_path, terrain_array.astype(np.float32))
    print(f"✅ [10m 정밀 격자 변환 성공] 행렬 크기: {new_height} x {new_width} (총 {terrain_array.size:,} 격자)")

    # 3. 🛣️ 10m 그리드 트랜스폼 기준 정밀 임도 래스터화
    shapes = ((geom, 1) for geom in roads_strictly_clipped.geometry)
    road_grid = features.rasterize(
        shapes=shapes,
        out_shape=(new_height, new_width),
        transform=dst_transform,
        fill=0,
        all_touched=True
    )
    
    np.save(road_npy_path, road_grid.astype(np.uint8))
    print(f"💾 고화질 임도 격자 저장 완료 -> 활성 임도 격자: {np.sum(road_grid)}개")

    # 4. 검증 시각화 맵 생성
    extent = [road_bounds[0], road_bounds[2], road_bounds[1], road_bounds[3]]
    fig, ax = plt.subplots(figsize=(10, 10))
    im = ax.imshow(terrain_array, cmap='terrain', extent=extent, origin='upper', alpha=0.8)
    fig.colorbar(im, ax=ax, label='Elevation (m)')
    roads_strictly_clipped.plot(ax=ax, color='red', linewidth=2)
    
    plt.savefig(validation_png_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"🖼️ 검증 맵 저장 완료: {validation_png_path}")

if __name__ == "__main__":
    RAW_SHP_PATH = 'data/37712098/37712098.shp'
    RAW_LARGE_DEM_PATH = 'data/37712_dem.img'
    run_high_res_preprocessing_pipeline(RAW_SHP_PATH, RAW_LARGE_DEM_PATH)