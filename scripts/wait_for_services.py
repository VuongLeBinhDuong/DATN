#!/usr/bin/env python3
"""Kiểm tra tính sẵn sàng của Neo4j và Ollama trước khi khởi chạy API server.
Tự động áp dụng Cypher Schema và nhập dữ liệu baseline nếu cơ sở dữ liệu trống.
"""

from __future__ import annotations

import os
import sys
import time
import socket
import subprocess
from urllib.parse import urlparse
from pathlib import Path

# Thêm thư mục gốc vào sys.path để import các module của dự án
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

def wait_for_port(host: str, port: int, timeout_sec: int = 60) -> bool:
    """Chờ cổng TCP chấp nhận kết nối."""
    start_time = time.time()
    print(f"[*] Đang chờ kết nối tới {host}:{port}...", flush=True)
    while time.time() - start_time < timeout_sec:
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"[+] Kết nối thành công tới {host}:{port}!", flush=True)
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            time.sleep(2)
    print(f"[-] Quá thời gian chờ {host}:{port} sau {timeout_sec} giây.", flush=True)
    return False

def check_and_initialize_db() -> bool:
    """Kiểm tra và tự động khởi tạo cơ sở dữ liệu Neo4j nếu trống."""
    try:
        from kg.neo4j_client import Neo4jKGClient
        client = Neo4jKGClient()
        driver, db = client._connection()
        driver.verify_connectivity()
        
        # Đếm số lượng thực thể Entity y tế
        with driver.session(database=db) as session:
            result = session.run("MATCH (n:Entity) RETURN count(n) AS cnt").single()
            entity_count = result["cnt"] if result else 0
            
        print(f"[+] Kết nối thành công tới Neo4j. Tìm thấy {entity_count} nút Entity trong db '{db}'.", flush=True)
        
        # Nếu chưa có dữ liệu, tiến hành khởi tạo
        if entity_count == 0:
            print("[*] Cơ sở dữ liệu trống. Đang tự động thiết lập schema và nạp dữ liệu baseline...", flush=True)
            
            # Chạy apply schema
            schema_script = REPO_ROOT / "scripts" / "kg_apply_schema.py"
            print(f"[*] Đang chạy: python {schema_script.relative_to(REPO_ROOT)}", flush=True)
            subprocess.run([sys.executable, str(schema_script)], check=True)
            
            # Chạy import baseline artifacts
            import_script = REPO_ROOT / "scripts" / "kg_import_artifacts.py"
            print(f"[*] Đang chạy: python {import_script.relative_to(REPO_ROOT)} --clear", flush=True)
            subprocess.run([sys.executable, str(import_script), "--clear"], check=True)
            
            print("[+] Khởi tạo cơ sở dữ liệu y tế thành công!", flush=True)
        return True
    except Exception as e:
        print(f"[-] Lỗi khi kết nối hoặc khởi tạo cơ sở dữ liệu Neo4j: {e}", file=sys.stderr, flush=True)
        return False

def main() -> int:
    # 1. Tải settings cấu hình
    try:
        from core.settings import get_settings
        settings = get_settings()
        neo_cfg = settings.neo4j
    except Exception as e:
        print(f"[!] Không thể tải cấu hình dự án: {e}", file=sys.stderr, flush=True)
        neo_cfg = None

    # 2. Đọc cấu hình kết nối Neo4j
    neo4j_uri = os.getenv("NEO4J_URI") or (neo_cfg.uri if neo_cfg else "bolt://localhost:7687")
    parsed_neo = urlparse(neo4j_uri)
    neo_host = parsed_neo.hostname or "localhost"
    neo_port = parsed_neo.port or 7687

    # Chờ Neo4j sẵn sàng
    neo4j_timeout = int(os.getenv("NEO4J_CONNECT_TIMEOUT_SEC", "60"))
    if not wait_for_port(neo_host, neo_port, timeout_sec=neo4j_timeout):
        print("[-] Neo4j không sẵn sàng. Tiếp tục khởi động nhưng các chức năng liên quan đến đồ thị sẽ bị lỗi.", file=sys.stderr, flush=True)
    else:
        check_and_initialize_db()

    # 3. Kiểm tra tính sẵn sàng của Ollama (nếu bật sử dụng Ollama)
    llm_backend = os.getenv("LLM_BACKEND", "ollama").lower()
    use_ollama = os.getenv("USE_OLLAMA") or (str(get_settings().use_ollama) if hasattr(get_settings(), 'use_ollama') else "1")
    
    if llm_backend == "ollama" and use_ollama in ("1", "true", "True"):
        ollama_host = os.getenv("OLLAMA_HOST") or (settings.ollama.host if settings else "http://localhost:11434")
        parsed_ollama = urlparse(ollama_host)
        ollama_ip = parsed_ollama.hostname or "localhost"
        ollama_port = parsed_ollama.port or 11434
        
        # Chờ cổng kết nối Ollama
        print(f"[*] Đang sử dụng Ollama backend tại: {ollama_host}", flush=True)
        wait_for_port(ollama_ip, ollama_port, timeout_sec=15)
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
