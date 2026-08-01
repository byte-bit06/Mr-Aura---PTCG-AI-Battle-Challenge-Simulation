import os
import glob
import time
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def launch():
    print("Finding the latest replay...")
    replays = glob.glob("replays/*.json")
    if not replays:
        print("No replays found! Run generate_replays.py first.")
        return
        
    # Sort by modification time
    replays.sort(key=os.path.getmtime, reverse=True)
    latest_replay = os.path.abspath(replays[0])
    
    print(f"Launching visualizer for {latest_replay}...")
    
    # Setup Chrome
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True) # Keep browser open after script exits
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # 1. Open the Heroz visualizer
    driver.get("https://ptcgvis.heroz.jp/Visualizer/Replay/0")
    
    # 2. Wait for the file input to be present and upload the JSON
    try:
        print("Waiting for visualizer to load...")
        file_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
        )
        print("Uploading replay JSON...")
        file_input.send_keys(latest_replay)
        time.sleep(1) # Give it a second to parse
    except Exception as e:
        print("Could not find the upload button. You might need to upload it manually.")
        
    # 3. Inject the DAgger Annotator Bookmarklet
    print("Injecting DAgger Annotator...")
    js_code = """
    var s=document.createElement('script');
    s.src='http://localhost:5000/bookmarklet.js?t='+Date.now();
    document.body.appendChild(s);
    """
    driver.execute_script(js_code)
    
    print("Done! You can now use the Chrome window to annotate the replay.")
    print("NOTE: Make sure the annotate_past.py server is running in the background!")

if __name__ == "__main__":
    launch()
