---
name: pw-rvt-vibration-analysis
description: Use this skill when the user asks about PW-RVT, RS422, Modbus RTU, vibration analysis, CSV analysis, RMS, Kurtosis, Peak-to-Peak, Frequency Centroid, PostgreSQL, historical trend analysis, vibration report, Raw Data, feature extraction, or MCP Server based sensor workflows.
---

# PW-RVT Vibration Analysis

## Purpose

此 Skill 用於 PW-RVT vibration workflow 自動化。

主要功能包含：

- PW-RVT Raw Data collection
- vibration feature extraction
- CSV analysis
- PostgreSQL historical query
- vibration trend analysis
- Time Domain / Frequency Domain plots
- feature trend plots
- vibration report generation

本系統基於固定 measurement point，分析同一位置於不同時間的 vibration changes。

---

## When To Use

當使用者詢問以下內容時使用：

- PW-RVT
- RS422
- Modbus RTU
- vibration analysis
- CSV analysis
- RMS
- Kurtosis
- Peak-to-Peak
- Frequency Centroid
- PostgreSQL
- historical trend analysis
- feature trend plots
- vibration report
- Raw Data
- feature extraction

---

## MCP Tools

### collect_sensor_data

用途：收集 PW-RVT Raw Data。

Input：

- duration_sec

Output：

- task_id
- csv_local_path
- measurement_time
- num_samples
- temperature_info

Related Module：

- collect.py

---

### analyze_vibration_file

用途：分析單筆 vibration task。

Input：

- task_id

Output：

- JSON feature content
- vibration feature results

Related Module：

- analyze_vibration.py

---

### generate_vibration_plots

用途：產生 vibration plots。

Input：

- task_id
- plot_type

Output：

- Time Domain plots
- Frequency Domain plots

Related Module：

- plot_vibration.py

---

### analyze_feature_trend_by_task_ids_tool

用途：產生 vibration feature trend plots。

Supported features：

- RMS
- Kurtosis
- PeakToPeak
- FreqCentroid

Input：

- task_ids
- feature_names
- window_sec
- step_sec

Behavior：

- Single task：
  使用 sliding-window feature analysis。
  根據 window_sec 與 step_sec，
  分析單筆 vibration signal 的 feature trend。
  X/Y/Z 三軸會畫在同一張圖。

- Multiple tasks：
  每個 task 視為一次完整 measurement。
  每份 CSV 使用 entire signal 計算 overall feature value。
  使用 measurement_time 作為 X-axis，
  呈現 historical vibration trends。

Output：

- feature trend plots
- historical comparison
- vibration trend summaries

Related Modules：

- database.py
- analyze_vibration.py
- plot_feature_trend.py

---

### query_sensor_database

用途：查詢 PostgreSQL historical records。

Input：

- start_date
- end_date
- task_id
- feature_name

Output：

- historical task records
- feature values
- measurement information

Related Module：

- database.py

---

### analyze_vibration_trend_tool

用途：分析固定 measurement point 的 historical vibration trends。

Behavior：

- 使用 start_date / end_date 查詢 PostgreSQL historical records
- 分析 vibration feature changes
- 比較不同 measurement 的 feature values
- 產生 historical trend plots

Input：

- start_date
- end_date
- feature_names
- aggregation_method

Output：

- trend analysis
- historical comparison
- abnormal fluctuation points
- trend plots

Related Modules：

- database.py
- analyze_vibration.py
- plot_feature_trend.py

---

### generate_vibration_report

用途：自動產生 vibration report。

Input：

- task_id

or

- start_date
- end_date

Output：

- vibration summary
- trend conclusion
- report-ready text

Related Modules：

- database.py
- analyze_vibration.py
- plot_feature_trend.py

---

## Output Style

輸出 vibration analysis 時：

- 使用中文說明
- technical feature names 保留英文
- 著重 vibration trend explanation
- 避免直接判定 equipment failure

建議使用：

- vibration 有升高趨勢
- 可能存在 impact-like signal
- 建議持續觀察
- 尚不能直接判定 fault type

---

## Notes

- PW-RVT 支援 three-axis vibration 與 temperature
- Communication：RS422 / Modbus RTU
- Database：PostgreSQL
- JSON feature content 直接存於 PostgreSQL
- historical trend analysis 基於固定 measurement point 的 repeated measurements
