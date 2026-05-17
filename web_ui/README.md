# Module Web UI

## Mục đích

`web_ui/` là giao diện frontend tĩnh để dùng nhanh các chức năng chính mà không cần bước build riêng.

## Thành phần

| File | Vai trò |
|---|---|
| `index.html` | Trang tổng quan |
| `agent.html` | Giao diện chat Agent |
| `agent.js` | Logic chat + stream response |
| `nhap-tai-lieu.html` | Trang upload hồ sơ y tế |
| `lich-nhac.html` | Trang lịch nhắc thuốc |
| `tin-tuc-y-te.html` | Trang thông tin/tin tức |
| `app.js` | JS dùng chung |
| `schedule.js` | JS cho lịch nhắc thuốc |
| `styles.css` | CSS toàn bộ giao diện |

## Cách truy cập

Khi API chạy, static được mount tại:

- `http://localhost:8000/ui/`

## Hành vi chính theo file (frontend)

| File | Nội dung kỹ thuật |
|---|---|
| `index.html` | Landing / điều hướng tới các trang con. |
| `agent.html` + `agent.js` | Form chat: `fetch` POST agent; stream: đọc NDJSON từ `/api/agent-query/stream`, append token/step UI. |
| `nhap-tai-lieu.html` | Upload `FormData` tới `/api/medical-record/analyze`, hiển thị JSON kết quả. |
| `lich-nhac.html` + `schedule.js` | Lịch nhắc cục bộ (localStorage / UI) — tích hợp API tuỳ triển khai. |
| `tin-tuc-y-te.html` | Nội dung tin tức tĩnh hoặc link ngoài. |
| `app.js` | Util dùng chung (fetch base URL, thông báo lỗi). |
| `styles.css` | Layout / theme một file. |

## Tích hợp backend

- Agent endpoints: `/api/agent-query`, `/api/agent-query/stream`
- Medical record endpoint: `/api/medical-record/analyze`
- Health check: `/health`, `/health/ready`

## Sơ đồ luồng frontend -> backend

```text
Người dùng (trình duyệt)
          |
          v
index.html / agent.html / nhap-tai-lieu.html
          |
   +------+------+
   |             |
   v             v
agent.js       app.js
  |  \          |   \
  |   \         |    \-> /health
  |    \        |
  v     v       v
/api/agent-query  /api/agent-query/stream
                    |
                    v
             render chat theo luồng
app.js -> /api/medical-record/analyze -> render kết quả phân tích
```

## Cần cải thiện

1. Tách JS theo module nhỏ để dễ bảo trì.
2. Chuẩn hóa state management cho chat/session.
3. Bổ sung e2e tests cho luồng upload + chat stream.

## Liên kết

- README tổng: [`../README.md`](../README.md)
- API docs: [`../api/README.md`](../api/README.md)
