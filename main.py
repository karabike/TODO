from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import asyncio
import time
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import SQLModel, Field

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from playwright.async_api import async_playwright

Base = declarative_base()
engine = create_async_engine(
    "sqlite+aiosqlite:///./tasks.db"
)
DBSession = sessionmaker(bind=engine, autoflush=False,
                         autocommit=False, class_=AsyncSession)


class TaskModel(SQLModel, table=True):
    __tablename__ = "tasks"

    id: int | None = Field(primary_key=True)
    title: str
    description: str
    done: bool = False


async def get_db():
    db = DBSession()
    try:
        yield db
    finally:
        await db.close()

app = FastAPI(
    title="TODO API",
    version="1.0"
)


@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(
            SQLModel.metadata.create_all
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    print(
        f"Request to {request.url.path} processed in {process_time:.4f} seconds")
    return response


@app.get("/add")
def add_numbers(a: int, b: int):
    return {"result": a + b}


class TaskCreate(BaseModel):
    title: str
    description: str


class TaskUpdate(TaskCreate):
    title: str
    description: str
    done: bool = False


class Task(TaskUpdate):
    id: int


tasks: list[Task] = []
next_id = 1


@app.get("/tasks", response_model=list[TaskModel])
async def get_tasks(db: DBSession = Depends(get_db)):
    stmnt = Select(TaskModel)
    result = await db.execute(stmnt)
    return result.scalars()


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int, db: DBSession = Depends(get_db)):
    for t in tasks:
        if t.id == task_id:
            return t
    raise HTTPException(status_code=404, detail="Task not found")


@app.post("/tasks", response_model=Task, status_code=201)
async def create_task(task: TaskCreate, db: DBSession = Depends(get_db)):
    new_task = TaskModel(
        title=task.title,
        description=task.description
    )
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    return new_task


@app.put("/task/{task_id}", response_model=Task)
async def update_task(task_id: int, updated: TaskUpdate):
    for idx, t in enumerate(tasks):
        if t.id == task_id:
            tasks[idx] = Task(
                id=t.id,
                title=updated.title,
                description=updated.description,
                done=updated.done
            )
            return tasks[idx]
    raise HTTPException(status_code=404, detail="Tasks not found")


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, db: DBSession = Depends(get_db)):
    obj = await db.get(TaskModel, task_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Tasks not found")
    await db.delete(obj)
    await db.commit()

"""
@app.get("/async_task")
async def async_task():
    await asyncio.sleep(60)
    return {"message": "ok"}


@app.get("/background_task")
async def background_task(background_task: BackgroundTasks):
    def slow_time():
        import time
        time.sleep(10)
        print("ok")
        print("ok")
        print("ok")

    background_task.add_task(slow_time)
    return {"message": "task started"}


excutor = ThreadPoolExecutor(max_workers=2)
excutor = ProcessPoolExecutor(max_workers=2)


def blocking_io_task():
    import time

    time.sleep(60)
    return "ok"


@app.get("/thread_pool_sleep")
async def thread_pool_sleep():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(excutor, blocking_io_task)
    return {"message": result}


def heavy_func(n: int):
    result = 0
    for i in range(n):
        result += i * i
    return result


@app.get("/cpu_task")
async def cpu_task(n: int = 10000000000):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(excutor, heavy_func, n)
    return {
        "message": result
    }
"""


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

    async def parce_products(self) -> list [Product]:
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


@app.get("/parser")
async def parser(background_task: BackgroundTasks):
    citi_parser = CitilinkParser()

    async def func(x):
        await citi_parser.start()
        await citi_parser.load_page(x)
        products = await citi_parser.parce_products()
        print(products)

    async def paginator(url, max_pages):

        for page in range(max_pages):
            new_url = url + f"?p={page + 1}"
            await func(new_url)

    category_url = "https://www.citilink.ru/catalog/smartfony/"
    background_task.add_task(paginator, category_url, max_pages=5)
    return {"message": "Парсер запущен в фоне"}
