#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
集中管理 PW-RVT / RS422 / PostgreSQL / analysis 設定。
此檔案由原始 main.py 的 CONFIG 拆分而來。
"""

CONFIG = {
    # ===== RS422 / Modbus =====
    "PORT": "COM5",
    "BAUDRATE": 3000000,
    "BYTESIZE": 8,
    "PARITY": "N",
    "STOPBITS": 1,
    "TIMEOUT": 0.05,
    "UNIT_ID": 1,

    # ===== 收資料 =====
    "SAMPLE_RATE": 7812,
    "MAX_AXES_GROUPS": 41,
    "SHORT_DATA_SLEEP_SEC": 0.001,
    "PRINT_EVERY_N_LOOPS": 10,
    "PRINT_FIRST_3_AXES": True,
    "DURATION_SEC": 10,
    "OUTPUT_CSV": "pw_rvt_raw_data_with_temp.csv",
    "PRINT_PROGRESS_EVERY_N_SAMPLES": 2000,

    # ===== 溫度 =====
    "TEMP_REGISTER": 0x14,
    "TEMP_READ_INTERVAL_SEC": 0.5,

    # ===== 分析 =====
    "ANALYSIS_ROOT_DIR": "analysis_output",
    "DEFAULT_FREQ_MAX": 2000.0,
    # 依照原始 main.py 保留；若後續確認 ±4g 靈敏度為 8000 count/g，請改為 8000.0
    "COUNT_PER_G": 2000.0,
    "ROUND_DIGITS": 1,

    # ===== PostgreSQL =====
    "DB_HOST": "localhost",
    "DB_NAME": "AILappingPlan",
    "DB_USER": "postgres",
    "DB_PASSWORD": "postgres328",
    "DB_PORT": "5432",

    # ===== 資料表 =====
    "DB_SCHEMA": "Sensors",
    "DB_TABLE": "Vib_data",
}
