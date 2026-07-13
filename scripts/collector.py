import time
import requests
import duckdb


con = duckdb.connect('../data/flights.duckdb')

con.execute("""
    CREATE TABLE IF NOT EXISTS flight_tracker (
        timestamp TIMESTAMP,
        icao24 VARCHAR,
        callsign VARCHAR,
        latitude DOUBLE,
        longitude DOUBLE,
        altitude_baro REAL,
        velocity REAL,
        true_track REAL,
        vertical_rate REAL
    )
""")
print("DuckDB storage initialized successfully.")

# Define geographic Bounding Box (Central Europe airspace)
AREA = {
    'lamin': 45.0,
    'lomin': 5.0,
    'lamax': 55.0,
    'lomax': 20.0
}

URL = f"https://opensky-network.org/api/states/all?lamin={AREA['lamin']}&lomin={AREA['lomin']}&lamax={AREA['lamax']}&lomax={AREA['lomax']}"


def fetch_and_save():
    try:
        response = requests.get(URL, timeout=10)

        # Handle API rate limits gracefully
        if response.status_code == 429:
            print(f"[{time.strftime('%X')}] API rate limit reached. Waiting for the next cycle...")
            return
        elif response.status_code != 200:
            print(f"[{time.strftime('%X')}] OpenSky API error: Status code {response.status_code}")
            return

        data = response.json()
        states = data.get('states')

        if not states:
            print(f"[{time.strftime('%X')}] No aircraft detected in the target area.")
            return

        # Convert state vector epoch time to human-readable timestamp
        current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(data.get('time')))
        batch = []

        # Parse raw state vectors from OpenSky payload
        for row in states:
            # Skip records missing crucial spatial coordinates
            if row[5] is None or row[6] is None:
                continue

            flight_data = (
                current_time,
                str(row[0]).strip(),
                str(row[1]).strip() if row[1] else 'UNKNOWN',
                float(row[6]),  # Latitude
                float(row[5]),  # Longitude
                float(row[7]) if row[7] is not None else 0.0,  # Barometric Altitude (meters)
                float(row[9]) if row[9] is not None else 0.0,  # Ground Speed (m/s)
                float(row[10]) if row[10] is not None else 0.0,  # True Track (degrees)
                float(row[11]) if row[11] is not None else 0.0  # Vertical Rate (m/s)
            )
            batch.append(flight_data)

        # Execute bulk insert into DuckDB for high-throughput efficiency
        if batch:
            con.executemany("""
                INSERT INTO flight_tracker VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            print(f"[{time.strftime('%X')}] Successfully ingested {len(batch)} rows.")

    except Exception as e:
        print(f"Pipeline execution error: {e}")


if __name__ == '__main__':
    print("Starting live flight tracking ETL pipeline...")
    print("Press Ctrl + C to terminate.")

    while True:
        fetch_and_save()
        # 25-second interval to avoid IP blocking on public tier
        time.sleep(25)