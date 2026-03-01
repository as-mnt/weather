import pytest
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime
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
        url = weather.upload_to_neocities("test.png", mock_config['NEOCITIES_URL'], 
                                         mock_config['NEOCITIES_TOKEN'], mock_config['WEBHOST_URL'])
    
    assert url == "https://example.com/test.png"
    mock_post.assert_called_once()

@patch('requests.post')
def test_upload_to_neocities_failure(mock_post, mock_config):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    mock_post.return_value = mock_response

    with patch('builtins.open', mock_open(read_data=b"data")):
        url = weather.upload_to_neocities("test.png", mock_config['NEOCITIES_URL'], 
                                         mock_config['NEOCITIES_TOKEN'], mock_config['WEBHOST_URL'])
    
    assert url is None

def test_generate_retro_beautiful_graph_calls_base(mock_config):
    mock_query_api = MagicMock()
    
    # We patch the base function to see if it's called with correct filename
    with patch('mkweathergraphs_loop.generate_beautiful_graph') as mock_gen:
        weather.generate_retro_beautiful_graph(mock_query_api, mock_config, "-2d", "m", "f", "y", "t")
        
        mock_gen.assert_called_once()
        args, kwargs = mock_gen.call_args
        assert args[2] == "start: -2d"  # range_spec
        # The filename is the 8th positional argument (index 7) or passed via kwargs
        assert args[7] == "graphs/m-f--2d.png"

@patch('mkweathergraphs_loop.plt')
@patch('mkweathergraphs_loop.upload_to_neocities')
def test_generate_beautiful_graph_no_data(mock_upload, mock_plt, mock_config):
    mock_query_api = MagicMock()
    mock_query_api.query.return_value = [] # No tables returned
    
    res = weather.generate_beautiful_graph(mock_query_api, mock_config, "start: -1h", "m", "f", "y", "t")
    
    assert res is None
    mock_plt.subplots.assert_not_called()

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
    
    res = weather.generate_beautiful_graph(mock_query_api, mock_config, "start: -1h", "weather", "temp", "C", "Title")
    
    # Verify visualization steps
    mock_plt.subplots.assert_called_once()
    mock_ax.plot.assert_called_once()
    mock_ax.set_title.assert_called_with("Title", fontsize=4)
    mock_ax.set_ylabel.assert_called_with("C", fontsize=4)
    
    # Verify save and close
    mock_plt.savefig.assert_called_once()
    mock_plt.close.assert_called_with(mock_fig)
    
    assert res["status"] == "success"
    assert res["image_url"] == "https://example.com/ok.png"

@patch('mkweathergraphs_loop.plt')
@patch('mkweathergraphs_loop.upload_to_neocities')
def test_generate_beautiful_graph_upload_fails(mock_upload, mock_plt, mock_config):
    mock_record = MagicMock()
    mock_record.get_time.return_value = datetime(2023, 1, 1, 10, 0)
    mock_record.get_value.return_value = 10.0
    mock_table = MagicMock()
    mock_table.records = [mock_record]
    mock_query_api = MagicMock()
    mock_query_api.query.return_value = [mock_table]
    
    mock_plt.subplots.return_value = (MagicMock(), MagicMock())
    mock_upload.return_value = None # Upload failed
    
    res = weather.generate_beautiful_graph(mock_query_api, mock_config, "start: -1h", "m", "f", "y", "t")
    
    assert res["status"] == "error"
    assert "Failed to upload" in res["message"]
