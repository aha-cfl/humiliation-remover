"""Drives Paycor's web clock with a headless browser.

Paycor's markup isn't public, so buttons are located by visible text. If that fails,
a screenshot is saved to DATA_DIR/last-failure.png; set SEL_CLOCK_IN / SEL_CLOCK_OUT
to a Playwright selector that matches your tenant's UI.
"""
import re

from playwright.async_api import Page, async_playwright

from .config import Config

BUTTON_TEXT = {
    "in": re.compile(r"^\s*(clock|punch)\s*in\s*$", re.I),
    "out": re.compile(r"^\s*(clock|punch)\s*out\s*$", re.I),
}
CONFIRM_TEXT = re.compile(r"(clocked|punched)\s*(in|out)|punch (recorded|successful)|success", re.I)
NEXT_TEXT = re.compile(r"^\s*(next|continue|sign in|log in|login)\s*$", re.I)


class PunchError(Exception):
    pass


async def _login_if_needed(page: Page, cfg: Config) -> None:
    user = page.locator("input[type=email], input[name*=user i], input[id*=user i]").first
    pwd = page.locator("input[type=password]").first
    if not (await user.is_visible() or await pwd.is_visible()):
        return
    if not (cfg.paycor_user and cfg.paycor_pass):
        raise PunchError("session expired and PAYCOR_USER/PAYCOR_PASS not set; rerun login")
    if await user.is_visible():
        await user.fill(cfg.paycor_user)
        if not await pwd.is_visible():
            await page.get_by_role("button", name=NEXT_TEXT).first.click()
            await pwd.wait_for(state="visible", timeout=15000)
    await pwd.fill(cfg.paycor_pass)
    await page.get_by_role("button", name=NEXT_TEXT).first.click()
    await page.wait_for_load_state("networkidle", timeout=30000)
    if await page.locator("input[autocomplete=one-time-code], input[name*=code i]").first.is_visible():
        raise PunchError("Paycor is asking for an MFA code; rerun `python -m autopunch.login`")


async def _find_button(page: Page, action: str, cfg: Config):
    override = cfg.sel_clock_in if action == "in" else cfg.sel_clock_out
    if override:
        return page.locator(override).first
    btn = page.get_by_role("button", name=BUTTON_TEXT[action]).first
    if await btn.count():
        return btn
    return page.get_by_text(BUTTON_TEXT[action]).first


async def punch(action: str, cfg: Config) -> str:
    """Perform the punch. Returns the confirmation text; raises PunchError on failure."""
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=cfg.headless)
        ctx = await browser.new_context(
            storage_state=str(cfg.session_file) if cfg.session_file.exists() else None)
        page = await ctx.new_page()
        try:
            await page.goto(cfg.paycor_url, wait_until="networkidle", timeout=60000)
            await _login_if_needed(page, cfg)
            btn = await _find_button(page, action, cfg)
            try:
                await btn.wait_for(state="visible", timeout=30000)
            except Exception as e:
                raise PunchError(f"could not find clock-{action} button") from e
            await btn.click()
            # Some tenants show a confirm dialog after the first click.
            confirm_btn = page.get_by_role("button", name=re.compile(r"^\s*(confirm|yes|ok|submit)\s*$", re.I))
            try:
                await confirm_btn.first.click(timeout=5000)
            except Exception:
                pass
            try:
                msg = page.get_by_text(CONFIRM_TEXT).first
                await msg.wait_for(state="visible", timeout=20000)
                text = (await msg.inner_text()).strip()
            except Exception as e:
                raise PunchError("clicked but saw no confirmation; verify in Paycor") from e
            await ctx.storage_state(path=str(cfg.session_file))
            return text
        except Exception:
            await page.screenshot(path=str(cfg.data_dir / "last-failure.png"), full_page=True)
            raise
        finally:
            await browser.close()
