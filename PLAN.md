# PLAN — flow chuẩn, scope commit, template kết quả

## 1. Flow chuẩn của một đợt (mỗi lần làm việc theo đúng thứ tự)

1. **Phát biểu giả thuyết** 1-2 dòng trong đầu đợt (ROADMAP đợt đang làm): "nghi X là nút thắt,
   đo Y sẽ chứng minh/trả bại".
2. **Viết/tái sử dụng script đo** đặt trong `scripts/`. Script phải chạy được độc lập, ghi ra
   JSON trong `evidence/`, không hardcode đường dẫn máy.
3. **Chạy + lưu bằng chứng**: JSON vào `evidence/`, tên file mô tả
   (`<chủ-de>-<gì>-<ngày>.json`). Ghi trong JSON: ngày, hostname, version tool, lệnh chạy.
4. **Cập nhật tài liệu** của đợt (docs/ hoặc reports/): số đo vào bảng, kèm nguồn loại nào
   (đo tại máy / công bố / ước tính — xem [README § quy ước số liệu](README.md)).
5. **Soát trước khi commit**: đọc lại diff; câu nào có số phải truy được về evidence; câu khẳng
   định nào chưa đo phải mang dấu "chưa đo". Chạy lại probe nếu sửa script.
6. **Commit** theo quy ước ở §3, push lên `main` (repo cá nhân nghiên cứu; MR không bắt buộc,
   nhưng mỗi commit phải tự đứng được — không commit nửa vời "để mai sửa").

## 2. Scope — cái gì vào git, cái gì không

### Được commit

| Nhóm | Ghi chú |
|---|---|
| `README.md`, `PERFORMANCE-AUDIT.md`, `ROADMAP.md`, `PLAN.md` | luôn cập nhật theo trạng thái thật |
| `docs/**` | đào sâu theo trục; số phải ghi nguồn |
| `reports/**` | audit/benchmark; mỗi file có ngày + phạm vi |
| `scripts/**` | probe/đo chạy được, không phụ thuộc máy |
| `setup/**` | repos.md (name+link+ngôn ngữ) + env.md — đủ để máy khác dựng lại |
| `evidence/*.json` | manifest SHA + kết quả probe (gọn, text) |
| `.gitignore` | giữ chặn đúng nhóm dưới |

### Không commit (đã chặn trong `.gitignore`)

| Nhóm | Lý do |
|---|---|
| `upstream/`, `snapshots/` | clone source ngoài — dựng lại từ `setup/repos.md`, không copy vào git |
| `evidence/pulls.json` | metadata GitHub thô, dung lượng lớn; manifest gọn đã đủ đối chiếu |
| `luannt.md` | ghi chú cá nhân |
| `**/node_modules/`, `*.db`, `*.db-wal`, `*.db-shm`, `.env*` | dependency/dữ liệu/secret tại máy |
| `labs/**/output/`, `/.local/` | output thí nghiệm cục bộ |

## 3. Quy ước commit

- Message tiếng Việt có dấu, dòng đầu ≤ 72 ký tự, dạng: `<đợt>: <làm gì> (<bằng chứng ở đâu>)`.
  Ví dụ: `đợt-1: đo typecheck TS6 vs TS7 trên kho Z (evidence/typecheck-2026-10-26.json)`.
- Một commit một chủ đề; số đo và tài liệu diễn giải số đó vào cùng một commit khi được.
- Không commit key/token bất kỳ; không log secret vào evidence.

## 4. Template bảng kết quả đo (copy vào docs/reports khi cần)

```markdown
| Kịch bản | Phiên bản | Thông số | p50 | p95 | p99 | Ghi chú |
|---|---|---|---|---|---|---|
| typecheck toàn kho | typescript 6.x (JS) | npx tsc --noEmit, kho <tên>, <ngày> | — | — | — | nguồn: đo tại máy |
| typecheck toàn kho | typescript 7.x (native) | cùng lệnh, cùng máy | — | — | — | evidence/<file>.json |
```

Luật điền: mỗi ô số phải truy được về evidence; ô chưa có thì ghi `—` + "chưa đo", không để
trống trông như đã đo. Cột "nguồn" bắt buộc khi số là công bố/ước tính.

## 5. Luật thí nghiệm (giữ kết quả đáng tin)

1. Một thử nghiệm một biến; đổi runtime thì giữ nguyên query/index/logic/durability.
2. Pin version mọi tool; ghi Git SHA + build flag + hostname + ngày trong evidence.
3. A/B xen kẽ nhiều lượt để giảm drift do shared CPU; không ghép percentile hai lượt chạy.
4. Kiểm correctness (dữ liệu ghi/read khớp, không trùng, không mất) trước khi tin số hiệu năng.
5. Load test trên box dùng chung: giới hạn VU/thời gian, tránh đè service thật; ghi rõ giới
   hạn vào kết quả.

## 6. Vai trò khi làm bằng agent nhiều phiên

- Phiên làm đo chỉ làm đo; phiên review đọc lại evidence đối chiếu tài liệu — ai viết số không
  tự duy số mình (vai khác token).
- Mỗi đợt xong cập nhật `ROADMAP.md` (tick đợt) + `MEMORY` ghi chú ngắn nếu có quirk máy.
