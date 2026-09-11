import os
import subprocess
import sys
import time
import urllib.request
import streamlit as st

# Set the API base URL so the Streamlit UI knows where to talk to the local FastAPI backend
os.environ["API_BASE_URL"] = "http://127.0.0.1:8000"

def is_backend_running():
    """Check if the FastAPI backend is responding."""
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
        return True
    except Exception:
        return False

# Use st.cache_resource to ensure we only spin up the backend once per Streamlit server lifecycle,
# not every time the Streamlit UI reruns.
@st.cache_resource
def start_backend():
    if not is_backend_running():
        print("Starting FastAPI backend...")
        # Start the FastAPI server in the background
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        # Wait up to 10 seconds for it to become ready
        for _ in range(20):
            if is_backend_running():
                print("FastAPI backend is ready!")
                return True
            time.sleep(0.5)
        print("Backend failed to start in time.")
        return False
    return True

# Ensure the backend is started
backend_ready = start_backend()

if not backend_ready:
    st.error("Failed to start the local FastAPI backend.")
    st.stop()

# Add the current directory to sys.path so 'ui.components' can be imported correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Execute the existing UI file within this Streamlit context
with open("ui/app.py", "r", encoding="utf-8") as f:
    app_code = f.read()

exec(app_code)
