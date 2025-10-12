from flask import Flask
from lib.camera import init_camera
from routes import register_routes

# Flask app for the main dashboard
app = Flask(__name__, static_folder="static", template_folder="static/templates")

register_routes(app)

# Initialize camera
camera = init_camera()


# Function to run the dashboard server
def run_dashboard_server():
    print("Starting dashboard server on port 5000...")
    app.run(debug=True, port=5000, use_reloader=False)


if __name__ == "__main__":
    # Start only the dashboard process
    run_dashboard_server()
