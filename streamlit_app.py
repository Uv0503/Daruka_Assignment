import os
import subprocess
import sys
import time
import urllib.request
import streamlit as st

# Set the API base URL so the Streamlit UI knows where to talk to the local FastAPI backend
os.environ["API_BASE_URL"] = "http://127.0.0.1:8080"

def is_backend_running():
    """Check if the FastAPI backend is responding."""
    try:
        urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=1)
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
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8080"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Wait up to 60 seconds for it to become ready (in case it needs to download ML models first)
        for _ in range(120):
            if is_backend_running():
                print("FastAPI backend is ready!")
                return True, ""
            time.sleep(0.5)
            
        print("Backend failed to start in time.")
        
        # If it failed, let's grab the logs to see why
        process.terminate()
        try:
            outs, _ = process.communicate(timeout=2)
            return False, outs
        except subprocess.TimeoutExpired:
            process.kill()
            return False, "Timeout waiting for backend logs."
            
    return True, ""

# Ensure the backend is started
backend_ready, backend_logs = start_backend()

if not backend_ready:
    st.error("Failed to start the local FastAPI backend.")
    st.error("Backend Error Logs:")
    st.code(backend_logs)
    st.stop()

# Add the current directory to sys.path so 'ui.components' can be imported correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Execute the existing UI file within this Streamlit context
with open("ui/app.py", "r", encoding="utf-8") as f:
    app_code = f.read()

exec(app_code)
