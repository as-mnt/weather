import os
import requests
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
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

def upload_to_neocities(local_filename, remote_filename, api_url, api_token, webhost_url):
    try:
        with open(local_filename, "rb") as f:
            files = {remote_filename: f}
            headers = {"Authorization": f"Bearer {api_token}"}
            response = requests.post(api_url, files=files, headers=headers)
        
        fileurl = f"{webhost_url}/{remote_filename}"
        if response.status_code == 200:
            print(f"File uploaded: {fileurl}")
            return fileurl
        else:
            print(f"Error uploading {remote_filename}: {response.text}")
            return None
    except Exception as e:
        print(f"Upload failed for {remote_filename}: {e}")
        return None

def generate_beautiful_graph(query_api, config, location, tz_offset, range_spec, measurement, field, ylabel, title, filename):
    # Handle legacy data for Bishkek (where location tag might be missing)
    if location == "Bishkek":
        location_filter = f'r.location == "{location}" or not exists r.location'
    else:
        location_filter = f'r.location == "{location}"'

    query = f'from(bucket: "{config["INFLUX_BUCKET"]}") |> range({range_spec}) \
                                              |> filter(fn: (r) => r._measurement == "{measurement}") \
                                              |> filter(fn: (r) => r._field == "{field}") \
                                              |> filter(fn: (r) => {location_filter}) \
                                              |> aggregateWindow(every: 5m, fn: mean, createEmpty: false) \
                                              |> yield(name: "mean")'
    
    tables = query_api.query(query)
    times, values = [], []
    for table in tables:
        for record in table.records:
            times.append(record.get_time() + timedelta(hours=tz_offset))
            values.append(record.get_value())

    if not times:
        print(f"No data for {location} {measurement}:{field}")
        return None

    sns.set_style('darkgrid')
    plt.style.use("seaborn-v0_8-darkgrid")
    fig, ax = plt.subplots(figsize=(3, 1))

    values_smooth = gaussian_filter1d(values, sigma=2)

    ax.plot(times, values_smooth, linestyle="-", 
            color="#FF5733", linewidth=0.5, alpha=0.9)

    ax.set_xlabel("время", fontsize=4)
    ax.set_ylabel(ylabel, fontsize=4)
    ax.set_title(f"{location}: {title}", fontsize=4)
    plt.xticks(rotation=30, fontsize=4)
    plt.yticks(fontsize=4)

    # Disable scientific notation on Y axis
    ax.yaxis.set_major_formatter(ticker.ScalarFormatter(useOffset=False))
    ax.yaxis.get_major_formatter().set_scientific(False)

    ax.grid(which='major', color='darkgray', linestyle='-', linewidth=0.2)
    ax.minorticks_on()
    ax.grid(which='minor', color='lightgray', linestyle=':', linewidth=0.2)

    if config['DEBUG']: print(f"{current_timestamp()} Saving to {filename}")
    plt.savefig(filename, dpi=200, bbox_inches="tight")
    plt.close(fig)
    
    # Upload to Neocities (relative to root)
    url = upload_to_neocities(filename, filename, config['NEOCITIES_URL'], config['NEOCITIES_TOKEN'], config['WEBHOST_URL'])
    
    if url:
        return {"status": "success", "image_url": url, "location": location}
    else:
        return {"status": "error", "message": "Failed to upload", "location": location}

def current_timestamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def generate_city_html(location_name):
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Графики - {location_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; text-align: center; background-color: #f0f2f5; }}
        img {{ max-width: 80%; height: auto; margin: 20px; border: 1px solid #ddd; border-radius: 4px; }}
        .nav {{ margin-bottom: 20px; }}
    </style>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
    <meta http-equiv="Pragma" content="no-cache" />
    <meta http-equiv="Expires" content="0" />
</head>
<body>
    <div class="nav"><a href="/">На главную</a></div>
    <h1>Графики ({location_name})</h1>
    <img src="/graphs/{location_name.lower()}-weather-temperature_2m--2d.png?cache=none">
    <img src="/graphs/{location_name.lower()}-weather-temperature_2m--2w.png?cache=none">
    <img src="/graphs/{location_name.lower()}-weather-surface_pressure--2d.png?cache=none">
    <img src="/graphs/{location_name.lower()}-weather-surface_pressure--2w.png?cache=none">
    <img src="/graphs/{location_name.lower()}-weather-relative_humidity_2m--2d.png?cache=none">
    <img src="/graphs/{location_name.lower()}-weather-relative_humidity_2m--2w.png?cache=none">
    <img src="/graphs/{location_name.lower()}-pollution-components_pm2_5--2d.png?cache=none">
    <img src="/graphs/{location_name.lower()}-pollution-components_pm2_5--2w.png?cache=none">
</body>
</html>"""
    return html

def run_once(query_api, config):
    ct = current_timestamp()
    print(f"{ct} fetching and looping\n")
    
    locations = [
        {"name": "Bishkek", "offset": 6, "is_default": True},
        {"name": "Kazan", "offset": 3, "is_default": False},
        {"name": "Vladivostok", "offset": 10, "is_default": False},
    ]

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

    for loc in locations:
        for stepback, measurement, field, ylabel, title in metrics:
            filename_city = f"{config['GRAPHS_PATH']}/{loc['name'].lower()}-{measurement}-{field}-{stepback}.png"
            generate_beautiful_graph(query_api, config, loc["name"], loc["offset"], f"start: {stepback}", measurement, field, ylabel, title, filename_city)
            
            if loc.get("is_default"):
                filename_legacy = f"{config['GRAPHS_PATH']}/{measurement}-{field}-{stepback}.png"
                generate_beautiful_graph(query_api, config, loc["name"], loc["offset"], f"start: {stepback}", measurement, field, ylabel, title, filename_legacy)
        
        # Generate and upload city-specific index.html
        city_html_content = generate_city_html(loc["name"])
        local_city_html = f"{loc['name']}.html"
        remote_city_html = f"{loc['name']}/index.html"
        with open(local_city_html, "w") as f:
            f.write(city_html_content)
        upload_to_neocities(local_city_html, remote_city_html, config['NEOCITIES_URL'], config['NEOCITIES_TOKEN'], config['WEBHOST_URL'])

    # Upload main index.html
    upload_to_neocities(config['INDEX_HTML'], config['INDEX_HTML'], config['NEOCITIES_URL'], config['NEOCITIES_TOKEN'], config['WEBHOST_URL'])

if __name__ == "__main__":
    config = get_config()
    if not os.path.exists(config['GRAPHS_PATH']):
        os.makedirs(config['GRAPHS_PATH'])
        
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
