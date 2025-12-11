from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):   
        await websocket.accept()
        self.active_connections.append(websocket)

    async def handle(self, data, websocket):
        if data == "spec":
            await websocket.send_text("spec ok")
        elif data == "close":
            await self.disconnect(websocket)
        else:
            websocket.send_text(data * 10)

    async def disconnect(self, websocket: WebSocket):
        await websocket.close()
        self.active_connections.remove(websocket)


manager = ConnectionManager() 