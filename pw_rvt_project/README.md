# PW-RVT Vibration Analysis System

## Project Overview

本專案由原始 `main.py` 拆分而來，目標是把 PW-RVT / RS422 感測器流程模組化，方便後續接 MCP Server 與 Skill。

原本 `main.py` 同時包含：

1. RS422 / Modbus RTU 收資料
2. CSV 輸出
3. vibration feature analysis
4. Time Domain / Frequency Domain plots
5. PostgreSQL 寫入

現在拆成多個獨立 Python modules。

---

## Project Structure

```text
pw_rvt_project/
├─ collect.py
├─ analyze_vibration.py
├─ plot_vibration.py
├─ plot_feature_trend.py
├─ database.py
├─ mcp_server.py
├─ config.py
├─ utils.py
├─ main.py
├─ requirements.txt
├─ README.md
└─ skills/
   └─ pw-rvt-vibration-analysis/
      └─ SKILL.md
```

---

## Python Modules

### collect.py

負責連接 PW-RVT sensor，透過 RS422 / Modbus RTU 收集 Raw Data，並輸出 CSV。

### analyze_vibration.py

負責讀取 CSV、將 raw count 轉換為 g、計算 vibration features，並輸出 JSON feature content。

主要 features：

- RMS
- Skewness
- Kurtosis
- PeakToPeak
- SRA
- CrestFactor
- ShapeFactor
- ImpulseFactor
- ClearanceFactor
- TotalEnergy
- BandEnergy
- FreqCentroid
- PeakAmp
- PeakFreq

### plot_vibration.py

負責單筆 CSV 的 Time Domain plots 與 Frequency Domain plots。

### plot_feature_trend.py

負責 vibration feature trend analysis。

支援：

- single task sliding-window analysis
- multiple task historical trend analysis

Supported features：

- RMS
- Kurtosis
- PeakToPeak
- FreqCentroid

---

## Feature Trend Logic

### Single Task Trend Analysis

單筆 task 使用：

- window_sec
- step_sec

進行 sliding-window feature analysis。

例如：

```text
window_sec = 1
step_sec = 0.1
```

代表：

- 每次使用 1 秒 vibration data 計算 feature
- 每 0.1 秒往後滑動一次

輸出：

- X/Y/Z 三軸 feature trend
- 三軸畫在同一張圖

適合：

- signal internal trend observation
- transient vibration analysis

---

### Multiple Task Historical Trend Analysis

多筆 task：

- 每個 task 視為一次完整 measurement
- 每筆 CSV 使用 entire signal 計算 overall feature value
- 使用 measurement_time 作為 X-axis

例如：

| task_id | measurement_time | X_RMS |
|---|---|---|
| task_A | 16:27 | 0.8 |
| task_B | 16:30 | 0.6 |
| task_C | 16:31 | 1.5 |

適合：

- historical vibration monitoring
- long-term degradation observation
- abnormal trend detection

---

### analyze_vibration_trend_tool

用途：

- 使用 start_date / end_date 查詢 PostgreSQL historical records
- 進行 historical vibration trend analysis
- 比較不同 measurement 的 vibration feature values
- 產生 historical trend plots

適合：

- long-term vibration monitoring
- abnormal trend observation
- historical feature comparison

---

### analyze_feature_trend_by_task_ids_tool

用途：

- 指定一筆或多筆 task_id
- 產生 feature trend plots

Behavior：

- Single task：
  使用 sliding-window feature analysis
  根據 window_sec 與 step_sec
  分析單筆 vibration signal 的 feature trend
  X/Y/Z 三軸畫在同一張圖

- Multiple tasks：
  每個 task 視為一次完整 measurement
  使用 overall feature values
  根據 measurement_time
  呈現 historical vibration trends

---

### database.py

負責 PostgreSQL connection、task_id lookup、metadata storage、JSON feature content update、historical records query。

### mcp_server.py

負責將 Python functions 包裝成 MCP tools。

---

## Basic Usage

### Install dependencies

```bash
pip install -r requirements.txt
```

### Edit config.py

請先確認：

```python
"PORT": "COM5"
"BAUDRATE": 3000000
"COUNT_PER_G": 2000.0
"DB_HOST": "localhost"
"DB_NAME": "AILappingPlan"
"DB_USER": "postgres"
"DB_PASSWORD": "postgres328"
```

若確認 PW-RVT ±4g 靈敏度為 8000 count/g，請將：

```python
"COUNT_PER_G": 8000.0
```

---

## Run Locally

### 收資料

```bash
python collect.py
```

### 分析 CSV

```bash
python analyze_vibration.py path/to/raw.csv
```

### 畫 Time Domain / Frequency Domain 圖

```bash
python plot_vibration.py path/to/raw.csv
```

### 畫 Feature Trend 圖

```bash
python plot_feature_trend.py
```

### 一鍵完整流程

```bash
python main.py
```

---

## MCP Server

```bash
python mcp_server.py
```

不同 MCP / FastMCP 環境可能需要調整啟動方式。

---

## Database Notes

目前保留原始 `main.py` 的相容寫法：

```text
task_id
timestamp
features
raw_file_path
avg_temperature
min_temperature
max_temperature
```

若要使用完整 MCP workflow，建議資料表額外加入：

```text
host_name
host_ip
duration_sec
num_samples
temperature_info
```

---

## Important Notes

- 本系統假設 sensor 固定在同一個 measurement point。
- historical trend analysis 是比較不同時間的資料，不是比較不同位置。
- CSV path 可能只在收資料主機上有效。
- PostgreSQL 可記錄 host_name / host_ip / csv_local_path，方便跨主機追蹤資料來源。
