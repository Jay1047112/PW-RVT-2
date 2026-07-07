#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
plot_vibration.py

負責單筆 CSV 的 Time Domain / Frequency Domain plots。
"""

import os
from typing import Dict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import CONFIG
from utils import ensure_dir, get_analysis_paths
from analyze_vibration import load_vibration_csv, compute_fft


def plot_time_domain(time_axis: np.ndarray, signal: np.ndarray, axis_name: str, output_path: str) -> None:
    plt.figure(figsize=(10, 4))
    plt.plot(time_axis, signal)
    plt.title(f"{axis_name}-Axis Time Domain")
    plt.xlabel("Time (s)")
    plt.ylabel("g")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def plot_frequency_domain(signal: np.ndarray, sample_rate: int, axis_name: str, output_path: str, freq_max: float) -> None:
    freqs, amplitude, _ = compute_fft(signal, sample_rate)
    plt.figure(figsize=(10, 4))
    plt.plot(freqs, amplitude)
    plt.title(f"{axis_name}-Axis Frequency Domain")
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("g")
    plt.xlim(0, freq_max)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def generate_vibration_plots(input_csv: str, plot_type: str = "all") -> Dict[str, str]:
    output_dir, _ = get_analysis_paths(input_csv)
    ensure_dir(output_dir)

    df, signals = load_vibration_csv(input_csv)
    n = len(df)
    if n == 0:
        raise ValueError("CSV 沒有資料。")

    sample_rate = CONFIG["SAMPLE_RATE"]
    time_axis = np.arange(n) / sample_rate
    result_paths: Dict[str, str] = {}

    if plot_type in ("all", "time_domain"):
        for axis_name in ["X", "Y", "Z"]:
            output_path = os.path.join(output_dir, f"{axis_name.lower()}_time.png")
            plot_time_domain(time_axis, signals[axis_name], axis_name, output_path)
            result_paths[f"{axis_name}_time"] = os.path.abspath(output_path)

    if plot_type in ("all", "frequency_domain"):
        for axis_name in ["X", "Y", "Z"]:
            output_path = os.path.join(output_dir, f"{axis_name.lower()}_freq.png")
            plot_frequency_domain(signals[axis_name], sample_rate, axis_name, output_path, CONFIG["DEFAULT_FREQ_MAX"])
            result_paths[f"{axis_name}_freq"] = os.path.abspath(output_path)

    print("[INFO] Plot generation completed.")
    return result_paths


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate PW-RVT vibration plots.")
    parser.add_argument("csv_path", help="Path to PW-RVT raw CSV file.")
    parser.add_argument("--plot-type", default="all", choices=["all", "time_domain", "frequency_domain"])
    args = parser.parse_args()
    generate_vibration_plots(args.csv_path, args.plot_type)
