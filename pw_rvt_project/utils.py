#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import ctypes
from datetime import datetime, timedelta
from typing import Optional, Tuple

from config import CONFIG


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def signed_16bit(value: int) -> int:
    return ctypes.c_int16(value).value


def safe_div(a: float, b: float) -> float:
    if abs(b) < 1e-12:
        return 0.0
    return float(a / b)


def round_all_floats(obj, digits=1):
    if isinstance(obj, dict):
        return {k: round_all_floats(v, digits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_all_floats(v, digits) for v in obj]
    if isinstance(obj, float):
        return round(obj, digits)
    return obj


def get_timestamp_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_timestamped_output_csv_filename(base_filename: str, timestamp_str: str) -> str:
    base_name, ext = os.path.splitext(base_filename)
    return f"{base_name}_{timestamp_str}{ext}"


def get_analysis_paths(raw_csv_path: str) -> Tuple[str, str]:
    csv_abs = os.path.abspath(raw_csv_path)
    csv_name = os.path.basename(csv_abs)
    csv_stem, _ = os.path.splitext(csv_name)
    output_dir = os.path.join(CONFIG["ANALYSIS_ROOT_DIR"], csv_stem)
    json_name = f"{csv_stem}_features.json"
    return output_dir, json_name


def resolve_duration_sec(duration_sec: Optional[float]) -> float:
    if duration_sec is None:
        return float(CONFIG["DURATION_SEC"])
    try:
        duration_sec = float(duration_sec)
    except Exception as exc:
        raise ValueError("duration_sec 必須是數字") from exc
    if duration_sec <= 0:
        raise ValueError("duration_sec 必須大於 0")
    return duration_sec


def format_sample_time(start_dt: datetime, sample_index: int, sample_rate: int) -> str:
    dt = start_dt + timedelta(seconds=(sample_index / sample_rate))
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def task_id_from_csv_path(raw_file_path: str) -> str:
    raw_filename = os.path.basename(raw_file_path)
    raw_stem, _ = os.path.splitext(raw_filename)
    parts = raw_stem.split("_")
    if len(parts) >= 2:
        ts_part = parts[-2] + "_" + parts[-1]
        return f"task_{ts_part}"
    return f"task_{get_timestamp_str()}"
