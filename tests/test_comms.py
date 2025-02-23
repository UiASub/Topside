import sys
import os

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from lib.comms import get_data, post_data, patch_data, read_json_from_file, send_udp_data


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
