from fastapi import WebSocket
from typing import Dict, List


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        # Разделяем подписчиков по типам событий
        self.channels: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    async def connect_to_channel(self, channel: str, websocket: WebSocket):
        """Подписать клиента на канал событий"""
        await websocket.accept()
        if channel not in self.channels:
            self.channels[channel] = []
        self.channels[channel].append(websocket)
        self.active_connections.append(websocket)

    async def broadcast_to_channel(self, channel: str, message: str):
        """Отправить сообщение всем подписчикам канала"""
        if channel not in self.channels:
            return

        disconnected = []
        for websocket in self.channels[channel]:
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected.append(websocket)

        # Удаляем отключенные соединения
        for websocket in disconnected:
            await self.disconnect_from_channel(channel, websocket)

    async def handle(self, data, websocket):
        if data == "spec":
            await websocket.send_text("spec ok")
        elif data == "close":
            await self.disconnect(websocket)
        else:
            await websocket.send_text(data * 10)

    async def disconnect(self, websocket: WebSocket):
        """Отключить клиента от всех каналов"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        for channel_list in self.channels.values():
            if websocket in channel_list:
                channel_list.remove(websocket)

        try:
            await websocket.close()
        except Exception:
            pass

    async def disconnect_from_channel(self, channel: str,
                                      websocket: WebSocket):
        """Отключить клиента от конкретного канала"""
        if channel in self.channels:
            if websocket in self.channels[channel]:
                self.channels[channel].remove(websocket)

        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        try:
            await websocket.close()
        except Exception:
            pass


manager = ConnectionManager()
