"""One-time interactive login to capture a Paycor session (handles MFA).

Run on a machine with a screen:  python -m autopunch.login
Log in fully in the window that opens, then press Enter here.
Copy the resulting data/paycor_session.json to the server's DATA_DIR.
"""
import asyncio

from playwright.async_api import async_playwright

from .config import Config


async def main() -> None:
    cfg = Config()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(cfg.paycor_url)
        await asyncio.to_thread(input, "Log in (tick 'remember this device' if offered), then press Enter... ")
        await ctx.storage_state(path=str(cfg.session_file))
        await browser.close()
    print(f"Saved session to {cfg.session_file}")


if __name__ == "__main__":
    asyncio.run(main())
