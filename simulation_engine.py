import numpy as np

def run_wildfire_simulation(terrain_np, road_np, start_row, start_col, 
                            base_spread_prob, slope_coefficient, 
                            wind_speed, wind_direction, max_steps):
    """
    [산불 확산 시뮬레이션 고도화 물리 엔진 - 버그 교정 완료]
    - 기상학적 풍향 벡터 반전 적용 (순풍 방향 확산 가속, 역풍 감쇄 타원형 구현)
    - 임도(Forest Road) 방화선 차단 확률 무결성 복구 (0.10 기반 90% 강력 차단)
    """
    
    # 0: 미연소, 1: 연소 중, 2: 완전 소실(재)
    status_matrix = np.zeros_like(terrain_np, dtype=int)
    status_matrix[start_row, start_col] = 1  # 발화점 설정
    
    # 각 스텝별 격자 상태 스냅샷 저장
    history = [status_matrix.copy()]
    
    # 8방향 주변 탐색 오프셋 (북, 북동, 동, 남동, 남, 남서, 서, 북서)
    dr = [-1, -1, 0, 1, 1, 1, 0, -1]
    dc = [0, 1, 1, 1, 0, -1, -1, -1]
    
    # 8방향에 대한 각도(라디안) 매핑 (북쪽 0도 기준 시계방향)
    direction_angles = np.radians([0, 45, 90, 135, 180, 225, 270, 315])
    
    # 입력받은 풍향(텍스트 또는 각도)을 라디안 각도로 변환
    wind_dir_map = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}
    if isinstance(wind_direction, str):
        wind_angle = np.radians(wind_dir_map.get(wind_direction.upper(), 0))
    else:
        wind_angle = np.radians(wind_direction)
        
    rows, cols = terrain_np.shape
    
    for step in range(max_steps):
        current_status = history[-1]
        next_status = current_status.copy()
        
        burning_rows, burning_cols = np.where(current_status == 1)
        
        if len(burning_rows) == 0:
            break
            
        for r, c in zip(burning_rows, burning_cols):
            next_status[r, c] = 2  # 현재 불타는 셀은 다음 턴에 재가 됨
            
            for i in range(8):
                nr, nc = r + dr[i], c + dc[i]
                
                if 0 <= nr < rows and 0 <= nc < cols:
                    if current_status[nr, nc] == 0:
                        
                        # 1️⃣ [지형 경사 효과 계산]
                        elevation_diff = terrain_np[nr, nc] - terrain_np[r, c]
                        slope_effect = elevation_diff * slope_coefficient
                        
                        # 2️⃣ [바람 벡터 효과 계산 - 물리 부호 교정 💥]
                        # 기상학 풍향(바람이 오는 곳)을 물리적 추진 방향(바람이 불어가는 곳)으로 180도(+pi) 반전
                        pushed_wind_angle = wind_angle + np.pi
                        angle_diff = direction_angles[i] - pushed_wind_angle
                        
                        # 코사인 유사도 연산: 순풍 방향은 wind_effect 가 극대화되고 역풍 방향은 감쇄됨
                        wind_effect = wind_speed * np.cos(angle_diff) * 0.06 # 가중치 민감도를 0.06으로 살짝 상향
                        
                        # 3️⃣ [임도 방화선 확률적 감쇄 메커니즘 무결성 복구 🚧]
                        road_barrier = 1.0
                        if road_np[nr, nc] == 1:
                            # 0.10 기본값 세팅 = 90% 차단율 회복!
                            # 풍속 가중치 0.02를 적용하여 강풍 시 투과율이 유연하게 상승하도록 복구
                            road_barrier = 0.1 + (wind_speed * 0.010)
                            road_barrier = min(0.50, road_barrier) 
                        
                        # 4️⃣ [최종 종합 확산 확률 연산]
                        final_prob = (base_spread_prob + slope_effect + wind_effect) * road_barrier
                        final_prob = max(0.01, min(0.99, final_prob))
                        
                        # 몬테카를로 확률 판정
                        if np.random.rand() < final_prob:
                            next_status[nr, nc] = 1
                            
        history.append(next_status)
        
    return history