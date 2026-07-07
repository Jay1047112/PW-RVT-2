#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
collect.py

負責：
1. 透過 RS422 / Modbus RTU 連接 PW-RVT
2. 收集 X/Y/Z Raw Data 與 Temp_C
3. 輸出帶時間戳的 CSV
"""

import csv
import os
import sys
import time
from datetime import datetime
from typing import Optional, List

import msvcrt
from serial.tools import list_ports
from pymodbus.client.sync import ModbusSerialClient as ModbusClient

from config import CONFIG
from utils import (
    signed_16bit,
    get_timestamp_str,
    get_timestamped_output_csv_filename,
    resolve_duration_sec,
    format_sample_time,
)


def list_serial_ports():
    ports_info = []
    for p in list_ports.comports():
        ports_info.append({
            "device": p.device,
            "description": p.description,
            "hwid": p.hwid,
        })
    return ports_info


def auto_pick_port(user_port: Optional[str]) -> str:
    ports = list_serial_ports()

    if ports:
        print("[INFO] Detected serial ports:")
        for p in ports:
            print(f"       - {p['device']} | {p['description']}")
    else:
        print("[WARN] No serial ports detected by Windows.")

    if user_port:
        print(f"[INFO] Use user-specified port: {user_port}")
        return user_port

    if not ports:
        raise RuntimeError("找不到可用的 serial port，請確認 RS422/USB 轉接器有正確連接。")

    preferred_keywords = [
        "USB SERIAL", "USB-SERIAL", "USB UART", "FTDI", "CP210", "CH340", "PROLIFIC",
    ]

    for p in ports:
        desc = (p["description"] or "").upper()
        for kw in preferred_keywords:
            if kw in desc:
                print(f"[INFO] Auto selected USB-like port: {p['device']}")
                return p["device"]

    picked = ports[0]["device"]
    print(f"[INFO] Auto selected fallback port: {picked}")
    return picked


def build_client(port: str) -> ModbusClient:
    return ModbusClient(
        method="RTU",
        port=port,
        baudrate=CONFIG["BAUDRATE"],
        bytesize=CONFIG["BYTESIZE"],
        parity=CONFIG["PARITY"],
        stopbits=CONFIG["STOPBITS"],
        timeout=CONFIG["TIMEOUT"],
    )


def convert_temperature_from_adc(raw_adc: int) -> float:
    return 1.133 * (raw_adc * 0.0078125) - 7.963


def read_temperature_c(client: ModbusClient) -> Optional[float]:
    try:
        resp = client.read_holding_registers(
            CONFIG["TEMP_REGISTER"],
            1,
            unit=CONFIG["UNIT_ID"],
        )
        if hasattr(resp, "isError") and resp.isError():
            return None
        if not hasattr(resp, "registers") or len(resp.registers) < 1:
            return None
        raw_adc = resp.registers[0]
        temp_c = convert_temperature_from_adc(raw_adc)
        return round(temp_c, 3)
    except Exception:
        return None


def save_csv(rows: List[List], output_csv: str) -> None:
    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Time", "X", "Y", "Z", "Temp_C"])
        writer.writerows(rows)


def collect_vibration_data(duration_sec: Optional[float] = None) -> Optional[str]:
    duration_sec = resolve_duration_sec(duration_sec)

    port = auto_pick_port(CONFIG["PORT"])
    target_samples = int(duration_sec * CONFIG["SAMPLE_RATE"])
    timestamp_str = get_timestamp_str()
    output_csv = get_timestamped_output_csv_filename(CONFIG["OUTPUT_CSV"], timestamp_str)

    print("=" * 70)
    print("[INFO] PW-RVT Reader Start")
    print(f"[INFO] Platform             : {sys.platform}")
    print(f"[INFO] Port                 : {port}")
    print(f"[INFO] Baudrate             : {CONFIG['BAUDRATE']}")
    print(f"[INFO] Unit ID              : {CONFIG['UNIT_ID']}")
    print(f"[INFO] Sample Rate          : {CONFIG['SAMPLE_RATE']}")
    print(f"[INFO] Duration             : {duration_sec} sec")
    print(f"[INFO] Target Samples       : {target_samples}")
    print(f"[INFO] Output CSV           : {output_csv}")
    print(f"[INFO] Timeout              : {CONFIG['TIMEOUT']}")
    print(f"[INFO] Temp Register        : 0x{CONFIG['TEMP_REGISTER']:04X}")
    print("[INFO] Press Q to quit, or Ctrl+C to stop.")
    print("=" * 70)

    client = build_client(port)
    connection = client.connect()

    if not connection:
        raise RuntimeError(
            "Modbus 連線失敗。請檢查：\n"
            "1. port 是否正確\n"
            "2. baudrate 是否正確（先試 3000000，不通再試 115200）\n"
            "3. 感測器是否有供電\n"
            "4. RS422 接線是否正確\n"
            "5. unit/slave ID 是否為 1"
        )

    print("[INFO] Modbus connected successfully.")

    rows: List[List] = []
    sample_index = 0
    last_temp_read_ts = 0.0
    current_temp_c: Optional[float] = None

    try:
        chip = client.read_input_registers(0x80, 3, unit=CONFIG["UNIT_ID"])
        if hasattr(chip, "isError") and chip.isError():
            raise RuntimeError(f"讀取 Chip ID 失敗：{chip}")
        print("[INFO] Chip ID:", ", ".join(hex(x) for x in chip.registers))

        wr = client.write_register(0x01, CONFIG["SAMPLE_RATE"], unit=CONFIG["UNIT_ID"])
        if hasattr(wr, "isError") and wr.isError():
            raise RuntimeError(f"寫入 Sample Rate 失敗：{wr}")
        print(f"[INFO] Sample Rate set to {CONFIG['SAMPLE_RATE']} Hz")

        vib_dat = client.read_input_registers(0x02, 1, unit=CONFIG["UNIT_ID"])
        if hasattr(vib_dat, "isError") and vib_dat.isError():
            raise RuntimeError(f"初次讀取 Data Length 失敗：{vib_dat}")

        prev_data_len = 0
        counter = 0
        max_size = CONFIG["MAX_AXES_GROUPS"] * 3

        print(f"[INFO] Initial Data Length : {vib_dat.registers[0]}")
        print(f"[INFO] Max Read Size       : {max_size}")

        current_temp_c = read_temperature_c(client)
        print(f"[INFO] Initial Temperature : {current_temp_c} °C")

        start_dt = datetime.now()
        print("[INFO] Start collecting samples...")

        while len(rows) < target_samples:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key in [b"q", b"Q"]:
                    print("\n[INFO] Stop requested by keyboard: Q")
                    break

            try:
                start = time.perf_counter()
                current_len = vib_dat.registers[0]

                now_ts = time.time()
                if (now_ts - last_temp_read_ts) >= CONFIG["TEMP_READ_INTERVAL_SEC"]:
                    temp_val = read_temperature_c(client)
                    if temp_val is not None:
                        current_temp_c = temp_val
                    last_temp_read_ts = now_ts

                if current_len >= max_size:
                    vib_dat = client.read_input_registers(
                        0x02,
                        max_size + 1,
                        unit=CONFIG["UNIT_ID"],
                    )
                elif current_len <= (2 * 3):
                    time.sleep(CONFIG["SHORT_DATA_SLEEP_SEC"])
                    vib_dat = client.read_input_registers(0x02, 1, unit=CONFIG["UNIT_ID"])
                    if hasattr(vib_dat, "isError") and vib_dat.isError():
                        print(f"[WARN] Read data length failed: {vib_dat}")
                        continue
                    continue
                else:
                    vib_dat = client.read_input_registers(
                        0x02,
                        current_len + 1,
                        unit=CONFIG["UNIT_ID"],
                    )

                end = time.perf_counter()

                if hasattr(vib_dat, "isError") and vib_dat.isError():
                    print(f"[WARN] Read raw data failed: {vib_dat}")
                    time.sleep(0.05)
                    continue

                counter += 1

                if len(vib_dat.registers) > 1:
                    raw_regs = vib_dat.registers[1:]
                    usable_len = (len(raw_regs) // 3) * 3

                    for i in range(0, usable_len, 3):
                        x = signed_16bit(raw_regs[i])
                        y = signed_16bit(raw_regs[i + 1])
                        z = signed_16bit(raw_regs[i + 2])

                        t_str = format_sample_time(
                            start_dt=start_dt,
                            sample_index=sample_index,
                            sample_rate=CONFIG["SAMPLE_RATE"],
                        )
                        rows.append([t_str, x, y, z, current_temp_c])
                        sample_index += 1

                        if len(rows) >= target_samples:
                            break

                if counter >= CONFIG["PRINT_EVERY_N_LOOPS"]:
                    counter = 0
                    data_len = vib_dat.registers[0]
                    delta_len = data_len - prev_data_len

                    msg = (
                        f"[INFO] ReadTime={((end - start) * 1000):8.3f} ms | "
                        f"DataLen={data_len:4d} | "
                        f"Delta={delta_len:4d} | "
                        f"Collected={len(rows)}/{target_samples} | "
                        f"Temp={current_temp_c} °C"
                    )

                    if CONFIG["PRINT_FIRST_3_AXES"] and len(vib_dat.registers) >= 4:
                        px = signed_16bit(vib_dat.registers[1])
                        py = signed_16bit(vib_dat.registers[2])
                        pz = signed_16bit(vib_dat.registers[3])
                        msg += f" | XYZ=({px}, {py}, {pz})"

                    print(msg)

                if len(rows) > 0 and len(rows) % CONFIG["PRINT_PROGRESS_EVERY_N_SAMPLES"] == 0:
                    print(f"[INFO] Progress: {len(rows)}/{target_samples} samples collected")

                prev_data_len = vib_dat.registers[0]

            except KeyboardInterrupt:
                print("\n[INFO] Stopped by user (Ctrl+C).")
                break
            except Exception as e:
                print(f"[ERROR] Loop failed: {e}")
                time.sleep(0.1)

        if rows:
            save_csv(rows, output_csv)
            print("=" * 70)
            print("[INFO] Collection finished.")
            print(f"[INFO] Total samples saved : {len(rows)}")
            print(f"[INFO] CSV saved to        : {os.path.abspath(output_csv)}")
            print("[INFO] CSV columns         : Time, X, Y, Z, Temp_C")
            print("=" * 70)
            return os.path.abspath(output_csv)

        print("[WARN] No data collected. CSV not created.")
        return None

    finally:
        try:
            client.close()
        except Exception:
            pass
        print("[INFO] Modbus connection closed.")


if __name__ == "__main__":
    collect_vibration_data()
