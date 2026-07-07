#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
database.py

負責：
1. PostgreSQL 連線
2. 寫入 measurement metadata / feature JSON
3. 查詢 task_id / historical records
"""

import json
import os
import socket
from datetime import datetime
from typing import Dict, List, Any, Optional

import psycopg2
import psycopg2.extras

from config import CONFIG
from utils import task_id_from_csv_path


def get_connection():
    return psycopg2.connect(
        host=CONFIG["DB_HOST"],
        database=CONFIG["DB_NAME"],
        user=CONFIG["DB_USER"],
        password=CONFIG["DB_PASSWORD"],
        port=CONFIG["DB_PORT"],
    )


def insert_measurement_metadata(
    raw_file_path: str,
    duration_sec: Optional[float] = None,
    num_samples: Optional[int] = None,
    temperature_info: Optional[Dict[str, Any]] = None,
) -> str:
    """
    新 MCP flow 用：
    collect.py 收完 CSV 後，先寫入 metadata，回傳 task_id。

    若資料表尚未包含 host_name / host_ip / duration_sec / num_samples / temperature_info，
    可先使用 insert_features_to_db() 相容舊表。
    """
    task_id = task_id_from_csv_path(raw_file_path)
    host_name = socket.gethostname()
    try:
        host_ip = socket.gethostbyname(host_name)
    except Exception:
        host_ip = "unknown"

    conn = get_connection()
    cursor = conn.cursor()

    try:
        insert_query = f'''
        INSERT INTO "{CONFIG["DB_SCHEMA"]}"."{CONFIG["DB_TABLE"]}"
        (task_id, "timestamp", raw_file_path, host_name, host_ip, duration_sec, num_samples, temperature_info)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        '''

        cursor.execute(
            insert_query,
            (
                task_id,
                datetime.now().replace(microsecond=0),
                os.path.abspath(raw_file_path),
                host_name,
                host_ip,
                duration_sec,
                num_samples,
                json.dumps(temperature_info or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return task_id

    finally:
        cursor.close()
        conn.close()


def update_feature_json(task_id: str, features: Dict[str, Any]) -> None:
    """
    將 JSON feature content 更新回 PostgreSQL。
    依照目前需求：更新 JSON 內容，不更新 JSON 路徑。
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        update_query = f'''
        UPDATE "{CONFIG["DB_SCHEMA"]}"."{CONFIG["DB_TABLE"]}"
        SET features = %s
        WHERE task_id = %s
        '''
        cursor.execute(update_query, (json.dumps(features, ensure_ascii=False), task_id))
        conn.commit()

    finally:
        cursor.close()
        conn.close()


def get_task_record(task_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        query = f'''
        SELECT *
        FROM "{CONFIG["DB_SCHEMA"]}"."{CONFIG["DB_TABLE"]}"
        WHERE task_id = %s
        LIMIT 1
        '''
        cursor.execute(query, (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    finally:
        cursor.close()
        conn.close()


def get_csv_path_by_task_id(task_id: str) -> str:
    row = get_task_record(task_id)
    if not row:
        raise ValueError(f"找不到 task_id：{task_id}")

    raw_file_path = row.get("raw_file_path") or row.get("csv_local_path")
    if not raw_file_path:
        raise ValueError(f"task_id={task_id} 沒有 raw_file_path / csv_local_path")

    return raw_file_path


def query_feature_records(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    task_id: Optional[str] = None,
    feature_name: Optional[str] = None,
    axis: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conditions = []
    params = []

    if task_id:
        conditions.append("task_id = %s")
        params.append(task_id)

    if start_date:
        conditions.append('"timestamp" >= %s')
        params.append(start_date)

    if end_date:
        conditions.append('"timestamp" <= %s')
        params.append(end_date)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        query = f'''
        SELECT *
        FROM "{CONFIG["DB_SCHEMA"]}"."{CONFIG["DB_TABLE"]}"
        {where_clause}
        ORDER BY "timestamp" ASC
        '''
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        result = []
        for row in rows:
            item = dict(row)
            if isinstance(item.get("features"), str):
                try:
                    item["features"] = json.loads(item["features"])
                except Exception:
                    pass
            result.append(item)

        return result

    finally:
        cursor.close()
        conn.close()


def insert_features_to_db(features: Dict, raw_file_path: str) -> None:
    """
    相容原始 main.py 的舊流程：
    analyze 後直接 INSERT features / raw_file_path / temperature summary。
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        task_id = task_id_from_csv_path(raw_file_path)
        timestamp = datetime.now().replace(microsecond=0)

        temperature_block = features.get("temperature", {})
        avg_temperature = round(float(temperature_block.get("Mean", 0.0)), 1)
        min_temperature = round(float(temperature_block.get("Min", 0.0)), 1)
        max_temperature = round(float(temperature_block.get("Max", 0.0)), 1)

        insert_query = f'''
        INSERT INTO "{CONFIG["DB_SCHEMA"]}"."{CONFIG["DB_TABLE"]}"
        (task_id, "timestamp", features, raw_file_path, avg_temperature, min_temperature, max_temperature)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''

        cursor.execute(
            insert_query,
            (
                task_id,
                timestamp,
                json.dumps(features, ensure_ascii=False),
                os.path.abspath(raw_file_path),
                avg_temperature,
                min_temperature,
                max_temperature,
            ),
        )

        conn.commit()
        print("[INFO] 資料已成功寫入 PostgreSQL")
        print(f"[INFO] task_id       : {task_id}")
        print(f"[INFO] raw_file_path : {os.path.abspath(raw_file_path)}")

    finally:
        cursor.close()
        conn.close()
