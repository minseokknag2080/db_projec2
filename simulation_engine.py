# simulation_engine.py
import numpy as np

def run_wildfire_simulation(terrain_np, road_np, start_row, start_col, base_spread_prob, slope_coefficient, max_steps):
    """
    [산불 확산 시뮬레이션 핵심 물리 엔진]
    - app.py와 독립되어 연산만 수행합니다.
    - 향후 Modified Rothermel 공식이나 PINN 연산 코드를 적용할 때 이 함수 내부만 수정하면 됩니다.
    """
    # 0: 미연소, 1: 연소 중, 2: 완전 소실
    status_matrix = np.zeros_like(terrain_np, dtype=int)
    status_matrix[start_row, start_col] = 1  # 발화점 설정
    
    # 각 스텝별 격자 상태의 스냅샷을 저장하여 애니메이션용으로 리턴
    history = [status_matrix.copy()]
    
    # 8방향 주변 탐색 오프셋
    dr = [-1, -1, -1,  0, 0,  1, 1, 1]
    dc = [-1,  0,  1, -1, 1, -1, 0, 1]
    
    rows, cols = terrain_np.shape
    
    for step in range(max_steps):
        current_status = history[-1]
        next_status = current_status.copy()
        
        burning_rows, burning_cols = np.where(current_status == 1)
        
        # 더 이상 탈 수 있는 화원이 없으면 조기 종료
        if len(burning_rows) == 0:
            break
            
        for r, c in zip(burning_rows, burning_cols):
            next_status[r, c] = 2  # 현재 불타는 셀은 다음 턴에 재(Ash)가 됨
            
            for i in range(8):
                nr, nc = r + dr[i], c + dc[i]
                
                if 0 <= nr < rows and 0 <= nc < cols:
                    if next_status[nr, nc] == 0:
                        
                        # [방재 차단벽]: 임도 구역이면 확산 전파 차단
                        if road_np[nr, nc]:
                            continue
                            
                        # 경사도에 따른 고도 차이 계산
                        elevation_diff = terrain_np[nr, nc] - terrain_np[r, c]
                        
                        # 최종 확산 확률 연산 (수학식 가중치 적용)
                        final_prob = base_spread_prob + (elevation_diff * slope_coefficient)
                        final_prob = max(0.05, min(0.95, final_prob))
                        
                        if np.random.rand() < final_prob:
                            next_status[nr, nc] = 1
                            
        history.append(next_status)
        
    return history