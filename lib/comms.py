import requests
import json
from lib import eventlogger
from lib.bitmask_converter import convert_json_to_binary, convert_binary_to_json
import time
import socket
import threading

url = "127.0.0.1:5000"  # Raspberry Pi IP and port for HTTP server
urlGet = f"http://{url}/data"  # URL for retrieving data
urlPost = f"http://{url}/post-data"  # URL for sending data
urlPatch = f"http://{url}/patch-data"  # URL for patching data

UPDATE_RATE = 1000  # Hz (example: 20 Hz = every 50 ms)
TIME_INTERVAL = 1.0 / UPDATE_RATE  # Time interval per send cycle

# UDP configurations
UDP_IP = "127.0.0.1"  # Replace with the receiver's IP
UDP_PORT = 5001  # Receiver port
CONTROLS_JSON_PATH = "data/controls.json"  # Path to controls JSON file

# Bitmask/Binary communication configurations for STM32
STM32_UDP_IP = "127.0.0.1"  # Replace with STM32 IP
STM32_UDP_PORT = 5002  # STM32 communication port

def get_data():
    try:
        response = requests.get(urlGet)

        if response.status_code == 200:
            try:
                data = response.json()
                eventlogger.logger.log_info("HTTP get_data success")
                print(data)
            except json.JSONDecodeError:
                eventlogger.logger.log_error("HTTP get_data failed: Response is not valid JSON")
                print("Error: Response is not valid JSON")
        else:
            status = f"HTTP get_data failed with status: {response.status_code}"
            eventlogger.logger.log_error(status)
            print(status, response.text)

    except requests.exceptions.ConnectionError:
        error = "HTTP get_data Unable to connect to the server."
        eventlogger.logger.log_error(error)
        print(error)

    except requests.exceptions.Timeout:
        error = "HTTP get_data The request timed out."
        eventlogger.logger.log_error(error)
        print(error)

    except requests.exceptions.RequestException as e:
        error = f"Error: {e}"
        eventlogger.logger.log_error(error)
        print(error)


def post_data(json_string):
    """
    Sends a JSON string as a POST request.

    :param json_string: JSON string to send in the POST request.
    """
    try:
        data = json.loads(json_string)

        response = requests.post(urlPost, json=data)

        if response.status_code == 200:
            try:
                response_data = response.json()
                eventlogger.logger.log_info("HTTP post_data success")
                print("POST Success:", response_data)
            except json.JSONDecodeError:
                eventlogger.logger.log_error("HTTP post_data failed: Response is not valid JSON")
                print("Error: Response is not valid JSON")
        else:
            status = f"HTTP post_data failed with status: {response.status_code}"
            eventlogger.logger.log_error(status)
            print(status, response.text)

    except json.JSONDecodeError:
        error = "HTTP post_data Error: Provided string is not valid JSON."
        eventlogger.logger.log_error(error)
        print(error)

    except requests.exceptions.ConnectionError:
        error = "HTTP post_data Unable to connect to the server."
        eventlogger.logger.log_error(error)
        print(error)

    except requests.exceptions.Timeout:
        error = "HTTP post_data The request timed out."
        eventlogger.logger.log_error(error)
        print(error)

    except requests.exceptions.RequestException as e:
        error = f"Error: {e}"
        eventlogger.logger.log_error(error)
        print(error)


def patch_data(json_string):
    """
    Sends a JSON string as a PATCH request.

    :param json_string: JSON string to send in the PATCH request.
    """
    try:
        patch_data = json.loads(json_string)

        response = requests.patch(urlPatch, json=patch_data)

        if response.status_code == 200:
            try:
                response_data = response.json()
                eventlogger.logger.log_info("HTTP patch_data success")
                print("PATCH Success:", response_data)
            except json.JSONDecodeError:
                eventlogger.logger.log_error("HTTP patch_data failed: Response is not valid JSON")
                print("Error: Response is not valid JSON")
        else:
            status = f"HTTP patch_data failed with status: {response.status_code}"
            eventlogger.logger.log_error(status)
            print(status, response.text)

    except json.JSONDecodeError:
        error = "HTTP patch_data Error: Provided string is not valid JSON."
        eventlogger.logger.log_error(error)
        print(error)

    except requests.exceptions.ConnectionError:
        error = "HTTP patch_data Unable to connect to the server."
        eventlogger.logger.log_error(error)
        print(error)

    except requests.exceptions.Timeout:
        error = "HTTP patch_data The request timed out."
        eventlogger.logger.log_error(error)
        print(error)

    except requests.exceptions.RequestException as e:
        error = f"Error: {e}"
        eventlogger.logger.log_error(error)
        print(error)


def read_json_from_file():
    """
    Reads JSON data from 'data/controls.json'. Returns an empty structure if the file is missing or invalid.
    """
    try:
        with open(CONTROLS_JSON_PATH, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        eventlogger.logger.log_error(f"Failed to read JSON: {e}")
        print(f"Failed to read JSON: {e}")
        return {"Thrust": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "Buttons": {"button_surface": 0}}


def send_udp_data():
    """
    Sends a JSON string via UDP at 1000 Hz.
    Reads JSON from 'data/controls.json' before sending.
    Logs only every 10 seconds to avoid excessive logging.
    """
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # Create UDP socket
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)  # Small buffer since JSON is small

        eventlogger.logger.log_info(f"UDP socket created. Sending to {UDP_IP}:{UDP_PORT}")
        print(f"UDP socket created. Sending to {UDP_IP}:{UDP_PORT}")

        last_log_time = time.perf_counter()  # Last log timestamp
        next_cycle_time = time.perf_counter()  # Track the cycle start time

        while True:
            json_data = read_json_from_file()  # Read latest JSON
            json_string = json.dumps(json_data, separators=(",", ":"), ensure_ascii=False)  # Compact JSON

            udp_socket.sendto(json_string.encode(), (UDP_IP, UDP_PORT))  # Send JSON data

            # Log only every 10 seconds
            if time.perf_counter() - last_log_time >= 10:
                eventlogger.logger.log_info("UDP server is still running")
                print("UDP server is still running")
                last_log_time = time.perf_counter()

            # Ensure precise 1000 Hz refresh rate
            next_cycle_time += TIME_INTERVAL  # Increment next cycle time
            sleep_duration = next_cycle_time - time.perf_counter()  # Calculate time to wait
            if sleep_duration > 0:
                time.sleep(sleep_duration)  # Sleep only if needed to maintain timing

    except Exception as e:
        eventlogger.logger.log_error(f"UDP socket error: {e}")
        print(f"UDP socket error: {e}")

    finally:
        udp_socket.close()


def send_bitmask_data_to_stm32(json_data=None):
    """
    Sends data to STM32 microcontroller using bitmask/binary format.
    Reads JSON from 'data/data.json' if no data provided, converts to binary,
    and sends via UDP to STM32.
    
    Args:
        json_data: Optional JSON data to send. If None, reads from data.json
    """
    try:
        if json_data is None:
            # Read from data.json if no data provided
            from lib.json_data_handler import JSONDataHandler
            data_handler = JSONDataHandler()
            json_data = data_handler.read_data()
        
        # Convert JSON to binary format for STM32
        binary_data = convert_json_to_binary(json_data)
        
        # Create UDP socket and send binary data
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.sendto(binary_data, (STM32_UDP_IP, STM32_UDP_PORT))
        udp_socket.close()
        
        eventlogger.logger.log_info(f"Sent {len(binary_data)} bytes of binary data to STM32")
        return True
        
    except Exception as e:
        eventlogger.logger.log_error(f"Failed to send bitmask data to STM32: {e}")
        print(f"Failed to send bitmask data to STM32: {e}")
        return False


def receive_bitmask_data_from_stm32(timeout=1.0):
    """
    Receives binary data from STM32 and converts it back to JSON format.
    
    Args:
        timeout: Socket timeout in seconds
        
    Returns:
        dict: JSON data received from STM32, or None if failed
    """
    try:
        # Create UDP socket for receiving
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(timeout)
        udp_socket.bind(('', STM32_UDP_PORT + 1))  # Use different port for receiving
        
        # Receive binary data
        binary_data, addr = udp_socket.recvfrom(1024)  # Adjust buffer size as needed
        udp_socket.close()
        
        # Convert binary data back to JSON
        json_data = convert_binary_to_json(binary_data)
        
        eventlogger.logger.log_info(f"Received {len(binary_data)} bytes of binary data from STM32")
        return json_data
        
    except socket.timeout:
        eventlogger.logger.log_warning("Timeout receiving data from STM32")
        return None
    except Exception as e:
        eventlogger.logger.log_error(f"Failed to receive bitmask data from STM32: {e}")
        print(f"Failed to receive bitmask data from STM32: {e}")
        return None


def send_bitmask_data_continuous():
    """
    Continuously sends bitmask data to STM32 at regular intervals.
    Reads from data.json and sends binary data every 100ms (10 Hz).
    """
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
        
        eventlogger.logger.log_info(f"Starting continuous bitmask transmission to STM32 at {STM32_UDP_IP}:{STM32_UDP_PORT}")
        print(f"Starting continuous bitmask transmission to STM32 at {STM32_UDP_IP}:{STM32_UDP_PORT}")
        
        last_log_time = time.perf_counter()
        next_cycle_time = time.perf_counter()
        time_interval = 0.1  # 100ms = 10 Hz
        
        while True:
            try:
                # Read latest data
                from lib.json_data_handler import JSONDataHandler
                data_handler = JSONDataHandler()
                json_data = data_handler.read_data()
                
                # Convert to binary and send
                binary_data = convert_json_to_binary(json_data)
                udp_socket.sendto(binary_data, (STM32_UDP_IP, STM32_UDP_PORT))
                
                # Log every 10 seconds
                if time.perf_counter() - last_log_time >= 10:
                    eventlogger.logger.log_info("STM32 bitmask transmission running")
                    print("STM32 bitmask transmission running")
                    last_log_time = time.perf_counter()
                
                # Maintain precise timing
                next_cycle_time += time_interval
                sleep_duration = next_cycle_time - time.perf_counter()
                if sleep_duration > 0:
                    time.sleep(sleep_duration)
                    
            except Exception as e:
                eventlogger.logger.log_error(f"Error in continuous bitmask transmission: {e}")
                time.sleep(1)  # Wait before retrying
                
    except Exception as e:
        eventlogger.logger.log_error(f"Failed to start continuous bitmask transmission: {e}")
        print(f"Failed to start continuous bitmask transmission: {e}")
    finally:
        udp_socket.close()


if __name__ == '__main__':
    # Run UDP sender in a separate thread to keep sending data
    udp_thread = threading.Thread(target=send_udp_data, daemon=True)
    udp_thread.start()

    while True:
        time.sleep(2)
        get_data()
        time.sleep(2)

        # Example JSON string for post_data
        post_json_string = '{"thrusters": {"U_FWD_P": {"power": 75, "temp": 15}}}'
        post_data(post_json_string)

        time.sleep(2)
        get_data()
        time.sleep(2)

        # Example JSON string for patch_data
        patch_json_string = '{"thrusters": {"U_FWD_P": {"power": 100, "temp": 10}}}'
        patch_data(patch_json_string)