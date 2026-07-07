#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
plot_feature_trend.py

MCP-ready feature trend plotting module for PW-RVT vibration data.

設計重點：
1. 固定同一個 measurement point，不再做 P1 / P2 / P3 多位置比較。
2. 單筆 task_id / CSV：使用 sliding window 計算 feature trend，並以 X/Y/Z 三軸三條線畫在同一張圖。
3. 多筆 task_id / 時間區間：每筆 task 取一次完整 CSV 的 feature summary，依 timestamp 畫 historical trend。
4. 可直接被 mcp_server.py 匯入與呼叫。

主要輸出：
- 單筆：4 張圖（RMS, Kurtosis, PeakToPeak, FreqCentroid），每張圖包含 X/Y/Z 三條線。
- 多筆：4 張 historical trend 圖，每張圖包含 X/Y/Z 三條線，X 軸為 measurement timestamp。
- 對應 CSV 表格，方便後續報告或 Labu 顯示。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import CONFIG
from utils import ensure_dir, safe_div
from database import (
    get_csv_path_by_task_id,
    query_feature_records,
    update_feature_json,
)
from analyze_vibration import analyze_vibration_csv, compute_fft


AXES = ["X", "Y", "Z"]
DEFAULT_FEATURES = ["RMS", "Kurtosis", "PeakToPeak", "FreqCentroid"]

FEATURE_SETTINGS: Dict[str, Dict[str, str]] = {
    "RMS": {
        "column_suffix": "RMS_g",
        "ylabel": "RMS (g)",
        "title": "RMS",
        "filename": "RMS",
    },
    "Kurtosis": {
        "column_suffix": "Kurtosis",
        "ylabel": "Kurtosis",
        "title": "Kurtosis",
        "filename": "Kurtosis",
    },
    "PeakToPeak": {
        "column_suffix": "PeakToPeak_g",
        "ylabel": "Peak-to-Peak (g)",
        "title": "Peak-to-Peak",
        "filename": "PeakToPeak",
    },
    "FreqCentroid": {
        "column_suffix": "FreqCentroid_Hz",
        "ylabel": "Frequency Centroid (Hz)",
        "title": "Frequency Centroid",
        "filename": "FreqCentroid",
    },
}


# =========================================================
# 1. Feature calculation helpers
# =========================================================

def calc_kurtosis(x: np.ndarray) -> float:
    """對齊 analyze_vibration.py / main.py 的 Kurtosis 計算方式。"""
    x = np.asarray(x, dtype=np.float64)
    if len(x) == 0:
        return 0.0
    mu = np.mean(x)
    sigma = np.std(x, ddof=0)
    if sigma < 1e-12:
        return 0.0
    return float(np.mean(((x - mu) / sigma) ** 4))


def calc_freq_centroid(signal: np.ndarray, sample_rate: int) -> float:
    """FreqCentroid = sum(freqs * amplitude) / sum(amplitude)."""
    freqs, amplitude, _ = compute_fft(signal, sample_rate)
    if len(freqs) == 0:
        return 0.0
    return safe_div(float(np.sum(freqs * amplitude)), float(np.sum(amplitude)))


def calc_window_features(signal_g: np.ndarray, sample_rate: int) -> Dict[str, float]:
    """計算單一 sliding window 內的 features。signal_g 單位必須已是 g。"""
    signal_g = np.asarray(signal_g, dtype=np.float64)
    if len(signal_g) == 0:
        return {feature: 0.0 for feature in DEFAULT_FEATURES}

    return {
        "RMS": float(np.sqrt(np.mean(signal_g ** 2))),
        "Kurtosis": calc_kurtosis(signal_g),
        "PeakToPeak": float(np.max(signal_g) - np.min(signal_g)),
        "FreqCentroid": calc_freq_centroid(signal_g, sample_rate),
    }


def _normalize_feature_names(feature_names: Optional[Sequence[str] | str]) -> List[str]:
    if feature_names is None:
        return list(DEFAULT_FEATURES)
    if isinstance(feature_names, str):
        names = [x.strip() for x in feature_names.split(",") if x.strip()]
    else:
        names = [str(x).strip() for x in feature_names if str(x).strip()]

    invalid = [x for x in names if x not in FEATURE_SETTINGS]
    if invalid:
        raise ValueError(f"不支援的 feature_names：{invalid}，可用：{list(FEATURE_SETTINGS.keys())}")
    return names


def _get_time_label(start: int, end: int, window_size: int, sample_rate: int, mode: str) -> float:
    if mode == "start":
        return start / sample_rate
    if mode == "center":
        return (start + window_size / 2) / sample_rate
    if mode == "end":
        return end / sample_rate
    raise ValueError("TIME_LABEL_MODE 只能是 'start'、'center' 或 'end'")


def _feature_value(feature_json: Dict[str, Any], axis: str, feature_name: str) -> Optional[float]:
    try:
        value = feature_json["features"][axis][feature_name]
        return float(value)
    except Exception:
        return None


# =========================================================
# 2. CSV loading and single-task sliding trend
# =========================================================

def load_raw_csv_as_g(csv_path: str) -> Tuple[pd.DataFrame, Dict[str, np.ndarray]]:
    """讀取 PW-RVT raw CSV，並將 X/Y/Z raw count 轉為 g。"""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"找不到 CSV 檔案：{csv_path}")

    df = pd.read_csv(csv_path)
    required_cols = ["X", "Y", "Z"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"CSV 缺少必要欄位：{missing}")

    count_per_g = float(CONFIG["COUNT_PER_G"])
    signals = {
        "X": df["X"].to_numpy(dtype=np.float64) / count_per_g,
        "Y": df["Y"].to_numpy(dtype=np.float64) / count_per_g,
        "Z": df["Z"].to_numpy(dtype=np.float64) / count_per_g,
    }
    return df, signals


def build_sliding_feature_table_for_csv(
    csv_path: str,
    window_sec: float = 1.0,
    step_sec: float = 0.1,
    time_label_mode: str = "start",
) -> pd.DataFrame:
    """
    單一 CSV 的 sliding feature table。

    輸出欄位：
    - time_sec
    - X_RMS_g, Y_RMS_g, Z_RMS_g
    - X_Kurtosis, ...
    - X_PeakToPeak_g, ...
    - X_FreqCentroid_Hz, ...
    """
    sample_rate = int(CONFIG["SAMPLE_RATE"])
    window_size = int(float(window_sec) * sample_rate)
    step_size = int(float(step_sec) * sample_rate)

    if window_size <= 0:
        raise ValueError("window_sec 太小，造成 window_size <= 0")
    if step_size <= 0:
        raise ValueError("step_sec 太小，造成 step_size <= 0")

    df, signals = load_raw_csv_as_g(csv_path)
    n = len(df)
    if n < window_size:
        raise ValueError(
            f"CSV 資料長度不足，目前 {n} 筆，但 window_sec={window_sec} 需要 {window_size} 筆。"
        )

    rows: List[Dict[str, float]] = []
    for start in range(0, n - window_size + 1, step_size):
        end = start + window_size
        row: Dict[str, float] = {
            "time_sec": _get_time_label(start, end, window_size, sample_rate, time_label_mode)
        }
        for axis_name, signal in signals.items():
            feat = calc_window_features(signal[start:end], sample_rate)
            row[f"{axis_name}_RMS_g"] = feat["RMS"]
            row[f"{axis_name}_Kurtosis"] = feat["Kurtosis"]
            row[f"{axis_name}_PeakToPeak_g"] = feat["PeakToPeak"]
            row[f"{axis_name}_FreqCentroid_Hz"] = feat["FreqCentroid"]
        rows.append(row)

    trend_df = pd.DataFrame(rows)
    numeric_cols = trend_df.select_dtypes(include=[np.number]).columns
    trend_df[numeric_cols] = trend_df[numeric_cols].round(int(CONFIG["ROUND_DIGITS"]))
    return trend_df


def plot_single_task_axis_lines(
    trend_df: pd.DataFrame,
    feature_name: str,
    output_dir: str,
    title_prefix: str = "Single Task",
) -> str:
    """
    單筆資料圖：同一張圖上用三條線表示 X/Y/Z 三軸。
    """
    settings = FEATURE_SETTINGS[feature_name]
    suffix = settings["column_suffix"]

    ensure_dir(output_dir)
    plt.figure(figsize=(12, 5))
    for axis_name in AXES:
        col = f"{axis_name}_{suffix}"
        if col in trend_df.columns:
            plt.plot(trend_df["time_sec"], trend_df[col], label=f"{axis_name}-axis")

    plt.xlabel("Time (s)")
    plt.ylabel(settings["ylabel"])
    plt.title(f"{title_prefix} - {settings['title']} Trend")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    output_path = os.path.join(output_dir, f"single_task_{settings['filename']}_XYZ_trend.png")
    plt.savefig(output_path, dpi=300)
    plt.close()
    return os.path.abspath(output_path)


def generate_single_task_feature_trend_plots(
    task_id: Optional[str] = None,
    csv_path: Optional[str] = None,
    feature_names: Optional[Sequence[str] | str] = None,
    output_dir: Optional[str] = None,
    window_sec: float = 1.0,
    step_sec: float = 0.1,
    time_label_mode: str = "start",
) -> Dict[str, Any]:
    """
    單筆 task_id / CSV：產生 sliding window feature trend plots。
    每張圖都是 X/Y/Z 三條線。
    """
    if not csv_path:
        if not task_id:
            raise ValueError("task_id 與 csv_path 至少需要提供一個。")
        csv_path = get_csv_path_by_task_id(task_id)

    feature_names_list = _normalize_feature_names(feature_names)
    csv_stem = os.path.splitext(os.path.basename(csv_path))[0]
    output_dir = output_dir or os.path.join(CONFIG["ANALYSIS_ROOT_DIR"], csv_stem, "feature_trend")
    ensure_dir(output_dir)

    trend_df = build_sliding_feature_table_for_csv(
        csv_path=csv_path,
        window_sec=window_sec,
        step_sec=step_sec,
        time_label_mode=time_label_mode,
    )

    trend_csv = os.path.join(output_dir, "single_task_feature_trend.csv")
    trend_df.to_csv(trend_csv, index=False, encoding="utf-8-sig")

    title_prefix = task_id or csv_stem
    plot_paths = {
        feature_name: plot_single_task_axis_lines(
            trend_df=trend_df,
            feature_name=feature_name,
            output_dir=output_dir,
            title_prefix=title_prefix,
        )
        for feature_name in feature_names_list
    }

    return {
        "status": "success",
        "mode": "single_task_sliding_window",
        "task_id": task_id,
        "csv_path": os.path.abspath(csv_path),
        "window_sec": window_sec,
        "step_sec": step_sec,
        "trend_csv": os.path.abspath(trend_csv),
        "plot_paths": plot_paths,
    }


# =========================================================
# 3. Multi-task historical trend
# =========================================================

def _ensure_features_for_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    確保 record 有 features。
    若 PostgreSQL 尚未存 JSON feature content，會讀取 CSV 並分析後更新回 PostgreSQL。
    """
    task_id = record.get("task_id")
    features = record.get("features") or record.get("json_feature_content")
    if isinstance(features, dict) and features.get("features"):
        return features

    csv_path = record.get("raw_file_path") or record.get("csv_local_path")
    if not csv_path and task_id:
        csv_path = get_csv_path_by_task_id(task_id)
    if not csv_path:
        raise ValueError(f"record 缺少 CSV path，task_id={task_id}")

    _, features = analyze_vibration_csv(csv_path, write_json=True)
    if task_id:
        update_feature_json(task_id, features)
    return features


def build_historical_feature_table(
    records: Sequence[Dict[str, Any]],
    feature_names: Optional[Sequence[str] | str] = None,
) -> pd.DataFrame:
    """
    多筆 task 的 historical feature table。
    每一筆 task、每一個 axis、每一個 feature 會形成一列。
    """
    feature_names_list = _normalize_feature_names(feature_names)
    rows: List[Dict[str, Any]] = []

    for rec in records:
        task_id = rec.get("task_id")
        timestamp = rec.get("timestamp") or rec.get("measurement_time")
        features = _ensure_features_for_record(dict(rec))

        for axis_name in AXES:
            for feature_name in feature_names_list:
                value = _feature_value(features, axis_name, feature_name)
                if value is None:
                    continue
                rows.append({
                    "task_id": task_id,
                    "timestamp": timestamp,
                    "axis": axis_name,
                    "feature_name": feature_name,
                    "value": value,
                })

    table = pd.DataFrame(rows)
    if not table.empty:
        table["timestamp"] = pd.to_datetime(table["timestamp"])
        table = table.sort_values(["timestamp", "feature_name", "axis"])
        table["value"] = table["value"].round(int(CONFIG["ROUND_DIGITS"]))
    return table


def plot_historical_feature_xyz_lines(
    trend_df: pd.DataFrame,
    feature_name: str,
    output_dir: str,
) -> str:
    """
    多筆資料圖：X 軸為 measurement timestamp，三條線代表 X/Y/Z axis。
    """
    if trend_df.empty:
        raise ValueError("沒有可繪製的 historical trend data。")

    settings = FEATURE_SETTINGS[feature_name]
    feature_df = trend_df[trend_df["feature_name"] == feature_name].copy()
    if feature_df.empty:
        raise ValueError(f"沒有 feature={feature_name} 的資料。")

    ensure_dir(output_dir)
    plt.figure(figsize=(12, 5))

    for axis_name in AXES:
        axis_df = feature_df[feature_df["axis"] == axis_name].sort_values("timestamp")
        if axis_df.empty:
            continue
        plt.plot(axis_df["timestamp"], axis_df["value"], marker="o", label=f"{axis_name}-axis")

    plt.xlabel("Measurement Time")
    plt.ylabel(settings["ylabel"])
    plt.title(f"Historical {settings['title']} Trend")
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=30)
    plt.tight_layout()

    output_path = os.path.join(output_dir, f"historical_{settings['filename']}_XYZ_trend.png")
    plt.savefig(output_path, dpi=300)
    plt.close()
    return os.path.abspath(output_path)


def generate_historical_feature_trend_plots(
    records: Sequence[Dict[str, Any]],
    feature_names: Optional[Sequence[str] | str] = None,
    output_dir: str = "analysis_output/trends",
) -> Dict[str, Any]:
    """
    多筆 task：使用每筆 task 的完整 feature summary 畫 historical trend。
    這是固定 measurement point 情境下，最適合用來看日/週/月變化的呈現方式。
    """
    feature_names_list = _normalize_feature_names(feature_names)
    ensure_dir(output_dir)

    trend_df = build_historical_feature_table(records, feature_names_list)
    if trend_df.empty:
        return {"status": "empty", "message": "No feature records found.", "task_count": 0}

    trend_csv = os.path.join(output_dir, "historical_feature_trend_table.csv")
    trend_df.to_csv(trend_csv, index=False, encoding="utf-8-sig")

    plot_paths = {
        feature_name: plot_historical_feature_xyz_lines(trend_df, feature_name, output_dir)
        for feature_name in feature_names_list
    }

    summary: Dict[str, Any] = {}
    for feature_name in feature_names_list:
        feature_df = trend_df[trend_df["feature_name"] == feature_name]
        summary[feature_name] = {
            "max": float(feature_df["value"].max()),
            "min": float(feature_df["value"].min()),
            "mean": float(feature_df["value"].mean()),
            "max_axis": str(feature_df.loc[feature_df["value"].idxmax(), "axis"]),
            "max_task_id": str(feature_df.loc[feature_df["value"].idxmax(), "task_id"]),
            "max_timestamp": str(feature_df.loc[feature_df["value"].idxmax(), "timestamp"]),
        }

    task_ids = sorted({str(x) for x in trend_df["task_id"].dropna().unique()})
    return {
        "status": "success",
        "mode": "historical_task_summary",
        "task_count": len(task_ids),
        "task_ids": task_ids,
        "trend_csv": os.path.abspath(trend_csv),
        "plot_paths": plot_paths,
        "summary": summary,
    }


# =========================================================
# 4. MCP-facing functions
# =========================================================

def analyze_feature_trend_by_task_ids(
    task_ids: Sequence[str] | str,
    feature_names: Optional[Sequence[str] | str] = None,
    output_dir: str = "analysis_output/trends",
    window_sec: float = 1.0,
    step_sec: float = 0.1,
) -> Dict[str, Any]:
    """
    MCP tool 可直接呼叫的 task_id 版本。

    - 1 個 task_id：回傳 sliding-window trend plots。
    - 多個 task_id：回傳 historical trend plots。
    """
    if isinstance(task_ids, str):
        task_id_list = [x.strip() for x in task_ids.split(",") if x.strip()]
    else:
        task_id_list = [str(x).strip() for x in task_ids if str(x).strip()]

    if not task_id_list:
        raise ValueError("task_ids 不可為空。")

    if len(task_id_list) == 1:
        return generate_single_task_feature_trend_plots(
            task_id=task_id_list[0],
            feature_names=feature_names,
            output_dir=output_dir,
            window_sec=window_sec,
            step_sec=step_sec,
        )

    records = query_feature_records()
    record_map = {rec.get("task_id"): rec for rec in records}
    selected_records = []
    missing = []
    for task_id in task_id_list:
        rec = record_map.get(task_id)
        if rec is None:
            missing.append(task_id)
        else:
            selected_records.append(rec)

    if missing:
        raise ValueError(f"找不到以下 task_id：{missing}")

    return generate_historical_feature_trend_plots(
        records=selected_records,
        feature_names=feature_names,
        output_dir=output_dir,
    )


def analyze_vibration_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    axis: Optional[str] = None,
    feature_name: Optional[str] = None,
    feature_names: Optional[Sequence[str] | str] = None,
    aggregation_method: str = "all",
    output_dir: str = "analysis_output/trends",
) -> Dict[str, Any]:
    """
    MCP tool 可直接呼叫的時間區間版本。

    注意：
    - axis 參數保留向下相容，但新圖表預設會同時畫 X/Y/Z 三軸。
    - feature_name 保留向下相容；若 feature_names 未提供，會使用 feature_name。
    - aggregation_method 目前保留給 MCP / Labu 介面使用，實際輸出會提供 max/min/mean summary。
    """
    if feature_names is None and feature_name:
        feature_names = [feature_name]
    feature_names_list = _normalize_feature_names(feature_names)

    records = query_feature_records(start_date=start_date, end_date=end_date)
    if not records:
        return {"status": "empty", "message": "No task records found.", "task_count": 0}

    result = generate_historical_feature_trend_plots(
        records=records,
        feature_names=feature_names_list,
        output_dir=output_dir,
    )
    result["start_date"] = start_date
    result["end_date"] = end_date
    result["aggregation_method"] = aggregation_method
    if axis:
        result["note"] = "axis parameter is accepted for compatibility, but plots include X/Y/Z axes together."
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate PW-RVT feature trend plots for MCP workflow.")
    parser.add_argument("--task-ids", default=None, help="Single task_id or comma-separated task_id list.")
    parser.add_argument("--start-date", default=None, help="Start date for historical trend query.")
    parser.add_argument("--end-date", default=None, help="End date for historical trend query.")
    parser.add_argument("--features", default=",".join(DEFAULT_FEATURES), help="Comma-separated features.")
    parser.add_argument("--output-dir", default="analysis_output/trends")
    parser.add_argument("--window-sec", type=float, default=1.0)
    parser.add_argument("--step-sec", type=float, default=0.1)
    args = parser.parse_args()

    if args.task_ids:
        print(analyze_feature_trend_by_task_ids(
            task_ids=args.task_ids,
            feature_names=args.features,
            output_dir=args.output_dir,
            window_sec=args.window_sec,
            step_sec=args.step_sec,
        ))
    else:
        print(analyze_vibration_trend(
            start_date=args.start_date,
            end_date=args.end_date,
            feature_names=args.features,
            output_dir=args.output_dir,
        ))
