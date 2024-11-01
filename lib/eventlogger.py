import logging
from datetime import datetime

MAX_IMPORTANT_LOGS = 10 # Maximum number of important logs to store for GUI display
LOG_FILE = f"logs/log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"

class Logger:
    def __init__(self, log_file=LOG_FILE, flush_on_start=True, max_important_logs=MAX_IMPORTANT_LOGS):
        self.log_file = log_file
        self.max_important_logs = max_important_logs
        self.info_logs_list = []
        self.warn_logs_list = []
        self.error_logs_list = []
        
        # Clear the log file on startup if required
        if flush_on_start:
            with open(self.log_file, 'w') as f:
                f.write('')

        # Configure the logging module
        logging.basicConfig(
            filename=self.log_file,
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def _add_to_info_list(self, message):
        """Helper function to add messages to the important log list for GUI display."""
        if len(self.info_logs_list) >= self.max_important_logs:
            self.info_logs_list.pop(0)  # Remove oldest log if at max capacity
        self.info_logs_list.append(message)
        
    def _add_to_warn_list(self, message):
        """Helper function to add messages to the important log list for GUI display."""
        if len(self.warn_logs_list) >= self.max_important_logs:
            self.warn_logs_list.pop(0)  # Remove oldest log if at max capacity
        self.warn_logs_list.append(message)
        
    def _add_to_error_list(self, message):
        """Helper function to add messages to the important log list for GUI display."""
        if len(self.error_logs_list) >= self.max_important_logs:
            self.error_logs_list.pop(0)  # Remove oldest log if at max capacity
        self.error_logs_list.append(message)

    def log_info(self, message):
        logging.info(message)
        self._add_to_info_list(f"INFO: {message}")

    def log_warning(self, message):
        logging.warning(message)
        self._add_to_warn_list(f"WARNING: {message}")

    def log_error(self, message):
        logging.error(message)
        self._add_to_error_list(f"ERROR: {message}")

    def log_custom(self, event_type, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"{timestamp} - {event_type} - {message}"
        
        # Write to file directly for custom events
        with open(self.log_file, 'a') as f:
            f.write(log_message + '\n')
        
        self._add_to_error_list(f"{event_type}: {message}")

    def get_info_logs(self):
        """Returns a list of important logs for GUI display."""
        return self.info_logs_list
    
    def get_warn_logs(self):
        """Returns a list of important logs for GUI display."""
        return self.warn_logs_list

    def get_error_logs(self):
        """Returns a list of important logs for GUI display."""
        return self.error_logs_list

logger = Logger()

# Example usage for testing
if __name__ == "__main__":
    logger.log_info("Application started")
    logger.log_warning("Low battery warning")
    logger.log_error("Connection to backend failed")
    logger.log_custom("CUSTOM_EVENT", "User initiated custom logging")

    # Retrieve important logs for GUI
    print(logger.get_error_logs())
