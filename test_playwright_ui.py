import asyncio
from playwright.async_api import async_playwright
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    print("Launching Chromium browser via Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating to http://127.0.0.1:8500 ...")
        response = await page.goto("http://127.0.0.1:8500", timeout=15000)
        print("HTTP Status Code:", response.status)
        title = await page.title()
        print("Page Title:", title)
        assert "ATHENA" in title
        print("✅ Playwright successfully connected and rendered ATHENA UI!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
