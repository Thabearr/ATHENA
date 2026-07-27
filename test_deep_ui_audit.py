import asyncio
import os
import sys
# pyrefly: ignore [missing-import]
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')
ARTIFACTS_DIR = r"C:\Users\boisa\.gemini\antigravity-ide\brain\22d6478c-1673-4e13-a8ac-cfc26b10db8b"

console_logs = []
js_errors = []

import threading
import uvicorn
import time
import requests
from api.server import app

def ensure_server_running():
    global SERVER_URL
    SERVER_URL = "http://127.0.0.1:8505"
    print("   Starting fresh local FastAPI server on port 8505...")
    def run_srv():
        uvicorn.run(app, host="127.0.0.1", port=8505, log_level="error")

    t = threading.Thread(target=run_srv, daemon=True)
    t.start()
    time.sleep(2.5)

async def deep_ui_audit():
    ensure_server_running()
    print("==================================================")
    print("     🔍 DEEP ATHENA UI & FUNCTIONALITY AUDIT 🔍   ")
    print("==================================================")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 850})
        page = await context.new_page()

        # Listen to console messages and errors
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: js_errors.append(str(err)))

        # 1. Dashboard Audit
        print("\n1. Auditing Dashboard View...")
        await page.goto(SERVER_URL, wait_until="networkidle")
        await page.wait_for_timeout(1000)
        
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "audit_1_dashboard.png"))
        print("   ✅ Dashboard loaded & captured.")

        # 2. Acca Builder Audit
        print("\n2. Auditing Acca Builder View...")
        await page.click("#nav-generate")
        await page.wait_for_timeout(500)
        
        # Test inputs
        await page.fill("#input-days", "1")
        await page.fill("#input-folds", "5")
        
        # Wait for dynamic league checkboxes to load
        try:
            await page.wait_for_selector(".league-checkbox", timeout=25000)
            checkboxes = await page.query_selector_all(".league-checkbox")
            print(f"   ✅ Dynamic League Checkboxes Loaded: {len(checkboxes)} leagues available!")
        except Exception as e:
            print(f"   ⚠️ League checkboxes timeout: {e}")

        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "audit_2_acca_builder.png"))

        # Click Generate Slip
        print("   Clicking 'Generate Slip'...")
        await page.click("#btn-generate")
        
        # Wait for generation to finish (loader overlay hides or results table populates)
        try:
            await page.wait_for_selector("#results-area:not(.hidden)", timeout=45000)
            table_html = await page.inner_html("#acca-table")
            has_results = "Ready to generate" not in table_html
            print(f"   ✅ Accumulator Slip Generated Successfully! Table Populate: {has_results}")
        except Exception as e:
            print(f"   ⚠️ Acca generation timeout/wait: {e}")

        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "audit_3_acca_generated.png"))

        # Test Export Code dropdown & button
        print("   Testing Booking Code Export Dropdown...")
        await page.select_option("#input-export-bookie", "sportybet")
        await page.click("#btn-export-code")
        await page.wait_for_timeout(4000)
        export_text = await page.inner_text("#export-results")
        print(f"   Booking Code Export Result: {export_text.strip()[:100]}")
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "audit_4_export_code.png"))

        # 3. Global Fixtures Audit
        print("\n3. Auditing Global Fixtures View...")
        await page.click("#nav-fixtures")
        try:
            await page.wait_for_selector(".fixture-card, .date-btn, .league-group", timeout=25000)
            fixtures_content = await page.inner_text("#fixtures-container")
            print(f"   ✅ Fixtures Loaded! Container text length: {len(fixtures_content)}")
        except Exception as e:
            print(f"   ⚠️ Fixtures wait timeout: {e}")
            
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "audit_5_fixtures.png"))

        # 4. Athenizer Audit
        print("\n4. Auditing Athenizer View...")
        await page.click("#nav-athenizer")
        await page.wait_for_timeout(500)

        # Tab 1: Optimize
        print("   Testing Tab 1: Optimize...")
        await page.fill("#input-vet-code", "TESTBC123")
        await page.select_option("#input-vet-bookie", "sportybet")
        await page.click("#btn-vet-slip")
        await page.wait_for_timeout(1000)
        vet_res = await page.inner_text("#vet-results")
        print(f"   Optimize Result: {vet_res[:80]}...")
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "audit_6_athenizer_optimize.png"))

        # Tab 2: Split
        print("   Testing Tab 2: Split...")
        await page.click("button[data-target='tab-split']")
        await page.fill("#input-split-code", "TESTSPLIT99")
        await page.fill("#input-split-parts", "2")
        await page.click("#btn-split-slip")
        await page.wait_for_timeout(1000)
        split_res = await page.inner_text("#split-results")
        print(f"   Split Result: {split_res[:80]}...")
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "audit_7_athenizer_split.png"))

        # Tab 3: Merge
        print("   Testing Tab 3: Merge...")
        await page.click("button[data-target='tab-merge']")
        await page.fill("#input-merge-codes", "CODE1, CODE2")
        await page.click("#btn-merge-slips")
        await page.wait_for_timeout(1000)
        merge_res = await page.inner_text("#merge-results")
        print(f"   Merge Result: {merge_res[:80]}...")
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "audit_8_athenizer_merge.png"))

        # 5. Engine Status Audit
        print("\n5. Auditing Engine Status View...")
        await page.click("#nav-settings")
        await page.wait_for_timeout(500)
        await page.screenshot(path=os.path.join(ARTIFACTS_DIR, "audit_9_engine_status.png"))

        print("\n==================================================")
        print("                AUDIT SUMMARY                     ")
        print("==================================================")
        print(f"JS Console Errors: {len(js_errors)}")
        for err in js_errors:
            print(f" ❌ {err}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(deep_ui_audit())
