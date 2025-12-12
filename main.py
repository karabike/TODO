from __future__ import annotations
import asyncio
import time
from fastapi import (
    FastAPI,
    Request,
    HTTPException,
    BackgroundTasks,
    Depends,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import SQLModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import engine, DBSession, get_db
from parser import CitilinkParser
from wsconmanager import manager


class TaskModel(SQLModel, table=True):
    __tablename__ = "tasks"

    id: int | None = Field(primary_key=True)
    title: str
    description: str
    done: bool = False

app = FastAPI(
    title="TODO API",
    version="1.0"
)

# Флаг для отслеживания работающей задачи парсера
parser_task = None


@app.on_event("startup")
async def on_startup():
    global parser_task
    async with engine.begin() as conn:
        await conn.run_sync(
            SQLModel.metadata.create_all
        )
    # Запуск периодического парсинга при старте
    parser_task = asyncio.create_task(auto_parser())


@app.on_event("shutdown")
async def on_shutdown():
    global parser_task
    if parser_task and not parser_task.done():
        parser_task.cancel()
        try:
            await asyncio.wait_for(parser_task, timeout=5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


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


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    done: bool | None = None


class Task(BaseModel):
    id: int
    title: str
    description: str
    done: bool = False


async def auto_parser() -> None:
    """Автоматический парсинг каждые 60 минут"""
    while True:
        citi_parser = None
        db = None
        try:
            print("Запуск автоматического парсинга...")
            db = DBSession()
            citi_parser = CitilinkParser()
            await citi_parser.start()

            async def func(x: str) -> None:
                await citi_parser.load_page(x)
                await citi_parser.parce_products(db)

            async def paginator(url: str, max_pages: int) -> None:
                for page in range(max_pages):
                    new_url = url + f"?p={page + 1}"
                    await func(new_url)
                await citi_parser.close()
                print("Автоматический парсинг завершен!")

            category_url = "https://www.citilink.ru/catalog/smartfony/"
            await paginator(category_url, max_pages=2)
        except asyncio.CancelledError:
            print("Парсинг был отменен")
            if citi_parser:
                try:
                    await citi_parser.close()
                except Exception:
                    pass
            raise
        except Exception as e:
            print(f"Ошибка при парсинге: {e}")
        finally:
            if db:
                try:
                    await db.close()
                except Exception:
                    pass
        
        # Ждем 60 минут перед следующим запуском
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            print("Приложение завершает работу")
            raise


@app.get("/tasks", response_model=list[TaskModel])
async def get_tasks(db: AsyncSession = Depends(get_db)):
    stmnt = select(TaskModel)
    result = await db.execute(stmnt)
    return result.scalars()


@app.get("/tasks/{task_id}", response_model=TaskModel)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(TaskModel, task_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Tasks not found")
    return obj


@app.post("/tasks", response_model=Task, status_code=201)
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db)):
    new_task = TaskModel(
        title=task.title,
        description=task.description
    )
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    
    # Отправляем уведомление подписчикам
    import json
    await manager.broadcast_to_channel(
        "tasks",
        json.dumps({
            "event": "task_created",
            "task": {
                "id": new_task.id,
                "title": new_task.title,
                "description": new_task.description,
                "done": new_task.done
            }
        })
    )
    return new_task


@app.put("/task/{task_id}", response_model=TaskModel)
async def update_task(task_id: int, updated: TaskUpdate,
                      db: AsyncSession = Depends(get_db)):
    stmt = select(TaskModel).where(TaskModel.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Tasks not found")
    
    # Проверяем, изменился ли статус done
    status_changed = (updated.done is not None and
                      task.done != updated.done)
    old_done_status = task.done
    
    # Обновляем только переданные поля
    if updated.title is not None:
        task.title = updated.title
    if updated.description is not None:
        task.description = updated.description
    if updated.done is not None:
        task.done = updated.done

    await db.commit()
    await db.refresh(task)
    
    # Отправляем уведомление о изменении статуса
    if status_changed:
        import json
        await manager.broadcast_to_channel(
            "tasks",
            json.dumps({
                "event": "task_status_changed",
                "task": {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "done": task.done,
                    "previous_done": old_done_status
                }
            })
        )
    
    return task


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
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


@app.get("/parser")
async def parser(background_task: BackgroundTasks):
    async def run_parser() -> None:
        db = DBSession()
        try:
            citi_parser = CitilinkParser()
            await citi_parser.start()

            async def func(x: str) -> None:
                await citi_parser.load_page(x)
                await citi_parser.parce_products(db)

            async def paginator(url: str, max_pages: int) -> None:
                for page in range(max_pages):
                    new_url = url + f"?p={page + 1}"
                    await func(new_url)
                await citi_parser.close()
                print("Парсинг завершен!")

            category_url = "https://www.citilink.ru/catalog/smartfony/"
            await paginator(category_url, max_pages=2)
        finally:
            await db.close()

    background_task.add_task(run_parser)
    return {"message": "Парсер запущен в фоне"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    async def tick():
        while True:
            await websocket.send_text("tick")
            await asyncio.sleep(10)
    asyncio.create_task(tick())
    try:
        while True:
            data = await websocket.receive_text()
            await manager.handle(data, websocket)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


@app.websocket("/ws/tasks")
async def websocket_tasks(websocket: WebSocket):
    """WebSocket канал для уведомлений о новых задачах"""
    await manager.connect_to_channel("tasks", websocket)
    try:
        while True:
            # Слушаем сообщения от клиента (для keep-alive)
            data = await websocket.receive_text()
            if data == "close":
                break
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
