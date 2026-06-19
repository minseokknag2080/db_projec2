import numpy as np

def run_wildfire_simulation(terrain_np, road_np, start_row, start_col, 
                            base_spread_prob, slope_coefficient, 
                            wind_speed, wind_direction, max_steps):
    """
    [산불 확산 시뮬레이션 고도화 물리 엔진]
    - 지형 경사도(Elevation Slope Effect) 반영
    - 풍속 및 풍향에 따른 바람 벡터(Wind Vector Effect) 수학식 반영
    - 임도(Forest Road)를 만났을 때의 방화선 확률적 감쇄 및 저지 메커니즘 반영
    """
    
    # 0: 미연소, 1: 연소 중, 2: 완전 소실(재)
    status_matrix = np.zeros_like(terrain_np, dtype=int)
    status_matrix[start_row, start_col] = 1  # 발화점 설정
    
    # 각 스텝별 격자 상태 스냅샷 저장 (Streamlit 애니메이션 렌더링용)
    history = [status_matrix.copy()]
    
    # 8방향 주변 탐색 오프셋 (북, 북동, 동, 남동, 남, 남서, 서, 북서)
    dr = [-1, -1, 0, 1, 1, 1, 0, -1]
    dc = [0, 1, 1, 1, 0, -1, -1, -1]
    
    # 8방향에 대한 각도(라디안) 매핑 (북쪽 0도 기준 시계방향)
    # 북(0), 북동(45), 동(90), 남동(135), 남(180), 남서(225), 서(270), 북서(315)
    direction_angles = np.radians([0, 45, 90, 135, 180, 225, 270, 315])
    
    # 입력받은 풍향(텍스트 또는 각도)을 라디안 각도로 변환
    # 대소문자 방지 및 디폴트 처리
    wind_dir_map = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}
    if isinstance(wind_direction, str):
        wind_angle = np.radians(wind_dir_map.get(wind_direction.upper(), 0))
    else:
        wind_angle = np.radians(wind_direction) # 숫자로 들어올 경우 바로 라디안 변환
        
    rows, cols = terrain_np.shape
    
    for step in range(max_steps):
        current_status = history[-1]
        next_status = current_status.copy()
        
        burning_rows, burning_cols = np.where(current_status == 1)
        
        # 더 이상 연소 중인 화원이 없으면 시뮬레이션 조기 종료
        if len(burning_rows) == 0:
            break
            
        for r, c in zip(burning_rows, burning_cols):
            next_status[r, c] = 2  # 불타던 격자는 다음 턴에 재(Ash)가 됨
            
            for i in range(8):
                nr, nc = r + dr[i], c + dc[i]
                
                # 경계면 안쪽에 있고 아직 타지 않은 격자(0)인 경우 탐색
                if 0 <= nr < rows and 0 <= nc < cols:
                    if current_status[nr, nc] == 0:
                        
                        # 1️⃣ [지형 경사 효과 계산]
                        # 나보다 높은 곳으로 번질 때(diff > 0) 불길이 훨씬 빨라짐
                        elevation_diff = terrain_np[nr, nc] - terrain_np[r, c]
                        slope_effect = elevation_diff * slope_coefficient
                        
                        # 2️⃣ [바람 벡터 효과 계산 (핵심 추가)]
                        # 현재 번지려는 방향(direction_angles[i])과 바람이 부는 방향(wind_angle)의 사잇각 계산
                        angle_diff = direction_angles[i] - wind_angle
                        # 코사인 유사도를 활용하여 바람과 순풍일 때 가중치 극대화, 역풍일 때 감쇄
                        wind_effect = wind_speed * np.cos(angle_diff) * 0.05
                        
                        # 3️⃣ [임도 방화선 확률적 감쇄 메커니즘 (고도화)]
                        road_barrier = 1.0
                        if road_np[nr, nc] == 1:
                            # 기본적으로 임도는 불길을 강력하게 막아주지만(확률 85% 감소), 
                            # 풍속(wind_speed)이 강해지면 불씨가 날아갈 확률이 생기므로 차단력이 완화됨
                            road_barrier = 0.15 + (wind_speed * 0.02)
                            road_barrier = min(0.9, road_barrier) # 최소한의 방어선 한계 설정
                        
                        # 4️⃣ [최종 종합 확산 확률 연산]
                        final_prob = (base_spread_prob + slope_effect + wind_effect) * road_barrier
                        
                        # 확률적 예외 범위 제한 (0.02 ~ 0.98) 수치 안정성 확보
                        final_prob = max(0.02, min(0.98, final_prob))
                        
                        # 몬테카를로 확률 판정으로 확산 여부 결정
                        if np.random.rand() < final_prob:
                            next_status[nr, nc] = 1
                            
        history.append(next_status)
        
    return history