import asyncio
import json
import logging
import ssl
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from jinja2 import Environment
from starlette.requests import Request
from starlette.responses import HTMLResponse

from commands import get_commands_metadata
from commands.register import get_commands_handlers
from filters import pretty_json
from room_manager import RoomManager
from utils import CommandContext, safe_send_json, broadcast_to_room
from database.redis_client import init_redis, close_redis, redis_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

room_manager = RoomManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    logger.info("Signaling server started")
    yield
    await close_redis()
    logger.info("Signaling server stopped")


templates = Jinja2Templates(directory="static/html")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

command_handlers = get_commands_handlers()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    current_room = None
    current_participant = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Получен невалидный JSON")
                continue

            msg_type = msg.get("type")
            if not msg_type:
                continue

            handler = command_handlers.get(msg_type)
            if handler is None:
                logger.debug(f"Неизвестный тип сообщения: {msg_type}")
                continue

            ctx = CommandContext(websocket, room_manager, current_room, current_participant)
            try:
                new_room, new_participant = await handler(ctx, msg)
                current_room, current_participant = new_room, new_participant
            except Exception as e:
                logger.exception(f"Ошибка при обработке команды {msg_type}: {e}")
                await safe_send_json(websocket, data={
                    "type": "error",
                    "message": "Internal error"
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket отключён: {current_participant}")
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
    finally:
        if current_room and current_participant:
            removed = await room_manager.remove_participant(current_room, current_participant.id)
            if removed:
                logger.info(f"Участник {current_participant} удалён из комнаты {current_room}")
                await broadcast_to_room(
                    current_room,
                    message={
                        "type": "participant_left",
                        "participant_id": current_participant.id
                    },
                    exclude_ws=websocket
                )
                await room_manager.remove_if_empty(current_room.id)
        try:
            await websocket.close()
        except Exception:
            logger.exception("Ошибка при закрытии WebSocket")


@app.get("/health")
async def health():
    if await redis_client.ping():
        return {"status": "ok"}
    return {"status": "redis_down"}, 503


@app.get("/docs/websocket", response_class=HTMLResponse)
async def websocket_docs(request: Request):
    metadata = get_commands_metadata()
    groups = {}
    for cmd, meta in metadata.items():
        group = meta.get("group", "other")
        if group not in groups:
            groups[group] = {}
        groups[group][cmd] = meta
    return templates.TemplateResponse(request,"websocket_docs.html", context={
        "request": request,
        "groups": groups,
    })


templates.env.filters['pretty_json'] = pretty_json

async def main():
    cert_file = Path("cert.pem")
    key_file = Path("key.pem")
    ssl_context = None
    proto = "ws"

    if cert_file.exists() and key_file.exists():
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(str(cert_file), str(key_file))
        proto = "wss"
        logger.info("SSL certificates found, starting with WSS")
    else:
        logger.warning("SSL certificates not found, starting without encryption (WS)")

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        ssl_certfile=str(cert_file) if ssl_context else None,
        ssl_keyfile=str(key_file) if ssl_context else None,
    )
    server = uvicorn.Server(config)
    logger.info(f"Signaling server starting on {proto}://0.0.0.0:8000")
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
