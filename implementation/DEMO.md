# Kịch bản demo (~2 phút)

Mở một cửa sổ PowerShell trong `implementation/`. **Chạy từng lệnh một lần trước khi quay** 
để `uv` / `npx` cache nóng và mọi thứ chạy nhanh trên camera. Phóng to font terminal (Ctrl `+`) 
để chữ đọc được rõ.

---

## Cảnh 1 — Giới thiệu (0:00–0:12)
- **Hiện:** cây thư mục `implementation/` trong VS Code (`db/`, `mcp_server.py`).
- **Nói:** "Đây là server FastMCP expose một database SQLite qua ba tool — 
  `search`, `insert`, `aggregate` — cộng hai schema resource. Logic được tách rõ: 
  `db/` lo database, `mcp_server.py` lo MCP."

## Cảnh 2 — Khởi tạo database (0:12–0:25)
```powershell
uv run python init_db.py
```
- **Nói:** "Tạo và seed database mẫu — 8 students ở các cohort A1/A2/B1, 4 courses, 11 enrollments. 
  Nó là idempotent nên có thể tái lập được."

## Cảnh 3 — Xác thực tự động (0:25–0:52)  ⭐ cảnh quan trọng nhất
```powershell
uv run python verify_server.py
```
- **Nói:** "Script này nối một in-memory client và kiểm tra mọi thứ: 3 tool và 2 resource đều discoverable; 
  các call hợp lệ hoạt động — search với filter/order/paging, insert trả về row kèm id, 
  aggregate tính avg theo cohort; và các request sai (table/column lạ, operator sai, insert rỗng) 
  đều bị chặn với thông báo rõ ràng. **17/17 PASS.**"

## Cảnh 4 — Client thực: Claude Code (0:52–1:20)
```powershell
claude mcp list
```
- **Nói:** "Server kết nối vào client MCP thực — Claude Code hiện 
  `sqlite-lab-local ✔ Connected`."
- Mở `claude` (phiên tương tác) và prompt:
  > Dùng MCP server sqlite-lab-local: cho tôi điểm trung bình score theo từng cohort, rồi liệt kê top 2 students điểm cao nhất.
- **Nói:** "Claude gọi `aggregate` và `search` tool của server rồi trả về kết quả."

## Cảnh 5 — Resource (1:20–1:35)
- Trong cùng phiên `claude`:
  > Đọc resource @sqlite-lab-local:schema://table/students và mô tả các cột.
- **Nói:** "Client đọc được schema dynamic của từng bảng — đây là schema context 
  được serve qua MCP."

## Cảnh 6 — Bonus: HTTP + bearer auth (1:35–1:52)
```powershell
uv run python demo_http_auth.py
```
- **Nói:** "Bonus: một HTTP transport có xác thực. Không có token → 401 Unauthorized; 
  có token → kết nối được và liệt kê tool. **RESULT: PASS.**"

## Cảnh 7 — Kết (1:52–2:00)
- **Hiện:** `db/base.py` và `db/postgres_adapter.py` nhanh qua.
- **Nói:** "Kiến trúc này là swappable backend — cùng một MCP surface chạy được 
  trên SQLite hoặc PostgreSQL. Cảm ơn đã xem."

---

### Tùy chọn: MCP Inspector (trình duyệt tool/resource)
```powershell
.\start_inspector.ps1
```
Mở URL được in ra, click vào tab **Tools** và **Resources** để hiện schema, 
chạy một call hợp lệ, rồi call tới bảng không tồn tại để hiện lỗi.
