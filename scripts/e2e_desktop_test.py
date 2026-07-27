import os
import sys
import time
import subprocess
import requests
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ARTIFACTS_DIR = r"C:\Users\boisa\.gemini\antigravity\brain\39459eb3-502f-4562-adb2-3e52e4128392"
SERVER_URL = "http://127.0.0.1:8500"

def ensure_server_running():
    try:
        r = requests.get(f"{SERVER_URL}/api/status", timeout=2)
        if r.status_code == 200:
            print("FastAPI server is already running.")
            return None
    except Exception:
        pass

    print("Starting FastAPI server in background...")
    proc = subprocess.Popen([sys.executable, "api/server.py"], cwd=os.getcwd())
    for _ in range(15):
        time.sleep(1)
        try:
            r = requests.get(f"{SERVER_URL}/api/status", timeout=2)
            if r.status_code == 200:
                print("FastAPI server started successfully.")
                return proc
        except Exception:
            continue
    raise RuntimeError("Could not connect to FastAPI server.")

def run_e2e_test():
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    server_proc = ensure_server_running()

    print("Initializing Edge WebDriver in headless mode...")
    options = EdgeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1400,900")
    
    driver = webdriver.Edge(options=options)
    try:
        print(f"Navigating to {SERVER_URL}...")
        driver.get(SERVER_URL)
        time.sleep(3)

        # 1. Capture Dashboard Screenshot
        dash_shot = os.path.join(ARTIFACTS_DIR, "desktop_dashboard.png")
        driver.save_screenshot(dash_shot)
        print(f"Captured Dashboard screenshot: {dash_shot}")

        # 2. Click Fixtures tab
        print("Testing Navigation: Fixtures tab...")
        fixtures_nav = driver.find_element(By.ID, "nav-fixtures")
        fixtures_nav.click()
        time.sleep(4)
        fixtures_shot = os.path.join(ARTIFACTS_DIR, "desktop_fixtures.png")
        driver.save_screenshot(fixtures_shot)
        print(f"Captured Fixtures screenshot: {fixtures_shot}")

        # 3. Click Athenizer tab
        print("Testing Navigation: Athenizer tab...")
        athenizer_nav = driver.find_element(By.ID, "nav-athenizer")
        athenizer_nav.click()
        time.sleep(2)
        athenizer_shot = os.path.join(ARTIFACTS_DIR, "desktop_athenizer.png")
        driver.save_screenshot(athenizer_shot)
        print(f"Captured Athenizer screenshot: {athenizer_shot}")

        # 4. Click Settings tab
        print("Testing Navigation: Settings tab...")
        settings_nav = driver.find_element(By.ID, "nav-settings")
        settings_nav.click()
        time.sleep(2)
        settings_shot = os.path.join(ARTIFACTS_DIR, "desktop_settings.png")
        driver.save_screenshot(settings_shot)
        print(f"Captured Settings screenshot: {settings_shot}")

        # 5. Click Generate tab & trigger Accumulator generation
        print("Testing Accumulator Generation flow...")
        gen_nav = driver.find_element(By.ID, "nav-generate")
        gen_nav.click()
        time.sleep(2)

        btn_generate = driver.find_element(By.ID, "btn-generate")
        btn_generate.click()
        print("Clicked 'Generate Accumulator'. Waiting for generation to complete...")

        # Wait for results area or loader to clear
        wait = WebDriverWait(driver, 90)
        wait.until(EC.visibility_of_element_located((By.ID, "results-area")))
        time.sleep(3)

        results_shot = os.path.join(ARTIFACTS_DIR, "desktop_generation_result.png")
        driver.save_screenshot(results_shot)
        print(f"Captured Generation Results screenshot: {results_shot}")

        print("=== ALL DESKTOP E2E TESTS PASSED SUCCESSFULLY ===")

    finally:
        driver.quit()
        if server_proc:
            server_proc.terminate()

if __name__ == "__main__":
    run_e2e_test()
