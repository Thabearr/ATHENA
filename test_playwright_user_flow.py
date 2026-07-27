import asyncio
import os
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACTS_DIR = r"C:\Users\boisa\.gemini\antigravity-ide\brain\22d6478c-1673-4e13-a8ac-cfc26b10db8b"

async def run_user_simulation():
    print("==================================================")
    print("   🎭 PLAYWRIGHT USER INTERACTION SIMULATION 🎭  ")
    print("==================================================")

    async with async_playwright() as p:
        print("\n1. Launching Chromium Browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        # Step 1: Open App
        print("2. Navigating to http://127.0.0.1:8500 ...")
        await page.goto("http://127.0.0.1:8500", wait_until="networkidle")
        title = await page.title()
        print(f"   Page Title: {title}")

        dashboard_screenshot = os.path.join(ARTIFACTS_DIR, "1_dashboard_view.png")
        await page.screenshot(path=dashboard_screenshot)
        print(f"   Saved screenshot: {dashboard_screenshot}")

        # Step 2: Navigate to Acca Builder
        print("\n3. Navigating to Acca Builder (nav-generate)...")
        await page.click("#nav-generate")
        await page.wait_for_timeout(500)

        # Step 3: Fill Form & Click Generate
        print("4. Filling Acca Builder Form (Days: 1, Folds: 5)...")
        await page.fill("#input-days", "1")
        await page.fill("#input-folds", "5")
        
        builder_screenshot = os.path.join(ARTIFACTS_DIR, "2_acca_builder_view.png")
        await page.screenshot(path=builder_screenshot)

        print("5. Clicking 'Generate Slip' button...")
        await page.click("#btn-generate")
        
        # Wait for results or timeout
        await page.wait_for_timeout(3000)
        
        slip_screenshot = os.path.join(ARTIFACTS_DIR, "3_generated_slip_view.png")
        await page.screenshot(path=slip_screenshot)
        print(f"   Saved screenshot: {slip_screenshot}")

        # Step 4: Navigate to Global Fixtures
        print("\n6. Navigating to Global Fixtures (nav-fixtures)...")
        await page.click("#nav-fixtures")
        await page.wait_for_timeout(1000)

        fixtures_screenshot = os.path.join(ARTIFACTS_DIR, "4_fixtures_view.png")
        await page.screenshot(path=fixtures_screenshot)
        print(f"   Saved screenshot: {fixtures_screenshot}")

        # Step 5: Navigate to Athenizer
        print("\n7. Navigating to Athenizer (nav-athenizer)...")
        await page.click("#nav-athenizer")
        await page.wait_for_timeout(500)

        athenizer_screenshot = os.path.join(ARTIFACTS_DIR, "5_athenizer_view.png")
        await page.screenshot(path=athenizer_screenshot)
        print(f"   Saved screenshot: {athenizer_screenshot}")

        # Step 6: Test Athenizer Tabs (Split & Merge)
        print("8. Testing Athenizer Tabs: Split Slip & Merge Slips...")
        await page.click("button[data-target='tab-split']")
        await page.wait_for_timeout(300)
        
        await page.click("button[data-target='tab-merge']")
        await page.wait_for_timeout(300)

        merge_screenshot = os.path.join(ARTIFACTS_DIR, "6_athenizer_merge_view.png")
        await page.screenshot(path=merge_screenshot)
        print(f"   Saved screenshot: {merge_screenshot}")

        print("\n==================================================")
        print("   ✅ USER SIMULATION COMPLETE & SCREENSHOTS SAVED ")
        print("==================================================")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_user_simulation())
