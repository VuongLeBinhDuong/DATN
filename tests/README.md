# Bộ kiểm thử cho DATN

Thư mục `tests/` dùng **pytest** để kiểm tra các phần quan trọng của hệ thống.  
Mục tiêu chính: phát hiện lỗi sớm khi thay đổi code (route, agent, repository, cấu hình).

## File test và phạm vi

| File | Kiểm tra gì |
|---|---|
| `conftest.py` | Fixture dùng chung (`client`, mock backend, dọn cache settings) |
| `test_core_settings.py` | Nạp env/config, singleton `get_settings()` |
| `test_core_llm_backends.py` | `OllamaBackend`, `OpenRouterBackend`, `get_llm_backend()` |
| `test_repositories.py` | Repository pattern, factory chọn backend |
| `test_agent_react.py` | Parser/tool/flow ReAct (thường dùng mock LLM) |
| `test_api_routes.py` | Endpoint FastAPI qua `TestClient` |

## Cấu trúc thư mục

```
tests/
├── __init__.py               # Khai báo package test
├── conftest.py               # Fixture dùng chung
├── README.md                 # Tài liệu này
├── test_core_settings.py     # Test cho core/settings.py
├── test_core_llm_backends.py # Test cho core/llm_backends.py
├── test_repositories.py      # Test cho repositories/
├── test_agent_react.py       # Test cho agent/react/
└── test_api_routes.py        # Test cho api/routes/
```

## Cách chạy test

```bash
# 1) Cài dependencies
pip install -r requirements.txt

# 2) Chạy toàn bộ test
pytest tests/ -v

# 3) Chạy kèm coverage
pytest tests/ --cov=. --cov-report=html

# 4) Chạy một file test
pytest tests/test_core_settings.py -v

# 5) Bỏ qua test chậm
pytest tests/ -v -m "not slow"

# 6) Bỏ qua integration test
pytest tests/ -v -m "not integration"
```

## Fixture quan trọng trong `conftest.py`

| Fixture | Ý nghĩa cho người mới |
|---------|------------------------|
| `mock_ollama_backend` | Giả lập Ollama để test không cần server thật |
| `mock_query_result` | Dữ liệu mẫu dạng kết quả truy vấn |
| `mock_repository` | Repository giả để test logic service/route |
| `mock_streaming_chunks` | Dữ liệu stream giả lập từ LLM |
| `clean_settings_cache` | Xóa cache singleton để test độc lập |
| `temp_graphrag_project` | Dự án GraphRAG tạm cho test |
| `sample_react_output` | Chuỗi output mẫu để test parser ReAct |
| `client` | `FastAPI TestClient` để gọi endpoint |

## Marker thường dùng

| Marker | Ý nghĩa |
|--------|---------|
| `@pytest.mark.slow` | Test chạy lâu |
| `@pytest.mark.integration` | Test tích hợp nhiều thành phần |
| `@pytest.mark.requires_neo4j` | Chỉ chạy khi có Neo4j |
| `@pytest.mark.requires_ollama` | Chỉ chạy khi có Ollama |

## Sơ đồ luồng chạy test

```text
Developer -> pytest tests/
      |          |            |
      |          |            +-> coverage html
      |          +-> test_core_* / test_agent_react (unit)
      |                         |
      |                         +-> fixtures + mock backend
      +-> test_api_routes -> TestClient
```

## Mẫu viết test mới

```python
# tests/test_new_module.py
from __future__ import annotations

from core.new_module import MyClass


class TestMyClass:
    """Nhóm test cho MyClass."""

    def test_something(self):
        obj = MyClass()
        result = obj.do_something()
        assert result == expected
```

## Xem báo cáo coverage

```bash
pytest tests/ --cov=. --cov-report=html
start htmlcov/index.html  # Windows
```

## Lỗi thường gặp

| Lỗi | Cách xử lý nhanh |
|-----|-------------------|
| `ModuleNotFoundError` | Chạy lệnh từ root repo: `pytest tests/` |
| `Fixture not found` | Kiểm tra tên fixture trong `conftest.py` |
| `ImportError` | Cài lại dependencies: `pip install -r requirements.txt` |
