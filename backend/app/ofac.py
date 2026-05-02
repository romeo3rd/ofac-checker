from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Page, async_playwright

from .config import OFAC_URL, USER_AGENT


@dataclass
class OfacSearchResult:
    status: str
    result_text: str
    pdf_path: Path


def classify_result(result_text: str) -> str:
    return "no_hit" if "0 Found" in result_text else "hit_found"


def safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80] or "name"


class OfacClient:
    async def __aenter__(self) -> "OfacClient":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(user_agent=USER_AGENT)
        self._page = await self._context.new_page()
        await self._page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "media"}
            else route.continue_(),
        )
        await self._page.goto(OFAC_URL, wait_until="domcontentloaded", timeout=60_000)
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._browser.close()
        await self._playwright.stop()

    async def search(self, name: str, pdf_path: Path) -> OfacSearchResult:
        page: Page = self._page
        await page.fill("input[id$='txtLastName']", name)
        async with page.expect_navigation(wait_until="networkidle", timeout=60_000):
            await page.click("input[id$='btnSearch']")

        result_text = await page.locator("#ctl00_MainContent_lblResults").inner_text(timeout=10_000)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        await page.pdf(
            path=str(pdf_path),
            landscape=True,
            format="a4",
            scale=0.84,
            print_background=False,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        return OfacSearchResult(
            status=classify_result(result_text),
            result_text=result_text,
            pdf_path=pdf_path,
        )
