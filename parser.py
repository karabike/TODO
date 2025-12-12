from playwright.async_api import async_playwright
import asyncio
from sqlmodel import SQLModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class Product(SQLModel, table=True):
    __tablename__ = "products"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    price: str
    link: str

"""
class Product(BaseModel):
    name: str
    price: str
    link: str
"""


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

    async def parce_products(self, db: AsyncSession) -> None:
        cards = await self.page.query_selector_all(
            '[data-meta-name="SnippetProductVerticalLayout"]')
        print(f"Найдено товаров: {len(cards)}")
        added = 0
        updated = 0
        
        for card in cards:
            # Извлекаем данные о товаре
            name_el = await card.query_selector(
                '[data-meta-name="Snippet__title"]')
            name = await name_el.inner_text()

            link_el = await card.query_selector('a[href*="/product/"]')
            href = await link_el.get_attribute('href')
            link = self.BASE_URL + href

            price_el = await card.query_selector("[data-meta-price]")
            price = await price_el.get_attribute("data-meta-price")
            
            # Проверяем, существует ли товар с таким link
            stmt = select(Product).where(Product.link == link)
            result = await db.execute(stmt)
            existing_product = result.scalars().first()
            
            if existing_product:
                # Товар уже есть, обновляем цену если она изменилась
                if existing_product.price != price:
                    existing_product.price = price
                    updated += 1
                    print(f"Обновлена цена: {name} - {price}")
            else:
                # Товар новый, добавляем его
                product = Product(name=name, price=price, link=link)
                db.add(product)
                added += 1
        
        await db.commit()
        print(f"Добавлено: {added}, Обновлено: {updated}")

    async def close(self) -> None:
        await self.browser.close()
        print("Парсер завершил работу")


    """
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
        """
