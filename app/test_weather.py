import pytest
import threading
from unittest.mock import MagicMock, patch, mock_open, call
from datetime import datetime, timedelta
import mkweathergraphs_loop as weather

@pytest.fixture
def mock_config():
    return {
        'INFLUX_BUCKET': 'test-bucket',
        'NEOCITIES_URL': 'https://example.com/api',
        'NEOCITIES_TOKEN': 'test-token',
        'WEBHOST_URL': 'https://example.com',
        'DEBUG': False,
        'GRAPHS_PATH': 'graphs',
        'INDEX_HTML': 'index.html'
    }

def test_current_timestamp():
    ts = weather.current_timestamp()
    assert len(ts) == 15  # YYYYMMDD-HHMMSS
    assert ts[8] == '-'

@patch('requests.post')
def test_upload_to_neocities_success(mock_post, mock_config):
    # Setup mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    # We need to mock open() because the function opens the file
    with patch('builtins.open', mock_open(read_data=b"data")):
        url = weather.upload_to_neocities("local.png", "remote.png", mock_config['NEOCITIES_URL'], 
                                         mock_config['NEOCITIES_TOKEN'], mock_config['WEBHOST_URL'])
    
    assert url == "https://example.com/remote.png"
    mock_post.assert_called_once()

@patch('requests.post')
def test_upload_to_neocities_failure(mock_post, mock_config):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    mock_post.return_value = mock_response

    with patch('builtins.open', mock_open(read_data=b"data")):
        url = weather.upload_to_neocities("local.png", "remote.png", mock_config['NEOCITIES_URL'], 
                                         mock_config['NEOCITIES_TOKEN'], mock_config['WEBHOST_URL'])
    
    assert url is None

@patch('mkweathergraphs_loop.plt')
@patch('mkweathergraphs_loop.upload_to_neocities')
def test_generate_beautiful_graph_no_data(mock_upload, mock_plt, mock_config):
    mock_query_api = MagicMock()
    mock_query_api.query.return_value = [] # No tables returned
    
    res = weather.generate_beautiful_graph(mock_query_api, mock_config, "Bishkek", 6, "start: -1h", "m", "f", "y", "t", "out.png")
    
    assert res is None
    mock_plt.subplots.assert_not_called()

def test_with_retry_success():
    fn = MagicMock(return_value="ok")
    assert weather._with_retry(fn) == "ok"
    fn.assert_called_once()


def test_with_retry_succeeds_after_failure():
    fn = MagicMock(side_effect=[Exception("fail"), "ok"])
    with patch('time.sleep'):
        result = weather._with_retry(fn, retries=3, backoff=1)
    assert result == "ok"
    assert fn.call_count == 2


def test_with_retry_exhausted():
    fn = MagicMock(side_effect=Exception("fail"))
    with patch('time.sleep'):
        result = weather._with_retry(fn, retries=3, backoff=1)
    assert result is None
    assert fn.call_count == 3


def test_with_retry_no_retry_exception():
    fn = MagicMock(side_effect=weather._NoRetry("fatal"))
    result = weather._with_retry(fn)
    assert result is None
    fn.assert_called_once()


@patch('requests.post')
def test_upload_retries_on_server_error(mock_post, mock_config):
    mock_500 = MagicMock()
    mock_500.status_code = 500
    mock_500.text = "Internal Server Error"
    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_post.side_effect = [mock_500, mock_200]

    with patch('builtins.open', mock_open(read_data=b"data")), patch('time.sleep'):
        url = weather.upload_to_neocities("local.png", "remote.png",
                                          mock_config['NEOCITIES_URL'],
                                          mock_config['NEOCITIES_TOKEN'],
                                          mock_config['WEBHOST_URL'])

    assert url == "https://example.com/remote.png"
    assert mock_post.call_count == 2


@patch('mkweathergraphs_loop.plt')
@patch('mkweathergraphs_loop.upload_to_neocities')
def test_generate_beautiful_graph_retries_on_influx_error(mock_upload, mock_plt, mock_config):
    mock_record = MagicMock()
    mock_record.get_time.return_value = datetime(2023, 1, 1, 10, 0)
    mock_record.get_value.return_value = 20.5

    mock_table = MagicMock()
    mock_table.records = [mock_record]

    mock_query_api = MagicMock()
    mock_query_api.query.side_effect = [Exception("Connection refused"), [mock_table]]

    mock_fig = MagicMock()
    mock_ax = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)
    mock_upload.return_value = "https://example.com/ok.png"

    with patch('time.sleep'):
        res = weather.generate_beautiful_graph(
            mock_query_api, mock_config, "Kazan", 3, "start: -1h",
            "weather", "temp", "C", "Title", "kazan.png"
        )

    assert mock_query_api.query.call_count == 2
    assert res["status"] == "success"


@patch('mkweathergraphs_loop.plt')
@patch('mkweathergraphs_loop.upload_to_neocities')
def test_generate_beautiful_graph_with_data(mock_upload, mock_plt, mock_config):
    # Setup mock data from InfluxDB
    mock_record1 = MagicMock()
    mock_record1.get_time.return_value = datetime(2023, 1, 1, 10, 0)
    mock_record1.get_value.return_value = 20.5
    
    mock_record2 = MagicMock()
    mock_record2.get_time.return_value = datetime(2023, 1, 1, 11, 0)
    mock_record2.get_value.return_value = 22.0
    
    mock_table = MagicMock()
    mock_table.records = [mock_record1, mock_record2]
    
    mock_query_api = MagicMock()
    mock_query_api.query.return_value = [mock_table]
    
    # Mock plt.subplots to return mock fig and ax
    mock_fig = MagicMock()
    mock_ax = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)
    
    mock_upload.return_value = "https://example.com/ok.png"
    
    res = weather.generate_beautiful_graph(mock_query_api, mock_config, "Kazan", 3, "start: -1h", "weather", "temp", "C", "Title", "kazan.png")
    
    # Verify visualization steps
    mock_plt.subplots.assert_called_once()
    mock_ax.plot.assert_called_once()
    mock_ax.set_title.assert_called_with("Kazan: Title", fontsize=4)
    mock_ax.set_ylabel.assert_called_with("C", fontsize=4)
    
    # Verify save and close
    mock_plt.savefig.assert_called_once_with("kazan.png", dpi=200, bbox_inches="tight")
    mock_plt.close.assert_called_with(mock_fig)
    
    assert res["status"] == "success"
    assert res["image_url"] == "https://example.com/ok.png"
    assert res["location"] == "Kazan"


def test_generate_city_html_contains_location():
    html = weather.generate_city_html("Kazan")
    assert "<title>Графики - Kazan</title>" in html
    assert "<h1>Графики (Kazan)</h1>" in html


def test_generate_city_html_img_paths_are_lowercased():
    html = weather.generate_city_html("Vladivostok")
    for metric in ["weather-temperature_2m--2d", "weather-surface_pressure--2w",
                   "weather-relative_humidity_2m--2d", "pollution-components_pm2_5--2w"]:
        assert f"vladivostok-{metric}.png" in html


@patch('mkweathergraphs_loop.upload_to_neocities')
@patch('mkweathergraphs_loop.generate_beautiful_graph')
def test_run_once_graph_call_count(mock_graph, mock_upload, mock_config):
    """3 города × 8 метрик = 24, плюс 8 legacy-файлов для Bishkek (is_default=True) = 32."""
    with patch('builtins.open', mock_open()):
        weather.run_once(MagicMock(), mock_config)
    assert mock_graph.call_count == 32


@patch('mkweathergraphs_loop.upload_to_neocities')
@patch('mkweathergraphs_loop.generate_beautiful_graph')
def test_run_once_upload_call_count(mock_graph, mock_upload, mock_config):
    """3 city HTML + 1 index.html = 4 вызова upload_to_neocities."""
    with patch('builtins.open', mock_open()):
        weather.run_once(MagicMock(), mock_config)
    assert mock_upload.call_count == 4


@patch('mkweathergraphs_loop.upload_to_neocities')
@patch('mkweathergraphs_loop.generate_beautiful_graph')
def test_run_once_legacy_files_only_for_bishkek(mock_graph, mock_upload, mock_config):
    """Legacy-файлы (без префикса города) генерируются только для Bishkek."""
    with patch('builtins.open', mock_open()):
        weather.run_once(MagicMock(), mock_config)
    filenames = [c.args[9] for c in mock_graph.call_args_list]
    legacy = [f for f in filenames if not any(
        f.startswith(f"graphs/{city}") for city in ["bishkek", "kazan", "vladivostok"]
    )]
    assert len(legacy) == 8


@pytest.fixture
def loop_config(mock_config):
    return {**mock_config, 'DO_LOOP': False, 'WAIT_SECONDS': 3600}


def test_run_loop_single_cycle(loop_config):
    """DO_LOOP=False: run_once is called exactly once."""
    with patch('mkweathergraphs_loop.run_once') as mock_run_once:
        weather.run_loop(MagicMock(), loop_config, threading.Event())
    mock_run_once.assert_called_once()


def test_run_loop_skips_if_shutdown_set(loop_config):
    """If shutdown_event is set before the loop, run_once is never called."""
    shutdown = threading.Event()
    shutdown.set()
    with patch('mkweathergraphs_loop.run_once') as mock_run_once:
        weather.run_loop(MagicMock(), {**loop_config, 'DO_LOOP': True}, shutdown)
    mock_run_once.assert_not_called()


def test_run_loop_exits_after_cycle_on_shutdown(loop_config):
    """Shutdown requested during run_once: loop exits after that cycle completes."""
    shutdown = threading.Event()
    call_count = 0

    def _run_once_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        shutdown.set()

    with patch('mkweathergraphs_loop.run_once', side_effect=_run_once_side_effect):
        weather.run_loop(MagicMock(), {**loop_config, 'DO_LOOP': True, 'WAIT_SECONDS': 0}, shutdown)

    assert call_count == 1
