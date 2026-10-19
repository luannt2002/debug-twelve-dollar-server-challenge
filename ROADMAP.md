# ROADMAP — lộ trình các đợt

Nguyên tắc chung: mỗi đợt phải có **giả thuyết → script đo → bằng chứng (`evidence/`) → tài
liệu cập nhật**. Không nhảy đợt. Flow chi tiết và scope commit xem [PLAN.md](PLAN.md).

## Đợt 0 — Tải + audit tĩnh + probe nền (ĐÃ XONG — 19/10/2026)

- Clone `twelve-dollar-server-challenge` đủ lịch sử + fetch 124 PR head;
  xuất `snapshots/pr-N/` (120 thư mục submission).
- Audit tĩnh: [PERFORMANCE-AUDIT.md](PERFORMANCE-AUDIT.md) + 5 report trong `reports/`.
- Probe chạy được: SQLite fixture (FK/snapshot/CHECK), parser C++ #9, Go, TS/Node —
  JSON trong `evidence/`, script trong `scripts/`.
- **Tiêu chí xong**: `evidence/verification.json` xanh. ✅ (19/10/2026)
- **Chưa làm**: chạy 42 official checks cho mọi submission; load test thật; benchmark PostgreSQL.

## Đợt 1 — Trục TS: TS 7 + Bun trên codebase thật

Mục tiêu: chốt được "runtime nào + typecheck nào" cho dự án TS của mình, bằng số đo thay vì
tâm linh.

1. Chọn một codebase TS thật (vd service trong `app_service` hoặc dự án nhỏ độc lập).
2. Typecheck: đo `tsc --noEmit` TS 6 (JS) vs TS 7 (native) cùng lệnh, cùng máy:
   `time npx tsc --noEmit` với `typescript@6` rồi `typescript@7` — JSON vào `evidence/`.
3. Runtime: chạy cùng app trên Node rồi Bun (cùng code, cùng endpoint) — đo startup + p50/p99
   bằng k6/autocannon ở tải thấp-trung bình; **không** vừa đổi runtime vừa đổi query.
4. Ecosystem: chạy typescript-eslint / ts-jest / ts-morph trên TS 7 — ghi cái nào vỡ, cái nào
   cần song song TS 6 (alias `@typescript/typescript6`).
5. Chốt tsconfig mẫu vào `setup/env.md`.

Deliverable: `docs/01` + `docs/02` bổ sung cột "số đo tại máy" cạnh số công bố.
Tiêu chí xong: bảng so sánh có ≥ 1 cặp số đo thật, mọi ô số có lệnh + ngày kèm theo.

## Đợt 2 — Trục Go: service cạnh service TS

Mục tiêu: trả lời "phần nào của hệ đáng tách sang Go", bằng đo chứ không bằng trend.

1. Viết 1 service Go chuẩn (net/http + database/sql + pprof) làm cùng 1-2 endpoint với
   bản TS, cùng schema, cùng seed, cùng durability.
2. Đo A/B xen kẽ (giảm drift shared CPU): throughput, p50/p95/p99, RSS, GC pause, pool wait.
3. Áp lesson #18 (owner actor + group commit) nếu có write contention — đo trước/sau.
4. Kết luận dạng "đoạn nóng X đo được chiếm Y% critical path → đáng/không đáng tách".

Deliverable: `docs/03` + report đo mới trong `reports/` (đặt tên `BENCH-<ten>.md`).
Tiêu chí xong: có số A/B xen kẽ ≥ 2 lượt; kết luận nêu rõ phạm vi workload.

## Đợt 3 — Trục DB: SQLite → PostgreSQL, tất cả luồng

Mục tiêu: chạy checklist 10 luồng trong [docs/05](docs/05-sqlite-sang-postgresql.md) trên
schema thật, ra quyết định giữ SQLite hay chuyển PG cho từng phần dữ liệu.

1. Dựng PG local qua docker (`setup/env.md`); đổi goose migration sang PG dialect.
2. Lần lượt các luồng: connection/pool → transaction/retry → kiểu dữ liệu → dialect SQL →
   index/planner (EXPLAIN ANALYZE) → backup → vector (nếu có RAG).
3. Mỗi luồng ghi: SQL trước/sau, kết quả đo,pitfall gặp thật.
4. Cổng quyết định theo [PERFORMANCE-AUDIT.md §8](PERFORMANCE-AUDIT.md): giữ nguyên lý,
   thay cơ chế; không bê "1 connection cho mọi endpoint" sang PG.

Deliverable: `docs/05` bổ sung cột "đã thử tại máy" + migration sample trong `labs/`.
Tiêu chí xong: 10 luồng đều có trạng thái (đã thử / chưa áp dụng + lý do).

## Đợt 4 — Native học việc: áp 1 bài học, không viết lại hệ

Mục tiêu: chứng minh 1 kỹ thuật từ nhóm native có giá trị thật trong service của mình.

Ứng viên (chọn đúng 1, theo profile đo được ở đợt 1-2): group commit khi write contention;
prepared statement + projection gọn; serialize một lần / buffer tái sử dụng; SIMD escaping
(chỉ nếu profile chỉ ra escaping chi phối).

Deliverable: báo cáo trước/sau có số; nếu không đáng — ghi "không đáng" + số là kết quả hợp lệ.
Tiêu chí xong: một thử nghiệm một biến; correctness check (dữ liệu ghi/read khớp) trước khi tin số.

## Đợt 5 — Playbook tổng kết

Gộp đợt 1-4 thành playbook ngắn (đặt `reports/PLAYBOOK.md`): thứ tự kiểm khi nhận dự án cũ
chậm, kèm số đo mẫu từng bước. Đưa về dự án thật bằng MR theo dây chuyền dự án đó.

## Quản trị rủi ro xuyên đợt

- Box dùng chung: không chạy load test lớn đè service thật; giới hạn VU/duration; chạy lúc rảnh.
- Mỗi đợt tối đa 1 runtime/DB đổi tại một thời điểm; pin version + ghi SHA.
- Số của video/bảng xếp hạng upstream chỉ dùng định hướng, không dùng làm mục tiêu cam kết.
