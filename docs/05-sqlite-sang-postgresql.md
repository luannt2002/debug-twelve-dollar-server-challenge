# Trục 4 — SQLite → PostgreSQL: đổi gì ở tất cả luồng

Câu hỏi gốc: **"từ SQLite có gì hay — nếu chuyển qua PostgreSQL thì lợi hại gì?"**. Trả lời theo
nguyên tắc đã chốt ở [PERFORMANCE-AUDIT §8](../PERFORMANCE-AUDIT.md): **giữ nguyên lý, thay cơ
chế**. Tài liệu này liệt kê đủ các luồng cần soi khi chuyển; đợt 3 của [ROADMAP](../ROADMAP.md)
để chạy thử từng luồng trên schema thật và ghi trạng thái vào đây.

## 0. Khác biệt bản chất (gốc của mọi khác biệt khác)

| | SQLite | PostgreSQL |
|---|---|---|
| Hình thái | in-process, gọi hàm C | client-server qua network/protocol |
| Writer | **một** writer tại một thời điểm (WAL: nhiều reader + 1 writer) | **nhiều writer song song** (MVCC) |
| Kiểu dữ liệu | dynamic (type affinity) | static, bắt kiểu chặt |
| Triển khai | 1 file, zero-config, RAM ~0 | server process + RAM riêng (trên server $12: phải tune) |
| Backup | copy file / `.backup` | pg_dump / WAL archiving / PITR |

SQLite "hay" ở: không network hop (gọi hàm thay vì protocol), đọc cực nhanh cục bộ, RAM gần
bằng 0, hợp edge/local-first. Chính vì thế các submission native thắng: SQLite cùng process rút
ngắn đường đi của mỗi request (PERFORMANCE-AUDIT §4).

## 1. Mười luồng cần soi khi chuyển

### 1.1 Kết nối & pool
- SQLite: 1 process 1 file, không pool. PG: **pool có giới hạn** mỗi process.
- Tổng connections = replica × worker × max pool (+ jobs/admin/migration) — tính trước, không để
  mặc định vô hạn. Cần pgbouncer khi process nhiều.
- Không bê pattern "một connection, một hàng đợi cho mọi endpoint" sang PG — serialize quá mức
  (PERFORMANCE-AUDIT §1).

### 1.2 Transaction & isolation
- `BEGIN IMMEDIATE` của SQLite (giữ write lock từ đầu) ↔ PG: lock nhận khi đụng row; conflict ra
  serialization/deadlock error → **phải có retry** có idempotency.
- Semantics khác nhau đã probe tại máy (evidence/sqlite-probes.json): SQLite cùng connection thấy
  write chưa commit mà connection khác không thấy; read transaction giữ snapshot cũ tới COMMIT;
  **một CHECK lỗi không hủy peer statement**. PG: statement lỗi đưa transaction vào aborted →
  phải ROLLBACK, không ghi tiếp được. Không bê batch logic SQLite sang PG nguyên trạng.

### 1.3 Kiểu dữ liệu
- SQLite chôn `'123'` vào cột INTEGER vẫn chạy (affinity); PG báo lỗi kiểu. Rà mọi insert/compare
  bind theo đúng kiểu.
- boolean / timestamp / jsonb / uuid / numeric: SQLite dùng INTEGER/TEXT đại diện → PG có kiểu
  riêng; chọn sai kiểu sẽ trả giá ở index + so sánh.

### 1.4 SQL dialect
| SQLite | PostgreSQL |
|---|---|
| `PRAGMA ...` | `SET` / config server (không có PRAGMA) |
| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT (key) DO UPDATE/NOTHING` (semantic khác REPLACE delete+insert!) |
| `AUTOINCREMENT` | `GENERATED ALWAYS AS IDENTITY` |
| datetime functions riêng | `timestamptz` + functions chuẩn |
| `RETURNING` | có cả hai (SQLite ≥ 3.35) — giữ được |

### 1.5 Migration tooling
- goose hỗ trợ cả hai (app_service đã dùng goose) — migration file phải viết lại phần dialect;
  phần dữ liệu lớn cần batch migration + downtime plan (COPY cho bulk).

### 1.6 Index & planner
- SQLite: planner đơn giản, tự dùng index ổn định. PG: planner thống kê + `ANALYZE` — kế hoạch
  thay đổi theo dữ liệu; phải đọc `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu thật (skew làm đổi
  plan).
- Thêm loại index PG không có ở SQLite: GIN (jsonb/full-text), GiST, BRIN, partial index,
  covering (INCLUDE). Keyset pagination giữ nguyên nguyên lý.

### 1.7 Concurrency write
- Một writer SQLite biến thành lock wait/deadlock PG khi nhiều writer — cần thứ tự lock ổn định,
  transaction ngắn, hot row (vd counter like trên 1 row) phải tách (counter table / batch).

### 1.8 Durability & backup
- SQLite `synchronous=NORMAL` có thể mất write committed khi mất điện; FULL là hợp đồng khác
  (nguồn sqlite.org pragma docs; SIGKILL app không chứng minh power-loss).
- PG: `synchronous_commit` / `commit_delay` là knob cần bằng chứng, không bật mù; commit local
  durable ≠ acknowledgment replication. Backup: pg_dump định kỳ + WAL archiving (PITR) thay cho
  copy file.

### 1.9 Luồng nghiệp vụ mẫu (feed / like / create)
- Query feed 20 bài + count like: mẫu SQL PG ở PERFORMANCE-AUDIT §8 (CTE LIMIT trước, count qua
  index) — **chưa chạy trên PG trong phiên audit**, phải EXPLAIN trước khi tin. Exact count đắt
  khi like hàng triệu → counter table / read model nếu chấp nhận trễ.
- create/like: validate/auth trước, transaction ngắn, unique constraint bắt duplicate like,
  COMMIT rồi trả response; retry theo idempotency key; outbox cho event (PERFORMANCE-AUDIT §8).

### 1.10 Vector / RAG (nếu áp cho CRM RAG)
- sqlite-vec ↔ **pgvector**: cosine ops, index HNSW/IVFFlat, filter kết hợp ACL/tenant ngay trong
  query SQL — lợi thật của PG khi cần multi-tenant + metadata filter. Chưa thử tại máy này.

## 2. Lợi — hại tổng hợp theo bối cảnh

**Chuyển sang PG có lợi khi**: nhiều writer/tenant song song; cần truy cập từ nhiều máy; cần
jsonb/GIN/full-text/pgvector; cần PITR/replication; dữ liệu lớn hơn RAM của một file lock.

**Giữ SQLite có lợi khi**: 1 writer (local app, edge, CLI), đọc chiếm đa số, RAM nghèo (server
$12 — PG cần RAM tune: shared_buffers nhỏ, connection ít), latency in-process là trụ cột
(challenge chứng minh giá của nó).

**Hại phải nhận khi chuyển**: thêm một server để vận hành + backup + giám sát; mất latency
in-process (hop TCP + protocol); semantics transaction/kiểu dữ liệu phải sửa thật (mục 1.2-1.4);
RAM trên máy rẻ là ngân sách thật.

## 3. Trạng thái thử tại máy (cập nhật theo đợt 3)

| Luồng | Trạng thái |
|---|---|
| 1.1 pool | chưa thử |
| 1.2 transaction/retry | probe SQLite xong (evidence/sqlite-probes.json); PG chưa |
| 1.3-1.4 kiểu + dialect | chưa thử |
| 1.5 goose | chưa thử |
| 1.6 planner | chưa thử (mẫu SQL đã có, cần EXPLAIN) |
| 1.7-1.8 lock/durability | chưa thử |
| 1.9 luồng nghiệp vụ | chưa thử |
| 1.10 pgvector | chưa thử |
