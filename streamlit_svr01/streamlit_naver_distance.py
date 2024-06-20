import streamlit as st
import pandas as pd
import sqlite3
from io import BytesIO
import requests
import folium
from streamlit_folium import folium_static

# 환경 변수 로드
client_id = st.secrets["naver"]["client_id"]
client_secret = st.secrets["naver"]["client_secret"]

# SQLite 데이터베이스 설정
conn = sqlite3.connect('locations.db')
c = conn.cursor()

# 테이블 생성
c.execute('''
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    departure_name TEXT,
    departure_address TEXT,
    arrival_name TEXT,
    arrival_address TEXT,
    distance INTEGER,
    duration INTEGER,
    fuel_cost INTEGER
)''')
conn.commit()

def insert_data(df):
    for _, row in df.iterrows():
        c.execute('SELECT COUNT(*) FROM locations WHERE departure_address = ? AND arrival_address = ?', 
                  (row[1], row[3]))
        count = c.fetchone()[0]
        if count == 0:
            c.execute('INSERT INTO locations (departure_name, departure_address, arrival_name, arrival_address) VALUES (?, ?, ?, ?)', 
                      (row[0], row[1], row[2], row[3]))
    conn.commit()

def geocode(address):
    # 주소를 위도와 경도로 변환하는 함수
    url = f"https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode?query={address}"
    headers = {
        'X-NCP-APIGW-API-KEY-ID': client_id,
        'X-NCP-APIGW-API-KEY': client_secret
    }
    response = requests.get(url, headers=headers)
    data = response.json()
    # print(data)

    if data['status'] == 'OK' and int(data['meta']['totalCount']) > 0:
        # 결과가 있는 경우 첫 번째 결과의 위도와 경도를 반환
        location = data['addresses'][0]
        latitude = location['y']
        longitude = location['x']
        return latitude, longitude
    else:
        return None, None

def calculate_distance(start_lat, start_lng, end_lat, end_lng):

    # print(start_lat, ", ", start_lng, ", ", end_lat, ", ", end_lng)
    # 네이버 지도 API를 통해 출발지와 도착지 간의 거리 계산
    url = f"https://naveropenapi.apigw.ntruss.com/map-direction/v1/driving?start={start_lng},{start_lat}&goal={end_lng},{end_lat}&option=trafast&cartype=3&fueltype=diesel&mileage=9.3"
    headers = {
        'X-NCP-APIGW-API-KEY-ID': client_id,
        'X-NCP-APIGW-API-KEY': client_secret
    }
    response = requests.get(url, headers=headers)
    data = response.json()

    #print(data)
    # 거리와 소요시간을 반환 
    distance = data['route']['trafast'][0]['summary']['distance']
    duration = data['route']['trafast'][0]['summary']['duration']
    toll_fee = data['route']['trafast'][0]['summary']['tollFare']
    taxi_fare = data['route']['trafast'][0]['summary']['taxiFare']
    fuel_price = data['route']['trafast'][0]['summary']['fuelPrice']
    return distance, duration, toll_fee,taxi_fare,fuel_price

def update_data(location_id, distance, duration, fuel_cost):
    c.execute('''
    UPDATE locations
    SET distance = ?, duration = ?, fuel_cost = ?
    WHERE id = ?
    ''', (distance, duration, fuel_cost, location_id))
    conn.commit()

# Streamlit 앱 구성
st.title("운송 정보 관리")

tabs = st.tabs(["엑셀 업로드", "거리 계산", "지도 표시"])

with tabs[0]:
    uploaded_file = st.file_uploader("엑셀 파일을 업로드하세요", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        st.write("업로드된 데이터:", df)
        insert_data(df)
        st.success("데이터가 데이터베이스에 성공적으로 삽입되었습니다.")

with tabs[1]:
    
    query = "SELECT * FROM locations"
    locations_df = pd.read_sql(query, conn)
    table_placeholder = st.empty()
    table_placeholder.write(locations_df)

    # 버튼을 가로로 배치하기 위해 컬럼을 나눔
    col1, col2 = st.columns([3, 1])  # 첫 번째 열은 버튼들을 포함할 공간, 두 번째 열은 여백용

    with col1:
        if st.button("거리 계산"):
            query_di = "SELECT * FROM locations where distance is null"
            locations_df_upd = pd.read_sql(query_di, conn)

            for _, row in locations_df_upd.iterrows():
                departure = row['departure_address']
                arrival   = row['arrival_address']
                departurelat, departurelng = geocode(departure)
                arrivallat,   arrivallng   = geocode(arrival)
                
                distance, duration, toll_fee, taxi_fare, fuel_price = calculate_distance(departurelat, departurelng, arrivallat, arrivallng)
                if distance is not None and duration is not None and fuel_price is not None:
                    update_data(row['id'], distance, duration, fuel_price)
            
            # 업데이트된 데이터 다시 읽기
            locations_df = pd.read_sql(query, conn)
            table_placeholder.write(locations_df)

    with col2:
        # 전체 데이터 삭제
        if st.button("데이터 삭제"):
            c.execute('DELETE FROM locations')
            conn.commit()
            
            # 업데이트된 데이터 다시 읽기
            locations_df = pd.read_sql(query, conn)
            table_placeholder.write(locations_df)

with tabs[2]:
    st.subheader("지도 표시")
    # map_data 초기화
    map_data = pd.DataFrame(columns=['lat', 'lon', 'name'])
    locations_df = pd.read_sql(query, conn)
    map_center = [37.5665, 126.9780]  # 서울의 위도와 경도
    m = folium.Map(location=map_center, zoom_start=11)

    for _, row in locations_df.iterrows():
        arrival_address = row['arrival_address']
        lat, lng = geocode(arrival_address)
        
        if lat is not None and lng is not None:
            map_data = pd.concat([map_data, pd.DataFrame({'lat': [float(lat)], 'lon': [float(lng)], 'name': [row['arrival_name']]})], ignore_index=True)
    
    st.map(map_data)
