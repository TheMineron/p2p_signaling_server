import asyncio
import json
import statistics
import time

import matplotlib.pyplot as plt

from test.config import NUM_USERS_LIST, join_room

SIGNAL_COUNT = 15


async def measure_signal_latency(sender_ws, receiver_ws, target_id):
    send_time = time.perf_counter()
    await sender_ws.send(json.dumps({
        "type": "signal",
        "target_id": target_id,
        "data": {"test": "ping", "send_time": send_time}
    }))
    while True:
        resp = await receiver_ws.recv()
        data = json.loads(resp)
        if data.get("type") == "signal" and data.get("data", {}).get("test") == "ping":
            recv_time = time.perf_counter()
            return (recv_time - send_time) * 1000  # мс


async def run_test(num_users):
    print(f"Тестирование с {num_users} участниками...")
    connections = []
    ids = []
    for i in range(num_users):
        ws, pid = await join_room(i)
        connections.append(ws)
        ids.append(pid)
        await asyncio.sleep(0.1)

    delays = []
    for _ in range(SIGNAL_COUNT):
        d = await measure_signal_latency(connections[0], connections[1], ids[1])
        delays.append(d)
        await asyncio.sleep(0.2)

    for ws in connections:
        await ws.close()

    avg = statistics.mean(delays)
    std = statistics.stdev(delays) if len(delays) > 1 else 0
    print(f"  Среднее: {avg:.2f} мс, ст.откл.: {std:.2f} мс")
    return avg, std


async def main():
    results = []
    for n in NUM_USERS_LIST:
        avg, std = await run_test(n)
        results.append((n, avg, std))

    users = [r[0] for r in results]
    means = [r[1] for r in results]
    stds = [r[2] for r in results]

    plt.figure(figsize=(8, 5))
    plt.errorbar(users, means, yerr=stds, fmt='o-', capsize=5, label='Время обработки сигнала')
    plt.axhline(y=100, color='r', linestyle='--', label='Порог по Н1.1 (100 мс)')
    plt.xlabel('Количество участников в комнате')
    plt.ylabel('Время (мс)')
    plt.title('Зависимость времени обработки сигнала от числа участников')
    plt.legend()
    plt.grid(True)
    plt.savefig('signal_latency.png', dpi=150)
    plt.show()
    print("График сохранён как 'signal_latency.png'")


if __name__ == "__main__":
    asyncio.run(main())
