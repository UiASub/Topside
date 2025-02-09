import requests
import json
import json_data_handler
import eventlogger
import time

url = "127.0.0.1:5000"  #Raspberry pi ip og port
urlGet = f"http://{url}/data" #URL for å hente data
urlPost = f"http://{url}/post-data" #URL for å sende data
urlPatch = f"http://{url}/patch-data" #URL for å patche data

#Update rate er hvor ofte kontroller dataen sendes til ROV
UPDATE_RATE = 20 #Hz for eksempel 20 Hz = hvert 50 ms

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


def post_data():
    try:
        data = json_data_handler.JSONDataHandler().read_data()

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


def patch_data(patch_data):
    try:
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

# if __name__ == '__main__':
#     while True:
#         time.sleep(2)
#         get_data()
#         time.sleep(2)
#         post_data()
#         time.sleep(2)
#         get_data()
#         time.sleep(2)
#         patch_data({'thrusters': {"U_FWD_P": {"power": 100, "temp": 10}}})
