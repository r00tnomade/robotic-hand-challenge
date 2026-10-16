import time
import json
import os
import threading
import queue
from datetime import datetime
from pymodbus.client import ModbusTcpClient


class HardwareLogger:
    def __init__(
        self, ip="192.168.123.211", port=6000, output_dir="data/logs", target_hz=20
    ):
        self.ip = ip
        self.port = port
        self.output_dir = output_dir
        self.target_hz = target_hz

        self.client = ModbusTcpClient(ip, port=port)
        self.running = False
        self.log_thread = None
        self.write_thread = None
        self.data_queue = queue.Queue()
        self.filepath = None

        os.makedirs(output_dir, exist_ok=True)

        self.sensor_groups = [
            ("Little Tip", 3000, 3, 3),
            ("Little Nail", 3018, 12, 8),
            ("Little Pad", 3210, 10, 8),
            ("Ring Tip", 3370, 3, 3),
            ("Ring Nail", 3388, 12, 8),
            ("Ring Pad", 3580, 10, 8),
            ("Middle Tip", 3740, 3, 3),
            ("Middle Nail", 3758, 12, 8),
            ("Middle Pad", 3950, 10, 8),
            ("Index Tip", 4110, 3, 3),
            ("Index Nail", 4128, 12, 8),
            ("Index Pad", 4320, 10, 8),
            ("Thumb Tip", 4480, 3, 3),
            ("Thumb Nail", 4498, 12, 8),
            ("Thumb Mid", 4690, 3, 3),
            ("Thumb Pad", 4708, 12, 8),
            ("Palm", 4900, 8, 14),
        ]

    def _ensure_connection(self):
        if not self.client.is_socket_open():
            try:
                self.client.close()
                return self.client.connect()
            except Exception:
                return False
        return True

    def _safe_read(self, addr, length):
        if not self._ensure_connection():
            return []

        values = []
        for i in range(0, length, 120):
            try:
                res = self.client.read_holding_registers(
                    address=addr + i, count=min(120, length - i), slave=1
                )
                if res and not res.isError():
                    values.extend(res.registers)
                else:
                    return []
            except Exception:
                return []
        return values

    def _writer_loop(self):
        """Schreibt Daten asynchron aus der Queue auf die Festplatte."""
        with open(self.filepath, "w", encoding="utf-8") as f:
            # Metadaten-Header als erste Zeile
            header = {
                "type": "metadata",
                "ip": self.ip,
                "port": self.port,
                "target_hz": self.target_hz,
                "sensors": [s[0] for s in self.sensor_groups],
                "started_at": datetime.now().isoformat(),
            }
            f.write(json.dumps(header) + "\n")

            while self.running or not self.data_queue.empty():
                try:
                    record = self.data_queue.get(timeout=0.1)
                    f.write(json.dumps(record) + "\n")
                    f.flush()
                    self.data_queue.task_done()
                except queue.Empty:
                    continue

    def _logging_loop(self, label):
        interval = 1.0 / self.target_hz

        while self.running:
            start_time = time.perf_counter()

            record = {
                "timestamp": datetime.now().isoformat(),
                "label": label,
                "joints": [],
                "sensors": {},
            }

            # Gelenkwinkel lesen
            try:
                if self._ensure_connection():
                    res_joints = self.client.read_holding_registers(
                        address=1486, count=6, slave=1
                    )
                    if res_joints and not res_joints.isError():
                        record["joints"] = res_joints.registers
            except Exception:
                pass

            # Sensoren lesen
            for name, addr, h, w in self.sensor_groups:
                data = self._safe_read(addr, h * w)
                record["sensors"][name] = data if data else [0] * (h * w)

            # In die Queue schieben (blockiert den Sensor-Loop nicht)
            self.data_queue.put(record)

            # Exaktes Timing einhalten
            elapsed = time.perf_counter() - start_time
            if elapsed < interval:
                time.sleep(interval - elapsed)

    def start_logging(self, label="grasp_session"):
        if not self._ensure_connection():
            print(
                f"HardwareLogger: Verbindungsaufbau zu {self.ip}:{self.port} fehlgeschlagen."
            )
            return False

        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = os.path.join(self.output_dir, f"{label}_{session_id}.jsonl")

        self.running = True

        # Threads starten: Einer für Modbus-Polling, einer für Festplatten-I/O
        self.write_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.log_thread = threading.Thread(
            target=self._logging_loop, args=(label,), daemon=True
        )

        self.write_thread.start()
        self.log_thread.start()

        print(f"Pro-HardwareLogger gestartet. Datei: {self.filepath}")
        return True

    def stop_logging(self):
        if not self.running:
            return
        self.running = False

        if self.log_thread:
            self.log_thread.join()
        if self.write_thread:
            self.write_thread.join()

        self.client.close()
        print("Pro-HardwareLogger sicher gestoppt.")
