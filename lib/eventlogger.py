import logging
from datetime import datetime

# Flag to determine whether to flush the log on startup
FLUSH_LOG_ON_START = True

if FLUSH_LOG_ON_START:
    with open('event_log.txt', 'w') as f:
        f.write('')  # Overwrite any existing content, effectively clearing the file

# Configure the logging
logging.basicConfig(
    filename='event_log.txt',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Function to log general information
def log_info(message):
    logging.info(message)

# Function to log warnings
def log_warning(message):
    logging.warning(message)

# Function to log errors
def log_error(message):
    logging.error(message)

# Function to log a custom event
def log_custom(event_type, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open('event_log.txt', 'a') as f:
        f.write(f"{timestamp} - {event_type} - {message}\n")

# Example usage for testing
if __name__ == "__main__":
    log_info("Application started")
    log_warning("Low battery warning")
    log_error("Connection to backend failed")
    log_custom("CUSTOM_EVENT", "User initiated custom logging")