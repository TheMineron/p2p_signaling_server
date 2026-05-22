import json
import ssl

import websockets

SERVER_URL = "wss://130.193.45.202:8000/ws"
ROOM_ID = "perf_test_room"
NICKNAME_BASE = "test_user_"
NUM_USERS_LIST = list(range(2, 11))

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


async def join_room(user_id):
    ws = await websockets.connect(SERVER_URL, ssl=ssl_context)
    await ws.send(json.dumps({
        "type": "join",
        "room": ROOM_ID,
        "nickname": f"{NICKNAME_BASE}{user_id}"
    }))
    while True:
        msg = await ws.recv()
        data = json.loads(msg)
        if data.get("type") == "joined":
            participant_id = data["participant_id"]
            return ws, participant_id
