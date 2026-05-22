import asyncio
import json
import ssl
import statistics
import time
from typing import List, Tuple

import matplotlib.pyplot as plt
import websockets

SERVER_URL = "wss://130.193.45.202:8000/ws"
ROOM_ID = "n1_1_signal_test_room"
NICKNAME_BASE = "user_"

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

NUM_USERS_RANGE = range(2, 21)
SAMPLES_PER_N = 20
DELAY_BETWEEN_SAMPLES = 0.2
CONNECT_DELAY = 0.1


async def join_room(user_id: int) -> Tuple[websockets.WebSocketClientProtocol, str]:
    ws = await websockets.connect(SERVER_URL, ssl=SSL_CONTEXT)
    await ws.send(json.dumps({
        "type": "join",
        "room": ROOM_ID,
        "nickname": f"{NICKNAME_BASE}{user_id}"
    }))
    while True:
        msg = await ws.recv()
        data = json.loads(msg)
        if data.get("type") == "joined":
            return ws, data["participant_id"]


async def measure_signal_latency(sender_ws, receiver_ws, target_id: str) -> float:
    send_time = time.perf_counter()
    await sender_ws.send(json.dumps({
        "type": "signal",
        "target_id": target_id,
        "data": {"test": "n1_1_ping", "send_time": send_time}
    }))
    while True:
        resp = await receiver_ws.recv()
        data = json.loads(resp)
        if (data.get("type") == "signal" and
                data.get("data", {}).get("test") == "n1_1_ping"):
            recv_time = time.perf_counter()
            return (recv_time - send_time) * 1000


async def run_test_for_n(num_users: int) -> Tuple[float, float, List[float]]:
    print(f"Тестируем {num_users} участников...")
    connections = []
    participant_ids = []

    for i in range(num_users):
        ws, pid = await join_room(i)
        connections.append(ws)
        participant_ids.append(pid)
        await asyncio.sleep(CONNECT_DELAY)

    for ws in connections:
        try:
            while True:
                await asyncio.wait_for(ws.recv(), timeout=0.05)
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            pass

    sender = connections[0]
    receiver = connections[1]
    target_id = participant_ids[1]

    delays = []
    for _ in range(SAMPLES_PER_N):
        delay = await measure_signal_latency(sender, receiver, target_id)
        delays.append(delay)
        await asyncio.sleep(DELAY_BETWEEN_SAMPLES)

    for ws in connections:
        await ws.close()

    avg = statistics.mean(delays)
    stdev = statistics.stdev(delays) if len(delays) > 1 else 0.0
    print(f"  Средняя задержка: {avg:.2f} мс, стд: {stdev:.2f} мс, макс: {max(delays):.2f} мс")
    return avg, stdev, delays


async def main():
    results = []

    for n in NUM_USERS_RANGE:
        mean, stdev, _ = await run_test_for_n(n)
        results.append((n, mean, stdev))

    print("\n=== Результаты теста Н1.1 ===")
    print("Кол-во участников | Средняя задержка (мс) | Стандартное отклонение")
    for n, mean, stdev in results:
        print(f"{n:^17} | {mean:20.2f} | {stdev:22.2f}")

    max_mean = max(mean for _, mean, _ in results)
    if max_mean <= 100:
        print(f"\n✅ Н1.1 выполняется: максимальная средняя задержка = {max_mean:.2f} мс (≤100 мс)")
    else:
        print(
            f"\n❌ Н1.1 НЕ выполняется: максимальная средняя задержка = {max_mean:.2f} мс (>100 мс)")

    users = [r[0] for r in results]
    means = [r[1] for r in results]
    stds = [r[2] for r in results]

    plt.figure(figsize=(10, 6))
    plt.errorbar(users, means, yerr=stds, fmt='o-', capsize=5,
                 label='Время обработки сигнала (среднее ± стд)')
    plt.axhline(y=100, color='r', linestyle='--', linewidth=2,
                label='Порог по Н1.1 (100 мс)')
    plt.xlabel('Количество участников в комнате')
    plt.ylabel('Задержка (мс)')
    plt.title('Зависимость времени обработки сигнального сообщения от числа участников')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('n1_1_signal_latency.png', dpi=150)
    plt.show()
    print("График сохранён как 'n1_1_signal_latency.png'")


if __name__ == "__main__":
    asyncio.run(main())
