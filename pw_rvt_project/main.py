#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
main.py

本機測試用一鍵流程：
collect → analyze → plot → insert to PostgreSQL
"""

from typing import Optional

from collect import collect_vibration_data
from analyze_vibration import analyze_vibration_csv
from plot_vibration import generate_vibration_plots
from database import insert_features_to_db


def run_collection_task(duration_sec: Optional[float] = None):
    raw_csv_path = collect_vibration_data(duration_sec=duration_sec)
    if not raw_csv_path:
        return {"status": "error", "message": "No CSV generated"}

    json_path, features = analyze_vibration_csv(raw_csv_path)
    plot_paths = generate_vibration_plots(raw_csv_path, plot_type="all")

    # 相容原始 main.py：直接 INSERT features 到 PostgreSQL
    insert_features_to_db(features, raw_csv_path)

    return {
        "status": "success",
        "raw_csv": raw_csv_path,
        "json": json_path,
        "plots": plot_paths,
        "num_samples": features["num_samples"],
        "duration_sec": features["duration_sec"],
        "requested_duration_sec": duration_sec,
    }


def main():
    result = run_collection_task()
    print(result)


if __name__ == "__main__":
    main()
