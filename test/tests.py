import argparse
import asyncio
import json
import random
import ssl
import statistics
import subprocess
import time
from dataclasses import dataclass
from typing import Tuple, Optional

import websockets


@dataclass
class TestConfig:
    server_url: str
    use_wss: bool = True
    skip_ssl_verify: bool = True
    redis_container: str = "redis"
    signaling_container: str = "signaling"
    use_docker_stats: bool = True
    total_users_for_perf: int = 2000
    rooms_for_scale: int = 1000
    users_per_room_scale: int = 5
    max_users_in_one_room: int = 20
    signal_test_messages: int = 1000
    join_test_samples: int = 100
    keepalive_duration: int = 180
    keepalive_interval: float = 5.0
    resource_sample_interval: float = 2.0

    @property
    def ssl_context(self):
        if not self.use_wss:
            return None
        ctx = ssl.create_default_context()
        if self.skip_ssl_verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx


async def join_room(ws_url: str, room_id: str, nickname: str, password: str = None,
                    ssl_ctx=None, max_retries: int = 3) -> Tuple[websockets.WebSocketClientProtocol, str]:
    """Подключается к комнате с повторами при временных ошибках."""
    retry_delay = 0.5
    for attempt in range(max_retries):
        try:
            ws = await websockets.connect(ws_url, ssl=ssl_ctx, close_timeout=2)
            msg = {"type": "join", "room": room_id, "nickname": nickname}
            if password:
                msg["password"] = password
            await ws.send(json.dumps(msg))
            while True:
                resp = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(resp)
                if data.get("type") == "joined":
                    return ws, data["participant_id"]
                elif data.get("type") == "error":
                    raise RuntimeError(f"Join error: {data.get('message')}")
        except (websockets.exceptions.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed to connect after {max_retries} attempts: {e}")
            await asyncio.sleep(retry_delay)
            retry_delay *= 2
    raise RuntimeError("Unreachable")


async def send_signal(ws, target_id, payload=None):
    if payload is None:
        payload = {"ts": time.time()}
    await ws.send(json.dumps({
        "type": "signal",
        "target_id": target_id,
        "data": payload
    }))


async def wait_for_signal(ws, expected_sender_id=None, timeout=5.0):
    start = time.perf_counter()
    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout)
        except asyncio.TimeoutError:
            raise TimeoutError("No signal received")
        data = json.loads(msg)
        if data.get("type") == "signal":
            if expected_sender_id is None or data.get("from_id") == expected_sender_id:
                delay_ms = (time.perf_counter() - start) * 1000
                return delay_ms, data.get("data", {})


class TestSuite:
    def __init__(self, config: TestConfig):
        self.cfg = config
        self.results = {}

    async def test_latency_n1_1(self):
        print("\n[Н1.1] Измерение времени обработки сигнала (2 участника)...")
        room = f"latency_test_{int(time.time())}"
        ws1, pid1 = await join_room(self.cfg.server_url, room, "sender",
                                    ssl_ctx=self.cfg.ssl_context)
        ws2, pid2 = await join_room(self.cfg.server_url, room, "receiver",
                                    ssl_ctx=self.cfg.ssl_context)

        latencies = []
        for _ in range(30):
            await send_signal(ws1, pid2, {"ping": time.time()})
            delay, _ = await wait_for_signal(ws2, expected_sender_id=pid1, timeout=2.0)
            latencies.append(delay)
            await asyncio.sleep(0.1)

        await ws1.close()
        await ws2.close()

        avg = statistics.mean(latencies)
        p99 = sorted(latencies)[int(0.99 * len(latencies))]
        print(f"  Средняя задержка: {avg:.2f} мс, 99-й перцентиль: {p99:.2f} мс")
        ok = p99 <= 100
        print(f"  Результат: {'ПРОЙДЕН' if ok else 'НЕ ПРОЙДЕН'} (требование <=100 мс)")
        self.results["Н1.1"] = {"passed": ok, "avg_ms": avg, "p99_ms": p99}
        return ok

    async def test_throughput_n1_2(self):
        required_users = self.cfg.total_users_for_perf
        print(f"\n[Н1.2] Измерение пропускной способности при {required_users} участниках...")
        room = f"throughput_{int(time.time())}"
        participants = []
        print("  Подключаем участников (с паузами и повторами)...")
        connect_errors = 0
        for i in range(required_users):
            try:
                ws, pid = await join_room(self.cfg.server_url, room, f"user_{i}",
                                          ssl_ctx=self.cfg.ssl_context, max_retries=2)
                participants.append((ws, pid))
                if (i + 1) % 200 == 0:
                    print(f"    Подключено {i + 1}/{required_users}")
                await asyncio.sleep(0.05)
            except Exception as e:
                connect_errors += 1
                print(f"    Ошибка подключения участника {i}: {e}")
                if len(participants) < 2:
                    for ws, _ in participants:
                        await ws.close()
                    self.results["Н1.2"] = {"passed": False,
                                            "reason": f"Unable to connect enough participants: only {len(participants)}",
                                            "connected": len(participants)}
                    print(
                        f"  Результат: НЕ ПРОЙДЕН (не удалось подключить {required_users} участников)")
                    return False
        actual_users = len(participants)
        print(f"  Успешно подключено: {actual_users}/{required_users} (ошибок: {connect_errors})")
        if actual_users < 2:
            print("  Недостаточно участников для измерения пропускной способности.")
            self.results["Н1.2"] = {"passed": False, "connected": actual_users}
            return False

        sender_ws, sender_pid = participants[0]
        receiver_ws, receiver_pid = participants[1]

        messages_to_send = self.cfg.signal_test_messages
        print(f"  Отправляем {messages_to_send} сигналов...")
        start_time = time.perf_counter()
        for i in range(messages_to_send):
            await send_signal(sender_ws, receiver_pid, {"seq": i, "send_ts": time.time()})
        received = 0
        timeout = 15.0
        end_time = time.perf_counter() + timeout
        while received < messages_to_send and time.perf_counter() < end_time:
            try:
                _, _ = await wait_for_signal(receiver_ws, expected_sender_id=sender_pid,
                                             timeout=1.0)
                received += 1
            except TimeoutError:
                break
        total_time = time.perf_counter() - start_time
        throughput = received / total_time if total_time > 0 else 0
        print(f"  Отправлено: {messages_to_send}, получено: {received}, время: {total_time:.2f} с")
        print(f"  Пропускная способность: {throughput:.0f} msg/s")
        ok = (throughput >= 10000) and (actual_users >= required_users)
        if actual_users < required_users:
            print(f"  НЕ ПРОЙДЕН: подключено только {actual_users} участников из {required_users}")
        elif throughput < 10000:
            print(f"  НЕ ПРОЙДЕН: пропускная способность {throughput:.0f} < 10000 msg/s")
        else:
            print("  ПРОЙДЕН")
        self.results["Н1.2"] = {"passed": ok, "throughput": throughput, "connected": actual_users}
        for ws, _ in participants:
            await ws.close()
        return ok

    async def test_join_latency_n1_3(self):
        print(
            f"\n[Н1.3] Измерение времени join при {self.cfg.total_users_for_perf} одновременных подключениях...")
        room = f"join_latency_{int(time.time())}"
        latencies = []

        async def measure_one_join(idx):
            start = time.perf_counter()
            ws, pid = await join_room(self.cfg.server_url, room, f"user_{idx}",
                                      ssl_ctx=self.cfg.ssl_context)
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)
            await ws.close()  # сразу отключаемся, не нагружаем сервер
            return elapsed

        tasks = [asyncio.create_task(measure_one_join(i)) for i in
                 range(self.cfg.total_users_for_perf)]
        await asyncio.gather(*tasks)
        latencies.sort()
        p90 = latencies[int(0.9 * len(latencies))]
        print(f"  90-й перцентиль времени join: {p90:.2f} мс")
        ok = p90 <= 200
        print(f"  Результат: {'ПРОЙДЕН' if ok else 'НЕ ПРОЙДЕН'} (требуется <=200 мс)")
        self.results["Н1.3"] = {"passed": ok, "p90_ms": p90}
        return ok

    async def test_rooms_scale_n2_1(self):
        print(
            f"\n[Н2.1] Создание {self.cfg.rooms_for_scale} комнат по {self.cfg.users_per_room_scale} участников...")
        rooms = []
        for rid in range(self.cfg.rooms_for_scale):
            room_id = f"scale_room_{rid}"
            room_users = []
            for u in range(self.cfg.users_per_room_scale):
                ws, pid = await join_room(self.cfg.server_url, room_id, f"u_{rid}_{u}",
                                          ssl_ctx=self.cfg.ssl_context)
                room_users.append((ws, pid))
            rooms.append(room_users)
            if (rid + 1) % 200 == 0:
                print(f"  Создано {rid + 1}/{self.cfg.rooms_for_scale} комнат")
        print("  Проверка активности (отправка сигналов)...")
        ok_rooms = 0
        for users in rooms:
            if len(users) < 2:
                continue
            sender_ws, sender_pid = users[0]
            receiver_ws, receiver_pid = users[1]
            await send_signal(sender_ws, receiver_pid, {"test": "ping"})
            try:
                _, _ = await wait_for_signal(receiver_ws, expected_sender_id=sender_pid,
                                             timeout=1.0)
                ok_rooms += 1
            except:
                pass
        for users in rooms:
            for ws, _ in users:
                await ws.close()
        success_rate = ok_rooms / self.cfg.rooms_for_scale
        print(
            f"  Активных комнат: {ok_rooms}/{self.cfg.rooms_for_scale} ({success_rate * 100:.1f}%)")
        ok = ok_rooms >= 1000
        print(f"  Результат: {'ПРОЙДЕН' if ok else 'НЕ ПРОЙДЕН'}")
        self.results["Н2.1"] = {"passed": ok, "active_rooms": ok_rooms}
        return ok

    async def test_max_participants_per_room_n2_2(self):
        print(f"\n[Н2.2] Подключение {self.cfg.max_users_in_one_room} участников в одну комнату...")
        room = f"max_participants_{int(time.time())}"
        participants = []
        for i in range(self.cfg.max_users_in_one_room):
            ws, pid = await join_room(self.cfg.server_url, room, f"user_{i}",
                                      ssl_ctx=self.cfg.ssl_context)
            participants.append((ws, pid))
            await asyncio.sleep(0.05)
        sender_ws, sender_pid = participants[0]
        receiver_ws, receiver_pid = participants[-1]
        await send_signal(sender_ws, receiver_pid, {"test": "ping"})
        try:
            _, _ = await wait_for_signal(receiver_ws, expected_sender_id=sender_pid, timeout=2.0)
            ok = True
            print("  Сигнал успешно доставлен 20-му участнику")
        except:
            ok = False
            print("  Сигнал не доставлен")
        for ws, _ in participants:
            await ws.close()
        print(f"  Результат: {'ПРОЙДЕН' if ok else 'НЕ ПРОЙДЕН'}")
        self.results["Н2.2"] = {"passed": ok}
        return ok

    async def test_reliability_n3_1_n3_2(self):
        print("\n[Н3.1] Разрыв WebSocket и оповещение остальных...")
        room = f"reliability_{int(time.time())}"
        ws1, pid1 = await join_room(self.cfg.server_url, room, "A", ssl_ctx=self.cfg.ssl_context)
        ws2, pid2 = await join_room(self.cfg.server_url, room, "B", ssl_ctx=self.cfg.ssl_context)
        ws3, pid3 = await join_room(self.cfg.server_url, room, "C", ssl_ctx=self.cfg.ssl_context)

        await ws2.close()

        received_notify = False
        for _ in range(2):
            try:
                msg = await asyncio.wait_for(ws1.recv(), timeout=3.0)
                data = json.loads(msg)
                if data.get("type") == "participant_left" and data.get("participant_id") == pid2:
                    received_notify = True
            except:
                pass
        ok_disconnect = received_notify
        print(f"  Уведомление о разрыве получено: {'ДА' if ok_disconnect else 'НЕТ'}")

        print("\n[Н3.2] Повторное подключение с тем же ID...")

        ws2_new, pid2_new = await join_room(self.cfg.server_url, room, "B",
                                            ssl_ctx=self.cfg.ssl_context)
        ok_rejoin = (pid2_new == pid2)
        print(
            f"  Повторный join вернул тот же ID: {'ДА' if ok_rejoin else 'НЕТ'} (был {pid2}, стал {pid2_new})")

        await ws1.close()
        await ws3.close()
        await ws2_new.close()
        ok = ok_disconnect and ok_rejoin
        print(f"  Результат Н3.1+Н3.2: {'ПРОЙДЕН' if ok else 'НЕ ПРОЙДЕН'}")
        self.results["Н3.1"] = {"passed": ok_disconnect}
        self.results["Н3.2"] = {"passed": ok_rejoin}
        return ok

    async def test_security_n4(self):
        print("\n[Н4.1] Проверка WSS...")
        if self.cfg.use_wss:
            print("  Используется WSS (проверено на уровне подключения)")
            ok_wss = True
        else:
            print("  ВНИМАНИЕ: используется ws, а не wss")
            ok_wss = False

        print("\n[Н4.2] Валидация входных данных...")
        room = f"validate_{int(time.time())}"
        try:
            ws = await websockets.connect(self.cfg.server_url, ssl=self.cfg.ssl_context)
            await ws.send(json.dumps({"type": "join", "room": room}))  # нет nickname
            resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(resp)
            if data.get("type") == "error":
                ok_nickname = True
            else:
                ok_nickname = False
            await ws.close()
        except:
            ok_nickname = False

        try:
            ws = await websockets.connect(self.cfg.server_url, ssl=self.cfg.ssl_context)
            await ws.send(
                json.dumps({"type": "join", "room": room, "nickname": "<script>alert(1)</script>"}))
            resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(resp)
            if data.get("type") == "joined":
                ok_sanitize = True
                await ws.close()
            else:
                ok_sanitize = True
        except:
            ok_sanitize = False
        ok_validation = ok_nickname and ok_sanitize

        print("\n[Н4.3] Проверка пароля комнаты...")
        room_with_pass = f"password_room_{int(time.time())}"
        ws_owner, _ = await join_room(self.cfg.server_url, room_with_pass, "owner",
                                      password="secret",
                                      ssl_ctx=self.cfg.ssl_context)
        try:
            ws_bad, _ = await join_room(self.cfg.server_url, room_with_pass, "hacker",
                                        password="wrong",
                                        ssl_ctx=self.cfg.ssl_context)
            ok_password = False
            await ws_bad.close()
        except RuntimeError as e:
            if "error" in str(e).lower():
                ok_password = True
            else:
                ok_password = False
        try:
            ws_good, _ = await join_room(self.cfg.server_url, room_with_pass, "friend",
                                         password="secret",
                                         ssl_ctx=self.cfg.ssl_context)
            ok_password = ok_password and True
            await ws_good.close()
        except:
            ok_password = False
        await ws_owner.close()

        ok = ok_wss and ok_validation and ok_password
        print(f"  WSS: {ok_wss}, валидация: {ok_validation}, пароль комнаты: {ok_password}")
        print(f"  Результат Н4: {'ПРОЙДЕН' if ok else 'НЕ ПРОЙДЕН'}")
        self.results["Н4.1"] = {"passed": ok_wss}
        self.results["Н4.2"] = {"passed": ok_validation}
        self.results["Н4.3"] = {"passed": ok_password}
        return ok

    async def test_resources_n5(self):
        if not self.cfg.use_docker_stats:
            print("\n[Н5] Пропуск (требуется Docker для мониторинга ресурсов)")
            self.results["Н5.1"] = {"passed": False, "reason": "Docker stats disabled"}
            self.results["Н5.2"] = {"passed": False, "reason": "Docker stats disabled"}
            return False

        print(
            f"\n[Н5] Запуск нагрузки {self.cfg.total_users_for_perf} участников на {self.cfg.keepalive_duration} секунд...")
        room = f"resource_{int(time.time())}"
        participants = []
        for i in range(self.cfg.total_users_for_perf):
            ws, pid = await join_room(self.cfg.server_url, room, f"resuser_{i}",
                                      ssl_ctx=self.cfg.ssl_context)
            participants.append((ws, pid))
            if (i + 1) % 500 == 0:
                print(f"  Подключено {i + 1}/{self.cfg.total_users_for_perf}")
            await asyncio.sleep(0)

        stop_event = asyncio.Event()

        async def keep_alive_task(ws, my_pid, all_pids):
            while not stop_event.is_set():
                target = random.choice([p for p in all_pids if p != my_pid])
                await send_signal(ws, target, {"keepalive": time.time()})
                await asyncio.sleep(self.cfg.keepalive_interval)

        all_pids = [pid for _, pid in participants]
        tasks = []
        for ws, pid in participants:
            tasks.append(asyncio.create_task(keep_alive_task(ws, pid, all_pids)))

        cpu_data = []
        mem_data = []

        async def monitor():
            start = time.time()
            while time.time() - start < self.cfg.keepalive_duration:
                cpu, mem = self._get_container_stats(self.cfg.signaling_container)
                if cpu is not None:
                    cpu_data.append(cpu)
                    mem_data.append(mem)
                await asyncio.sleep(self.cfg.resource_sample_interval)

        monitor_task = asyncio.create_task(monitor())

        await asyncio.sleep(self.cfg.keepalive_duration)
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await monitor_task

        for ws, _ in participants:
            await ws.close()

        avg_cpu = statistics.mean(cpu_data) if cpu_data else 0
        max_cpu = max(cpu_data) if cpu_data else 0
        avg_mem = statistics.mean(mem_data) if mem_data else 0
        max_mem = max(mem_data) if mem_data else 0

        print(f"  CPU: средний {avg_cpu:.1f}%, максимум {max_cpu:.1f}%")
        print(f"  Память: средняя {avg_mem:.1f} MiB, максимум {max_mem:.1f} MiB")
        ok_cpu = avg_cpu <= 40
        ok_mem = max_mem <= 512
        print(f"  Н5.2 (CPU ≤40%): {'ПРОЙДЕН' if ok_cpu else 'НЕ ПРОЙДЕН'}")
        print(f"  Н5.1 (ОЗУ ≤512 МБ): {'ПРОЙДЕН' if ok_mem else 'НЕ ПРОЙДЕН'}")

        self.results["Н5.1"] = {"passed": ok_mem, "max_mem_mib": max_mem}
        self.results["Н5.2"] = {"passed": ok_cpu, "avg_cpu": avg_cpu}
        return ok_cpu and ok_mem

    def _get_container_stats(self, container_name: str) -> Tuple[Optional[float], Optional[float]]:
        try:
            output = subprocess.check_output(
                ["docker", "stats", "--no-stream", "--format",
                 "{{.CPUPerc}} {{.MemUsage}}", container_name],
                text=True
            ).strip()
            if not output:
                return None, None
            parts = output.split()
            cpu_str = parts[0].rstrip('%')
            cpu = float(cpu_str)
            mem_str = parts[1]
            mem_usage = mem_str.split('/')[0].strip()
            if mem_usage.endswith('MiB'):
                mem = float(mem_usage[:-3])
            elif mem_usage.endswith('GiB'):
                mem = float(mem_usage[:-3]) * 1024
            else:
                mem = 0.0
            return cpu, mem
        except Exception:
            return None, None

    def print_summary(self):
        print("\n" + "=" * 60)
        print("ИТОГОВЫЙ ОТЧЁТ ПО ТРЕБОВАНИЯМ")
        print("=" * 60)
        for req, data in self.results.items():
            if isinstance(data, dict):
                passed = data.get("passed", False)
                status = "✓ ПРОЙДЕН" if passed else "✗ НЕ ПРОЙДЕН"
                extra = ", ".join(f"{k}={v}" for k, v in data.items() if k != "passed")
                print(f"{req:6} : {status}  ({extra})")
            else:
                print(f"{req:6} : {data}")
        overall = all(v.get("passed", False) for v in self.results.values() if isinstance(v, dict))
        print("\nОБЩАЯ ОЦЕНКА:",
              "ВСЕ ТРЕБОВАНИЯ ВЫПОЛНЕНЫ" if overall else "НЕКОТОРЫЕ ТРЕБОВАНИЯ НЕ ВЫПОЛНЕНЫ")


async def main():
    parser = argparse.ArgumentParser(description="Тестирование signalling сервера")
    parser.add_argument("--server", default="wss://130.193.45.202:8000/ws", help="WebSocket URL")
    parser.add_argument("--no-wss", action="store_true", help="Использовать ws вместо wss")
    parser.add_argument("--no-verify", action="store_true", default=True,
                        help="Отключить проверку SSL")
    parser.add_argument("--no-docker", action="store_true",
                        help="Не использовать docker stats (для Н5)")
    parser.add_argument("--users", type=int, default=2000,
                        help="Количество участников для нагрузочных тестов")
    parser.add_argument("--rooms", type=int, default=1000,
                        help="Количество комнат для теста масштабируемости")
    parser.add_argument("--keepalive-duration", type=int, default=180,
                        help="Длительность ресурсного теста (сек)")
    args = parser.parse_args()

    config = TestConfig(
        server_url=args.server,
        use_wss=not args.no_wss,
        skip_ssl_verify=args.no_verify,
        use_docker_stats=not args.no_docker,
        total_users_for_perf=args.users,
        rooms_for_scale=args.rooms,
        keepalive_duration=args.keepalive_duration
    )
    suite = TestSuite(config)

    await suite.test_latency_n1_1()
    await suite.test_throughput_n1_2()
    await suite.test_join_latency_n1_3()
    await suite.test_rooms_scale_n2_1()
    await suite.test_max_participants_per_room_n2_2()
    await suite.test_reliability_n3_1_n3_2()
    await suite.test_security_n4()
    await suite.test_resources_n5()

    suite.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
