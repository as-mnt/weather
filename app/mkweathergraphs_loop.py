import os
import requests
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from influxdb_client import InfluxDBClient
import seaborn as sns
from scipy.ndimage import gaussian_filter1d
import datetime
import time
from datetime import datetime, timedelta


def get_config():
    return {
        'INFLUX_URL': os.getenv('INFLUX_URL'),
        'INFLUX_TOKEN': os.getenv('INFLUX_TOKEN'),
        'INFLUX_ORG': os.getenv('INFLUX_ORG'),
        'INFLUX_BUCKET': os.getenv('INFLUX_BUCKET'),
        'NEOCITIES_TOKEN': os.getenv('NEOCITIES_TOKEN'),
        'NEOCITIES_URL': os.getenv('NEOCITIES_URL'),
        'WAIT_SECONDS': int(os.getenv('WAIT_SECONDS', 3600)),
        'WEBHOST_URL': os.getenv('WEBHOST_URL'),
        'DO_LOOP': os.getenv('LOOP', 'true').lower() == 'true',
        'DEBUG': os.getenv('DEBUG', 'false').lower() == 'true',
        'GRAPHS_PATH': 'graphs',
        'INDEX_HTML': 'index.html'
    }

def upload_to_neocities(filename, api_url, api_token, webhost_url):
    try:
        with open(filename, "rb") as f:
            files = {filename: f}
            headers = {"Authorization": f"Bearer {api_token}"}
            response = requests.post(api_url, files=files, headers=headers)
        
        fileurl = f"{webhost_url}/{filename}"
        if response.status_code == 200:
            print(f"File uploaded: {fileurl}")
            return fileurl
        else:
            print(f"Error: {response.text}")
            return None
    except Exception as e:
        print(f"Upload failed: {e}")
        return None

def generate_beautiful_graph(query_api, config, range_spec, measurement, field, ylabel, title, filename=None):
    query = f'from(bucket: "{config["INFLUX_BUCKET"]}") |> range({range_spec}) \
                                              |> filter(fn: (r) => r._measurement == "{measurement}") \
                                              |> filter(fn: (r) => r._field == "{field}") \
                                              |> aggregateWindow(every: 5m, fn: mean, createEmpty: false) \
                                              |> yield(name: "mean")'
    
    tables = query_api.query(query)
    times, values = [], []
    for table in tables:
        for record in table.records:
            # Shift time to local (assuming +6h as in original code)
            times.append(record.get_time() + timedelta(hours=6))
            values.append(record.get_value())

    if not times:
        print(f"No data for {measurement}:{field}")
        return None

    sns.set_style('darkgrid')
    plt.style.use("seaborn-v0_8-darkgrid")
    fig, ax = plt.subplots(figsize=(3, 1))

    values_smooth = gaussian_filter1d(values, sigma=2)

    ax.plot(times, values_smooth, linestyle="-", 
            color="#FF5733", linewidth=0.5, alpha=0.9)

    ax.set_xlabel("время", fontsize=4)
    ax.set_ylabel(ylabel, fontsize=4)
    ax.set_title(title, fontsize=4)
    plt.xticks(rotation=30, fontsize=4)
    plt.yticks(fontsize=4)

    ax.grid(which='major', color='darkgray', linestyle='-', linewidth=0.2)
    ax.minorticks_on()
    ax.grid(which='minor', color='lightgray', linestyle=':', linewidth=0.2)

    if not filename:
        filename = f"{config['GRAPHS_PATH']}/{measurement}-{field}.png"
    
    if config['DEBUG']: print(f"{current_timestamp()} Saving to {filename}")
    plt.savefig(filename, dpi=200, bbox_inches="tight")
    plt.close(fig)
    if config['DEBUG']: print(f"{current_timestamp()} Saved and closed.")

    if config['DEBUG']: print(f"{current_timestamp()} Uploading {filename}")
    url = upload_to_neocities(filename, config['NEOCITIES_URL'], config['NEOCITIES_TOKEN'], config['WEBHOST_URL'])
    
    if url:
        return {"status": "success", "image_url": url}
    else:
        return {"status": "error", "message": "Failed to upload"}

def generate_retro_beautiful_graph(query_api, config, stepback, measurement, field, ylabel, title):
    filename = f"{config['GRAPHS_PATH']}/{measurement}-{field}-{stepback}.png"
    return generate_beautiful_graph(query_api, config, f"start: {stepback}", measurement, field, ylabel, title, filename)

def current_timestamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def run_once(query_api, config):
    ct = current_timestamp()
    print(f"{ct} fetching and looping\n")
    
    metrics = [
        ("-2d", "weather", "temperature_2m", "t, C", "Температура воздуха на 2м"),
        ("-2d", "weather", "surface_pressure", "p, hPa", "Атмосферное давление у земли"),
        ("-2d", "weather", "relative_humidity_2m", "hum, %", "Относительная влажность на 2м"),
        ("-2d", "pollution", "components_pm2_5", "pm25", "Загрязнение частицами pm2,5"),
        ("-2w", "weather", "temperature_2m", "t, C", "Температура воздуха на 2м"),
        ("-2w", "weather", "surface_pressure", "p, hPa", "Атмосферное давление у земли"),
        ("-2w", "weather", "relative_humidity_2m", "hum, %", "Относительная влажность на 2м"),
        ("-2w", "pollution", "components_pm2_5", "pm25", "Загрязнение частицами pm2,5"),
    ]

    for stepback, measurement, field, ylabel, title in metrics:
        res = generate_retro_beautiful_graph(query_api, config, stepback, measurement, field, ylabel, title)
        print(res)
    
    print(upload_to_neocities(config['INDEX_HTML'], config['NEOCITIES_URL'], config['NEOCITIES_TOKEN'], config['WEBHOST_URL']))

if __name__ == "__main__":
    config = get_config()
    print(f"LOOP: {config['DO_LOOP']}\n")
    
    client = InfluxDBClient(url=config['INFLUX_URL'], token=config['INFLUX_TOKEN'], org=config['INFLUX_ORG'])
    query_api = client.query_api()

    try:
        while True:
            run_once(query_api, config)
            if not config['DO_LOOP']:
                break
            time.sleep(config['WAIT_SECONDS'])
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        client.close()

