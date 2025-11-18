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


INFLUX_URL = os.getenv('INFLUX_URL')
INFLUX_TOKEN = os.getenv('INFLUX_TOKEN')
INFLUX_ORG = os.getenv('INFLUX_ORG')
INFLUX_BUCKET = os.getenv('INFLUX_BUCKET')
NEOCITIES_TOKEN = os.getenv('NEOCITIES_TOKEN')
NEOCITIES_URL = os.getenv('NEOCITIES_URL')
WAIT_SECONDS = int(os.getenv('WAIT_SECONDS'))
WEBHOST_URL = os.getenv('WEBHOST_URL')
DO_LOOP = os.getenv('LOOP') or 'true'
DEBUG = os.getenv('DEBUG') or 'false'
GRAPHS_PATH = 'graphs'

print(f"LOOP: {DO_LOOP}\n")

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
query_api = client.query_api()

def upload_to_neocities(filename, api_url, api_token, webhost_url):
    files = {f"{filename}": open(f"{filename}", "rb")}
    headers = {"Authorization": f"Bearer {api_token}"}
    response = requests.post(api_url, files=files, headers=headers)
    fileurl = f"{webhost_url}/{filename}"
    if response.status_code == 200:
        print(f"Graph uploaded: {fileurl}")
        return fileurl
    else:
        print(f"Error: {response.text}")
        return Nil

def generate_beautiful_graph(range_spec, measurement, field, ylabel, title, filename = None):
    query = f'from(bucket: "{INFLUX_BUCKET}") |> range({range_spec}) \
                                              |> filter(fn: (r) => r._measurement == "{measurement}") \
                                              |> filter(fn: (r) => r._field == "{field}") \
                                              |> aggregateWindow(every: 5m, fn: mean, createEmpty: false) \
                                              |> yield(name: "mean")'
    tables = query_api.query(query)
    if DEBUG == 'true': print(tables.to_json())
    times, values = [], []
    for table in tables:
        for record in table.records:
            times.append(record.get_time() + timedelta(hours=6))
            values.append(record.get_value())

    sns.set_style('darkgrid')
    plt.style.use("seaborn-v0_8-darkgrid")  # Красивый стиль
    fig, ax = plt.subplots(figsize=(3, 1))  # Размер графика

    values_smooth = gaussian_filter1d(values, sigma=2)

    # Строим линию
    ax.plot(times, values_smooth, linestyle="-", 
            color="#FF5733", linewidth=0.5, markerfacecolor="white",
#            color="#FF5733", linewidth=1, markerfacecolor="white",
            markeredgewidth=2, markeredgecolor="#FF5733", alpha=0.9)

    # Настройки осей
    ax.set_xlabel("время", fontsize=4)
    ax.set_ylabel(ylabel, fontsize=4)
    ax.set_title(title, fontsize=4)

    # Улучшенные подписи оси X
#    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))  # Метки по дням
#    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))  # Формат даты
    plt.xticks(rotation=30, fontsize=4)

    # Улучшенные подписи оси Y
    plt.yticks(fontsize=4)

    # Добавляем сетку

    ax.grid(which='major', color='darkgray', linestyle='-', linewidth=0.2)
    ax.minorticks_on()
    ax.grid(which='minor', color='lightgray', linestyle=':', linewidth=0.2)

    # Сохраняем картинку
    if not filename:
        filename = f"{GRAPHS_PATH}/{measurement}-{field}.png"
    plt.savefig(filename, dpi=200, bbox_inches="tight")  # Высокое качество

    # Заливаем на neocities

    url = upload_to_neocities(f"{filename}", NEOCITIES_URL, NEOCITIES_TOKEN, WEBHOST_URL)
    if url:
        return {"status": "success", "image_url": url}
    else:
        return {"status": "error", "message": "Failed to upload"}, 500

def generate_retro_beautiful_graph(stepback, measurement, field, ylabel, title):
    return generate_beautiful_graph(f"start: {stepback}", measurement, field, ylabel, title, f"{GRAPHS_PATH}/{measurement}-{field}-{stepback}.png")

def current_timestamp():
    return datetime.now().strftime("%Y%m%d-%H%M%s")

def loop(wait_seconds):
    ct = current_timestamp()
    print(f"{ct} Started\n")
    while True:
        ct = current_timestamp()
        print(f"{ct} fetching and looping\n")
        print(generate_retro_beautiful_graph("-2d", "weather", "temperature_2m", "t, C", "Температура воздуха на 2м"))
        print(generate_retro_beautiful_graph("-2d", "weather", "surface_pressure", "p, hPa", "Атмосферное давление у земли"))
        print(generate_retro_beautiful_graph("-2d", "weather", "relative_humidity_2m", "hum, %", "Относительная влажность на 2м"))
        print(generate_retro_beautiful_graph("-2w", "weather", "temperature_2m", "t, C", "Температура воздуха на 2м"))
        print(generate_retro_beautiful_graph("-2w", "weather", "surface_pressure", "p, hPa", "Атмосферное давление у земли"))
        print(generate_retro_beautiful_graph("-2w", "weather", "relative_humidity_2m", "hum, %", "Относительная влажность на 2м"))
        if DO_LOOP == 'false':
            print("LOOP false, exiting\n")
            exit(0)
        time.sleep(wait_seconds)

loop(WAIT_SECONDS)
#loop(60*60)

exit(0)
