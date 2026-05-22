import asyncio
import json
import time
import subprocess
import re
import matplotlib.pyplot as plt
import websockets

from test.config import SERVER_URL, ssl_context

ROOM_PREFIX = "res_test_"
ROOM_COUNT = 100
USERS_PER_ROOM = 4
ACTIVE_TIME = 180
SIGNAL_INTERVAL = 0.1


async def join_room(room_id, user_index):
    if ssl_context:
        ws = await websockets.connect(SERVER_URL, ssl=ssl_context)
    else:
        ws = await websockets.connect(SERVER_URL)
    nickname = f"user_{room_id}_{user_index}"
    await ws.send(json.dumps({
        "type": "join",
        "room": room_id,
        "nickname": nickname
    }))
    while True:
        msg = await ws.recv()
        data = json.loads(msg)
        if data.get("type") == "joined":
            return ws, data["participant_id"]


async def run_load():
    print(f"Создаём {ROOM_COUNT} комнат по {USERS_PER_ROOM} участников...")
    all_connections = []
    for rid in range(ROOM_COUNT):
        room_id = f"{ROOM_PREFIX}{rid}"
        room_users = []
        for u in range(USERS_PER_ROOM):
            ws, pid = await join_room(room_id, u)
            room_users.append((ws, pid))
            await asyncio.sleep(0.05)
        all_connections.append((room_id, room_users))
    print("Все участники подключены. Начинаем генерацию нагрузки.")
    end_time = time.time() + ACTIVE_TIME

    async def room_activity(room_id, users):
        if len(users) < 2:
            return
        sender_ws, _ = users[0]
        target_id = users[1][1]
        while time.time() < end_time:
            await sender_ws.send(json.dumps({
                "type": "signal",
                "target_id": target_id,
                "data": {"timestamp": time.time()}
            }))
            await asyncio.sleep(SIGNAL_INTERVAL)

    tasks = []
    for room_id, users in all_connections:
        tasks.append(asyncio.create_task(room_activity(room_id, users)))
    await asyncio.sleep(ACTIVE_TIME)
    for t in tasks:
        t.cancel()
    for _, users in all_connections:
        for ws, _ in users:
            await ws.close()
    print("Нагрузка завершена.")


def get_container_stats(container_name):
    try:
        output = subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}} {{.MemUsage}}",
             container_name],
            text=True
        ).strip()
        if not output:
            return 0.0, 0.0
        parts = output.split()
        if len(parts) < 2:
            return 0.0, 0.0
        cpu_str = parts[0]
        mem_str = parts[1]
        cpu = float(cpu_str.rstrip('%'))
        mem_usage = mem_str.split('/')[0].strip()
        mem_match = re.match(r"([\d.]+)(MiB|GiB)", mem_usage)
        if mem_match:
            val, unit = mem_match.groups()
            mem = float(val)
            if unit == "GiB":
                mem *= 1024
        else:
            mem = 0.0
        return cpu, mem
    except subprocess.CalledProcessError:
        return 0.0, 0.0


async def monitor_resources(duration, interval=2):
    output = subprocess.check_output(["docker", "ps", "--format", "{{.Names}}"],
                                     text=True).splitlines()
    containers = {}
    for name in output:
        if "signaling" in name:
            containers["signaling"] = name
        elif "redis" in name:
            containers["redis"] = name
    if "signaling" not in containers or "redis" not in containers:
        print("Не найдены контейнеры signaling или redis")
        return None
    print(
        f"Отслеживаем контейнеры: signaling={containers['signaling']}, redis={containers['redis']}")
    data = {
        "signaling": {"cpu": [], "mem": []},
        "redis": {"cpu": [], "mem": []}
    }
    start = time.time()
    await asyncio.sleep(1)
    while time.time() - start < duration:
        for key, cont_name in containers.items():
            cpu, mem = get_container_stats(cont_name)
            data[key]["cpu"].append(cpu)
            data[key]["mem"].append(mem)
        await asyncio.sleep(interval)
    return data


async def main():
    print("Начинаем тест ресурсов (3 минуты)...")
    monitor_task = asyncio.create_task(monitor_resources(ACTIVE_TIME, interval=2))
    load_task = asyncio.create_task(run_load())
    await load_task
    stats = await monitor_task
    if stats is None:
        return
    sig_cpu = stats["signaling"]["cpu"]
    sig_mem = stats["signaling"]["mem"]
    avg_sig_cpu = sum(sig_cpu) / len(sig_cpu) if sig_cpu else 0
    max_sig_cpu = max(sig_cpu) if sig_cpu else 0
    avg_sig_mem = sum(sig_mem) / len(sig_mem) if sig_mem else 0
    max_sig_mem = max(sig_mem) if sig_mem else 0
    print("\n=== Результаты тестирования Н5.1 и Н5.2 ===")
    print(f"Signal container: средний CPU = {avg_sig_cpu:.2f}%, макс CPU = {max_sig_cpu:.2f}%")
    print(
        f"Signal container: средняя память = {avg_sig_mem:.1f} MiB, макс память = {max_sig_mem:.1f} MiB")
    if avg_sig_cpu <= 30:
        print("Н5.2 (CPU ≤30%) – ВЫПОЛНЯЕТСЯ")
    else:
        print("Н5.2 (CPU ≤30%) – НЕ ВЫПОЛНЯЕТСЯ")
    if max_sig_mem <= 256:
        print("Н5.1 (ОЗУ сигналинга ≤256 MiB) – ВЫПОЛНЯЕТСЯ")
    else:
        print("Н5.1 (ОЗУ сигналинга ≤256 MiB) – НЕ ВЫПОЛНЯЕТСЯ")

    if not sig_cpu:
        print("Нет данных для построения графика.")
        return
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    times = list(range(0, len(sig_cpu) * 2, 2))[:len(sig_cpu)]
    ax1.plot(times, sig_cpu, label='CPU %')
    ax1.axhline(y=30, color='r', linestyle='--', label='Порог 30%')
    ax1.set_ylabel('CPU %')
    ax1.set_title('Использование CPU контейнера signaling')
    ax1.legend()
    ax1.grid(True)
    ax2.plot(times, sig_mem, label='Память (MiB)', color='orange')
    ax2.axhline(y=256, color='r', linestyle='--', label='Порог 256 MiB')
    ax2.set_ylabel('Память (MiB)')
    ax2.set_xlabel('Время (секунды)')
    ax2.set_title('Потребление ОЗУ контейнера signaling')
    ax2.legend()
    ax2.grid(True)
    plt.tight_layout()
    plt.savefig('resource_usage.png', dpi=150)
    plt.show()
    print("График сохранён как 'resource_usage.png'")


if __name__ == "__main__":
    asyncio.run(main())
