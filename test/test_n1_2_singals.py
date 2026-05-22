#!/usr/bin/env python3
"""
Тест Н1.2 – Пропускная способность сигнальных сообщений
Условие: не менее 5000 сообщений в секунду при 1000 участниках (100 комнат по 10 человек).
Сценарий: в каждой комнате один участник отправляет сигналы другому.
Измеряется общее количество доставленных сигналов за фиксированное время.
"""

import asyncio
import json
import ssl
import time
from collections import defaultdict
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import websockets

# ================== Конфигурация ==================
SERVER_URL = "wss://130.193.45.202:8000/ws"
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# Параметры нагрузки
NUM_ROOMS = 100              # количество комнат
USERS_PER_ROOM = 10          # участников в комнате
TOTAL_USERS = NUM_ROOMS * USERS_PER_ROOM  # 1000

# Время измерения (секунды)
TEST_DURATION = 10

# Частота отправки сигналов одним отправителем (сообщений в секунду)
# Для достижения общей пропускной способности 5000 msg/s при 100 комнатах,
# каждый отправитель должен отправлять примерно 50 msg/s.
# Установим 100 msg/s, чтобы гарантированно нагрузить сервер выше порога.
SIGNALS_PER_SECOND_PER_SENDER = 100

# Задержка между отправками в секундах
SIGNAL_INTERVAL = 1.0 / SIGNALS_PER_SECOND_PER_SENDER

# ================== Вспомогательные функции ==================
async def join_room(room_id: str, user_index: int) -> Tuple[websockets.WebSocketClientProtocol, str]:
    """Подключается к комнате, возвращает ws и participant_id."""
    ws = await websockets.connect(SERVER_URL, ssl=SSL_CONTEXT, open_timeout=10)
    await ws.send(json.dumps({
        "type": "join",
        "room": room_id,
        "nickname": f"user_{room_id}_{user_index}"
    }))
    while True:
        msg = await ws.recv()
        data = json.loads(msg)
        if data.get("type") == "joined":
            return ws, data["participant_id"]

async def run_room_test(room_id: str, users: List[Tuple[websockets.WebSocketClientProtocol, str]]):
    """
    Для одной комнаты: sender (первый участник) отправляет сигналы receiver (второй участник).
    Подсчитывает количество успешно принятых сигналов.
    Возвращает количество принятых сообщений.
    """
    sender_ws, sender_pid = users[0]
    receiver_ws, receiver_pid = users[1]
    received_count = 0
    stop_event = asyncio.Event()

    # Задача приёма сообщений у получателя
    async def receive_task():
        nonlocal received_count
        try:
            while not stop_event.is_set():
                msg = await asyncio.wait_for(receiver_ws.recv(), timeout=0.1)
                data = json.loads(msg)
                # Считаем только сигналы, адресованные получателю
                if data.get("type") == "signal" and data.get("from_id") == sender_pid:
                    received_count += 1
        except asyncio.TimeoutError:
            pass
        except websockets.exceptions.ConnectionClosed:
            pass

    # Задача отправки сигналов
    async def send_task():
        end_time = time.time() + TEST_DURATION
        seq = 0
        while time.time() < end_time:
            await sender_ws.send(json.dumps({
                "type": "signal",
                "target_id": receiver_pid,
                "data": {"seq": seq, "timestamp": time.time()}
            }))
            seq += 1
            await asyncio.sleep(SIGNAL_INTERVAL)

    recv_task = asyncio.create_task(receive_task())
    send_task_obj = asyncio.create_task(send_task())

    await send_task_obj
    stop_event.set()
    await recv_task
    return received_count

async def main():
    print(f"Создаём {NUM_ROOMS} комнат по {USERS_PER_ROOM} участников (всего {TOTAL_USERS})...")
    all_rooms = []  # [(room_id, [(ws, pid), ...])]

    # Подключаем всех участников
    for r in range(NUM_ROOMS):
        room_id = f"throughput_room_{r}"
        room_users = []
        for u in range(USERS_PER_ROOM):
            ws, pid = await join_room(room_id, u)
            room_users.append((ws, pid))
            # Небольшая задержка, чтобы не перегружать сервер подключениями
            await asyncio.sleep(0.05)
        all_rooms.append((room_id, room_users))
        print(f"Комната {room_id} подключена")

    print("Начинаем измерение пропускной способности...")
    start_time = time.time()

    # Запускаем тесты для всех комнат параллельно
    tasks = []
    for room_id, users in all_rooms:
        tasks.append(run_room_test(room_id, users))
    results = await asyncio.gather(*tasks)

    elapsed = time.time() - start_time
    total_received = sum(results)
    throughput = total_received / elapsed

    print(f"\n=== Результаты теста Н1.2 ===")
    print(f"Всего принято сигналов: {total_received}")
    print(f"Время теста: {elapsed:.2f} сек")
    print(f"Пропускная способность: {throughput:.0f} msg/s")
    if throughput >= 5000:
        print("✅ Н1.2 выполняется: пропускная способность ≥ 5000 msg/s")
    else:
        print("❌ Н1.2 НЕ выполняется: пропускная способность < 5000 msg/s")

    # Закрываем все соединения
    for _, users in all_rooms:
        for ws, _ in users:
            await ws.close()

    # Построение графика (можно также проварьировать количество участников)
    # Для простоты выведем текущий результат в виде столбца.
    plt.figure(figsize=(8, 5))
    plt.bar(["Пропускная способность"], [throughput], color='blue')
    plt.axhline(y=5000, color='r', linestyle='--', label='Порог Н1.2 (5000 msg/s)')
    plt.ylabel('Сообщений в секунду')
    plt.title('Пропускная способность сигналов (100 комнат × 10 участников)')
    plt.legend()
    plt.grid(axis='y')
    plt.savefig('n1_2_throughput.png', dpi=150)
    plt.show()
    print("График сохранён как 'n1_2_throughput.png'")

if __name__ == "__main__":
    asyncio.run(main())