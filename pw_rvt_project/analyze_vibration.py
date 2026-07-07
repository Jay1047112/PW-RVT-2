#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
analyze_vibration.py

負責：
1. 讀取 PW-RVT CSV Raw Data
2. 將 raw count 轉換為 g
3. 計算 Time Domain / Frequency Domain vibration features
4. 輸出 JSON feature content
"""

import json
import os
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from config import CONFIG
from utils import ensure_dir, safe_div, round_all_floats, get_analysis_paths


def calc_skewness(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    mu = np.mean(x)
    sigma = np.std(x, ddof=0)
    if sigma < 1e-12:
        return 0.0
    return float(np.mean(((x - mu) / sigma) ** 3))


def calc_kurtosis(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    mu = np.mean(x)
    sigma = np.std(x, ddof=0)
    if sigma < 1e-12:
        return 0.0
    return float(np.mean(((x - mu) / sigma) ** 4))


def compute_fft(signal: np.ndarray, sample_rate: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    signal = np.asarray(signal, dtype=np.float64)
    signal = signal - np.mean(signal)

    n = len(signal)
    if n == 0:
        return np.array([]), np.array([]), np.array([])

    fft_vals = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

    amplitude = np.abs(fft_vals) / n
    if n > 1:
        amplitude[1:-1] *= 2.0

    power = amplitude ** 2
    return freqs, amplitude, power


def time_domain_features(x: np.ndarray) -> Dict[str, float]:
    x = np.asarray(x, dtype=np.float64)
    abs_x = np.abs(x)

    peak = float(np.max(abs_x)) if len(x) else 0.0
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    mean_abs = float(np.mean(abs_x)) if len(x) else 0.0
    peak_to_peak = float(np.max(x) - np.min(x)) if len(x) else 0.0
    sra = float(np.mean(np.sqrt(abs_x)) ** 2) if len(x) else 0.0

    return {
        "RMS": rms,
        "Skewness": calc_skewness(x),
        "Kurtosis": calc_kurtosis(x),
        "PeakToPeak": peak_to_peak,
        "SRA": sra,
        "CrestFactor": safe_div(peak, rms),
        "ShapeFactor": safe_div(rms, mean_abs),
        "ImpulseFactor": safe_div(peak, mean_abs),
        "ClearanceFactor": safe_div(peak, sra),
    }


def band_energy(freqs: np.ndarray, power: np.ndarray, f_low: float, f_high: float) -> float:
    mask = (freqs >= f_low) & (freqs < f_high)
    if not np.any(mask):
        return 0.0
    return float(np.sum(power[mask]))


def freq_domain_features(x: np.ndarray, sample_rate: int) -> Dict[str, float]:
    freqs, amplitude, power = compute_fft(x, sample_rate)

    if len(freqs) == 0:
        return {
            "TotalEnergy": 0.0,
            "BandEnergy_0_500": 0.0,
            "BandEnergy_500_1000": 0.0,
            "BandEnergy_1000_2000": 0.0,
            "FreqCentroid": 0.0,
            "PeakAmp": 0.0,
            "PeakFreq": 0.0,
        }

    total_energy = float(np.sum(power))
    peak_amp = float(np.max(amplitude))
    peak_idx = int(np.argmax(amplitude))
    peak_freq = float(freqs[peak_idx])

    amp_sum = float(np.sum(amplitude))
    freq_centroid = safe_div(np.sum(freqs * amplitude), amp_sum)

    return {
        "TotalEnergy": total_energy,
        "BandEnergy_0_500": band_energy(freqs, power, 0.0, 500.0),
        "BandEnergy_500_1000": band_energy(freqs, power, 500.0, 1000.0),
        "BandEnergy_1000_2000": band_energy(freqs, power, 1000.0, 2000.0),
        "FreqCentroid": freq_centroid,
        "PeakAmp": peak_amp,
        "PeakFreq": peak_freq,
    }


def temperature_features(t: np.ndarray) -> Dict[str, float]:
    t = np.asarray(t, dtype=np.float64)
    if len(t) == 0:
        return {"Mean": 0.0, "Min": 0.0, "Max": 0.0, "Std": 0.0}
    return {
        "Mean": float(np.mean(t)),
        "Min": float(np.min(t)),
        "Max": float(np.max(t)),
        "Std": float(np.std(t, ddof=0)),
    }


def all_features(x: np.ndarray, sample_rate: int) -> Dict[str, float]:
    feats = {}
    feats.update(time_domain_features(x))
    feats.update(freq_domain_features(x, sample_rate))
    return feats


def load_vibration_csv(input_csv: str) -> Tuple[pd.DataFrame, Dict[str, np.ndarray]]:
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"找不到輸入檔案：{input_csv}")

    df = pd.read_csv(input_csv)

    required_cols = ["Time", "X", "Y", "Z"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"CSV 缺少必要欄位：{missing_cols}")

    try:
        df["Time"] = pd.to_datetime(df["Time"])
    except Exception:
        pass

    count_per_g = CONFIG["COUNT_PER_G"]
    signals = {
        "X": df["X"].to_numpy(dtype=np.float64) / count_per_g,
        "Y": df["Y"].to_numpy(dtype=np.float64) / count_per_g,
        "Z": df["Z"].to_numpy(dtype=np.float64) / count_per_g,
    }

    return df, signals


def analyze_vibration_csv(input_csv: str, write_json: bool = True) -> Tuple[str, Dict]:
    output_dir, json_name = get_analysis_paths(input_csv)
    ensure_dir(output_dir)

    df, signals = load_vibration_csv(input_csv)

    n = len(df)
    if n == 0:
        raise ValueError("CSV 沒有資料。")

    sample_rate = CONFIG["SAMPLE_RATE"]

    features = {
        "input_csv": os.path.abspath(input_csv),
        "sample_rate": sample_rate,
        "num_samples": int(n),
        "duration_sec": float(n / sample_rate),
        "requested_duration_sec": float(n / sample_rate),
        "features": {
            "X": all_features(signals["X"], sample_rate),
            "Y": all_features(signals["Y"], sample_rate),
            "Z": all_features(signals["Z"], sample_rate),
        },
    }

    if "Temp_C" in df.columns:
        temp = df["Temp_C"].to_numpy(dtype=np.float64)
        features["temperature"] = temperature_features(temp)

    features = round_all_floats(features, CONFIG["ROUND_DIGITS"])
    json_path = os.path.join(output_dir, json_name)

    if write_json:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(features, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("[INFO] Analysis completed.")
    print(f"[INFO] Input CSV      : {os.path.abspath(input_csv)}")
    print(f"[INFO] Output Folder  : {os.path.abspath(output_dir)}")
    print(f"[INFO] Samples        : {n}")
    print(f"[INFO] Duration (sec) : {n / sample_rate:.6f}")
    print(f"[INFO] JSON Output    : {os.path.abspath(json_path)}")
    print("=" * 60)

    return os.path.abspath(json_path), features


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analyze PW-RVT vibration CSV.")
    parser.add_argument("csv_path", help="Path to PW-RVT raw CSV file.")
    args = parser.parse_args()
    analyze_vibration_csv(args.csv_path)
