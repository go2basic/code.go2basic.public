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
        c.execute('INSERT INTO locations (departure_name, departure_address, arrival_name, arrival_address) VALUES (?, ?, ?, ?)', 
                  (row[0], row[1], row[2], row[3]))
    conn.commit()

# 네이버 API 설정
naver_map_api_url = "https://naveropenapi.apigw.ntruss.com/map-direction/v1/driving"

def calculate_distance_time_fuel(departure, arrival):
    headers = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
    }
    params = {
        "start": departure,
        "goal": arrival,
    }
    response = requests.get(naver_map_api_url, headers=headers, params=params)
    data = response.json()
    
    if response.status_code == 200 and 'route' in data:
        summary = data['route']['traoptimal'][0]['summary']
        distance = summary['distance']
        duration = summary['duration']
        fuel_cost = summary['fuelPrice']
        return distance, duration, fuel_cost
    else:
        return None, None, None

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
    st.header("엑셀 파일 업로드")
    uploaded_file = st.file_uploader("엑셀 파일을 업로드하세요", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        st.write("업로드된 데이터:", df)
        insert_data(df)
        st.success("데이터가 데이터베이스에 성공적으로 삽입되었습니다.")

with tabs[1]:
    st.header("거리 계산")
    query = "SELECT * FROM locations"
    locations_df = pd.read_sql(query, conn)
    st.write("등록된 출발지와 도착지:", locations_df)
    
    if st.button("거리 계산"):
        results = []
        for _, row in locations_df.iterrows():
            departure = row['departure_address']
            arrival = row['arrival_address']
            distance, duration, fuel_cost = calculate_distance_time_fuel(departure, arrival)
            if distance is not None and duration is not None and fuel_cost is not None:
                update_data(row['id'], distance, duration, fuel_cost)
                results.append([row['departure_name'], row['arrival_name'], distance, duration, fuel_cost])
        
        results_df = pd.DataFrame(results, columns=["출발지", "도착지", "거리(m)", "시간(ms)", "주유비(원)"])
        st.write("계산된 결과:", results_df)

with tabs[2]:
    st.header("지도 표시")
    locations_df = pd.read_sql(query, conn)
    map_center = [37.5665, 126.9780]  # 서울의 위도와 경도
    m = folium.Map(location=map_center, zoom_start=11)

    for _, row in locations_df.iterrows():
        arrival_address = row['arrival_address']
        # 여기에 위도와 경도 추출 로직 추가
        # 네이버 지오코딩 API를 사용할 수 있습니다.
        geocode_url = f"https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode"
        headers = {
            "X-NCP-APIGW-API-KEY-ID": client_id,
            "X-NCP-APIGW-API-KEY": client_secret,
        }
        params = {
            "query": arrival_address
        }
        response = requests.get(geocode_url, headers=headers, params=params)
        geocode_data = response.json()
        
        if response.status_code == 200 and geocode_data['addresses']:
            lat = geocode_data['addresses'][0]['y']
            lon = geocode_data['addresses'][0]['x']
            folium.Marker([lat, lon], tooltip=row['arrival_name']).add_to(m)
    
    folium_static(m)
