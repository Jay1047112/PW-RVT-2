#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
mcp_server.py

將 PW-RVT Python modules 包裝成 MCP tools。

注意：
不同版本 FastMCP import 方式可能不同。
若你的環境使用 fastmcp 套件，通常可用：
    from fastmcp import FastMCP
"""

from typing import Optional

from fastmcp import FastMCP

from collect import collect_vibration_data
from analyze_vibration import analyze_vibration_csv
from plot_vibration import generate_vibration_plots
from plot_feature_trend import analyze_vibration_trend, analyze_feature_trend_by_task_ids
from database import (
    insert_measurement_metadata,
    update_feature_json,
    get_csv_path_by_task_id,
    query_feature_records,
)

mcp = FastMCP("pw-rvt-vibration-analysis")


@mcp.tool()
def collect_sensor_data(duration_sec: Optional[float] = None):
    csv_path = collect_vibration_data(duration_sec=duration_sec)
    if not csv_path:
        return {"status": "error", "message": "No CSV generated"}

    task_id = insert_measurement_metadata(raw_file_path=csv_path, duration_sec=duration_sec)
    return {"status": "success", "task_id": task_id, "csv_local_path": csv_path}


@mcp.tool()
def analyze_vibration_file(task_id: str):
    csv_path = get_csv_path_by_task_id(task_id)
    json_path, features = analyze_vibration_csv(csv_path)
    update_feature_json(task_id, features)
    return {
        "status": "success",
        "task_id": task_id,
        "csv_local_path": csv_path,
        "json_path": json_path,
        "features": features,
    }


@mcp.tool()
def generate_vibration_plots_tool(task_id: str, plot_type: str = "all"):
    csv_path = get_csv_path_by_task_id(task_id)
    plot_paths = generate_vibration_plots(csv_path, plot_type=plot_type)
    return {"status": "success", "task_id": task_id, "plot_paths": plot_paths}


@mcp.tool()
def query_sensor_database(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    task_id: Optional[str] = None,
    feature_name: Optional[str] = None,
    axis: Optional[str] = None,
):
    records = query_feature_records(
        start_date=start_date,
        end_date=end_date,
        task_id=task_id,
        feature_name=feature_name,
        axis=axis,
    )
    return {"status": "success", "count": len(records), "records": records}


@mcp.tool()
def analyze_vibration_trend_tool(
    start_date: str,
    end_date: str,
    feature_names: Optional[str] = None,
    axis: Optional[str] = None,
    feature_name: Optional[str] = None,
    aggregation_method: str = "all",
):
    """Analyze historical feature trends for the fixed measurement point.

    New usage:
      feature_names = "RMS,Kurtosis,PeakToPeak,FreqCentroid"

    Backward-compatible usage:
      axis = "Z", feature_name = "RMS"
    """
    return analyze_vibration_trend(
        start_date=start_date,
        end_date=end_date,
        axis=axis,
        feature_name=feature_name,
        feature_names=feature_names,
        aggregation_method=aggregation_method,
    )


@mcp.tool()
def analyze_feature_trend_by_task_ids_tool(
    task_ids: str,
    feature_names: Optional[str] = None,
    window_sec: float = 1.0,
    step_sec: float = 0.1,
):
    """Generate feature trend plots from one or multiple task_id values.

    - One task_id: sliding-window trend, X/Y/Z lines in the same plot.
    - Multiple task_id values: historical trend, X/Y/Z lines over measurement time.

    task_ids can be a comma-separated string.
    """
    return analyze_feature_trend_by_task_ids(
        task_ids=task_ids,
        feature_names=feature_names,
        window_sec=window_sec,
        step_sec=step_sec,
    )


if __name__ == "__main__":
    mcp.run()
