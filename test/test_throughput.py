import asyncio
import json
import time
import websockets
import matplotlib.pyplot as plt

from test.config import ssl_context, ROOM_ID, SERVER_URL, NUM_USERS_LIST

MESSAGES_PER_TEST = 2000


async def join_room(user_id):
    ws = await websockets.connect(SERVER_URL, ssl=ssl_context)
    await ws.send(json.dumps({
        "type": "join",
        "room": ROOM_ID,
        "nickname": f"user_{user_id}"
    }))
    while True:
        msg = await ws.recv()
        data = json.loads(msg)
        if data.get("type") == "joined":
            return ws, data["participant_id"]


async def run_test(num_users):
    print(f"Тест с {num_users} участниками...")
    connections = []
    ids = []
    for i in range(num_users):
        ws, pid = await join_room(i)
        connections.append(ws)
        ids.append(pid)
        await asyncio.sleep(0.05)

    sender_ws = connections[0]
    receiver_ws = connections[1]
    target_id = ids[1]

    for _ in range(10):
        try:
            await asyncio.wait_for(receiver_ws.recv(), timeout=0.1)
        except asyncio.TimeoutError:
            break
        except:
            pass

    send_times = []
    for i in range(MESSAGES_PER_TEST):
        send_time = time.perf_counter()
        await sender_ws.send(json.dumps({
            "type": "signal",
            "target_id": target_id,
            "data": {"seq": i, "send_time": send_time}
        }))
        send_times.append(send_time)

    received = []
    timeout = 30
    end_time = time.perf_counter() + timeout
    while len(received) < MESSAGES_PER_TEST and time.perf_counter() < end_time:
        try:
            msg = await asyncio.wait_for(receiver_ws.recv(), timeout=1.0)
        except asyncio.TimeoutError:
            print(f"  Таймаут при приёме, получено {len(received)}/{MESSAGES_PER_TEST}")
            break
        data = json.loads(msg)
        if data.get("type") == "signal" and "seq" in data.get("data", {}):
            recv_time = time.perf_counter()
            received.append((data["data"]["seq"], recv_time))

    if len(received) == 0:
        print("  Не получено ни одного сигнала! Проверьте соединение.")
        throughput = 0
    else:
        total_time = received[-1][1] - send_times[0]
        throughput = MESSAGES_PER_TEST / total_time if total_time > 0 else 0
        print(
            f"  Получено: {len(received)}/{MESSAGES_PER_TEST}, "
            f"время: {total_time:.2f} с, "
            f"пропускная способность: {throughput:.0f} msg/s")

    for ws in connections:
        await ws.close()
    return throughput


async def main():
    results = []
    for n in NUM_USERS_LIST:
        tp = await run_test(n)
        results.append((n, tp))
        await asyncio.sleep(2)

    users = [r[0] for r in results]
    throughputs = [r[1] for r in results]

    plt.figure(figsize=(8, 5))
    plt.plot(users, throughputs, 'o-', label='Пропускная способность')
    plt.axhline(y=1000, color='r', linestyle='--', label='Требование 1000 msg/s по Н1.3')
    plt.xlabel('Количество участников в комнате')
    plt.ylabel('Сообщений в секунду')
    plt.title('Зависимость пропускной способности сигналов от числа участников (Н1.3)')
    plt.legend()
    plt.grid(True)
    plt.savefig('throughput.png', dpi=150)
    plt.show()
    print("График сохранён как 'throughput.png'")


if __name__ == "__main__":
    asyncio.run(main())
