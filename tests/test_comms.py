import sys
import os

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from lib.comms import get_data, post_data, patch_data, read_json_from_file, send_udp_data, send_bitmask_data_to_stm32, receive_bitmask_data_from_stm32


import pytest
import json
import socket
import requests
from unittest.mock import patch, MagicMock


# Mock the requests library to avoid actual HTTP calls
@pytest.fixture
def mock_requests():
    with patch("requests.get") as mock_get, \
            patch("requests.post") as mock_post, \
            patch("requests.patch") as mock_patch:
        yield mock_get, mock_post, mock_patch


# Test GET request
def test_get_data(mock_requests):
    mock_get, _, _ = mock_requests
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"thrusters": {"U_FWD_P": {"power": 75, "temp": 15}}}

    get_data()
    mock_get.assert_called_once()


# Test POST request
def test_post_data(mock_requests):
    _, mock_post, _ = mock_requests
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"success": True}

    post_json_string = '{"thrusters": {"U_FWD_P": {"power": 75, "temp": 15}}}'
    post_data(post_json_string)

    mock_post.assert_called_once_with("http://127.0.0.1:5000/post-data", json=json.loads(post_json_string))


# Test PATCH request
def test_patch_data(mock_requests):
    _, _, mock_patch = mock_requests
    mock_patch.return_value.status_code = 200
    mock_patch.return_value.json.return_value = {"success": True}

    patch_json_string = '{"thrusters": {"U_FWD_P": {"power": 100, "temp": 10}}}'
    patch_data(patch_json_string)

    mock_patch.assert_called_once_with("http://127.0.0.1:5000/patch-data", json=json.loads(patch_json_string))


# Test reading JSON file
def test_read_json_from_file(mocker):
    mock_data = {"Thrust": [100, 9.2, -42.0, 22.0, 0.0, 0.0], "Buttons": {"button_surface": 1}}

    mocker.patch("builtins.open", mocker.mock_open(read_data=json.dumps(mock_data)))
    result = read_json_from_file()

    assert result == mock_data


# Test UDP communication
def test_send_udp_data(mocker):
    mock_socket = mocker.patch("socket.socket")
    mock_udp_socket = mock_socket.return_value

    mock_data = {"Thrust": [100, 9.2, -42.0, 22.0, 0.0, 0.0], "Buttons": {"button_surface": 1}}

    mocker.patch("lib.comms.read_json_from_file", return_value=mock_data)

    send_udp_data()

    mock_udp_socket.sendto.assert_called()


# Test STM32 bitmask communication
def test_send_bitmask_data_to_stm32(mocker):
    """Test sending bitmask data to STM32."""
    mock_socket = mocker.patch("socket.socket")
    mock_udp_socket = mock_socket.return_value
    
    # Mock the bitmask converter
    mock_convert = mocker.patch("lib.comms.convert_json_to_binary")
    mock_convert.return_value = b'\x01\x02\x03\x04'
    
    test_data = {"battery": 100, "Thrust": [1, 2, 3, 4, 5, 6]}
    
    result = send_bitmask_data_to_stm32(test_data)
    
    assert result is True
    mock_convert.assert_called_once_with(test_data)
    mock_udp_socket.sendto.assert_called_once()
    mock_udp_socket.close.assert_called_once()


def test_send_bitmask_data_to_stm32_no_data(mocker):
    """Test sending bitmask data to STM32 without providing data (reads from file)."""
    mock_socket = mocker.patch("socket.socket")
    mock_udp_socket = mock_socket.return_value
    
    # Mock the data handler
    mock_data_handler = mocker.patch("lib.comms.JSONDataHandler")
    mock_handler_instance = mock_data_handler.return_value
    mock_handler_instance.read_data.return_value = {"battery": 90}
    
    # Mock the bitmask converter
    mock_convert = mocker.patch("lib.comms.convert_json_to_binary")
    mock_convert.return_value = b'\x01\x02\x03\x04'
    
    result = send_bitmask_data_to_stm32()
    
    assert result is True
    mock_handler_instance.read_data.assert_called_once()
    mock_convert.assert_called_once_with({"battery": 90})


def test_receive_bitmask_data_from_stm32(mocker):
    """Test receiving bitmask data from STM32."""
    mock_socket = mocker.patch("socket.socket")
    mock_udp_socket = mock_socket.return_value
    mock_udp_socket.recvfrom.return_value = (b'\x01\x02\x03\x04', ('127.0.0.1', 5002))
    
    # Mock the bitmask converter
    mock_convert = mocker.patch("lib.comms.convert_binary_to_json")
    mock_convert.return_value = {"battery": 85}
    
    result = receive_bitmask_data_from_stm32()
    
    assert result == {"battery": 85}
    mock_convert.assert_called_once_with(b'\x01\x02\x03\x04')
    mock_udp_socket.close.assert_called_once()


def test_receive_bitmask_data_timeout(mocker):
    """Test receiving bitmask data with timeout."""
    mock_socket = mocker.patch("socket.socket")
    mock_udp_socket = mock_socket.return_value
    mock_udp_socket.recvfrom.side_effect = socket.timeout()
    
    result = receive_bitmask_data_from_stm32()
    
    assert result is None
