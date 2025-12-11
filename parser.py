from playwright.async_api import async_playwright 
from pydantic import BaseModel
import asyncio


class Product(BaseModel):
    name: str
    price: str
    link: str


class CitilinkParser:

    BASE_URL = "https://www.citilink.ru"

    async def start(self):
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        context = await self.browser.new_context()
        self.page = await context.new_page()

    async def load_page(self, url):
        await self.page.goto(url, timeout=150000)
        await self.page.wait_for_selector(
            '[data-meta-name="SnippetProductVerticalLayout"]',
            timeout=15000)
        await asyncio.sleep(2)

    async def parce_products(self) -> list[Product]:
        products = []
        cards = await self.page.query_selector_all(
            '[data-meta-name="SnippetProductVerticalLayout"]',)
        print(f"Найдено товаров: {len(cards)}")
        for card in cards:
            name_el = await card.query_selector('[data-meta-name="Snippet__title"]')
            name = await name_el.inner_text()

            link_el = await card.query_selector('a[href*="/product/"]')
            href = await link_el.get_attribute('href')
            link = self.BASE_URL + href
            price_el = await card.query_selector("[data-meta-price]")
            price = await price_el.get_attribute("data-meta-price")

            products.append(
                Product(
                    name=name,
                    link=link,
                    price=price
                )
            )
        return products
