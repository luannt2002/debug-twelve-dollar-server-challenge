# Nguyên lý hiệu năng cốt lõi — mindset để debug dự án cũ

Đây là bản rút gọn từ những gì các repo hiệu năng top (và 120 submission của
[twelve-dollar-server-challenge](https://github.com/arjaythedev/twelve-dollar-server-challenge))
làm đúng. Dùng như checklist khi nhận một dự án chậm. Bằng chứng chi tiết nằm ở
[PERFORMANCE-AUDIT.md](../PERFORMANCE-AUDIT.md) và `reports/`.

## 10 nguyên lý

### 1. Đo trước, đổi sau

Mọi repo nhanh đều có văn hoá profile: pprof (Go), `--cpu-prof` (Node), `EXPLAIN (ANALYZE,
BUFFERS)` (PG), k6/autocannon (tải). Sửa thứ không đo được = sửa May mắn.

*Áp vào dự án cũ:* chạy profile 1 luồng thật trước khi đề xuất bất kỳ thay đổi nào. Không viết
số chưa chạy lệnh.

### 2. Giảm số việc trên mỗi request trước khi đổi runtime

Submission top không thắng vì "ngôn ngữ nhanh" — họ thắng vì làm **ít việc hơn mỗi request**:
query ít dữ liệu hơn, bỏ query lặp, ít round trip, ít object trung gian, serialize một lần.

Mô hình Amdahl (ước tính lý thuyết, không phải số đo): 80% thời gian không đổi, 20% được tăng
tốc 2 lần → tổng chỉ nhanh ≈ 1,11 lần. App CPU thường chỉ là một phần critical path; phần còn
lại là DB/network/lock.

*Áp vào dự án cũ:* đếm số query + round trip + serialize/parse lặp của 1 request hot trước khi
nghĩ đến "đổi framework/runtime".

### 3. Phân tầng rõ để sửa đúng tầng

Bốn tầng hay bị nhầm: **ngôn ngữ** (TS) / **compiler-typecheck** (tsc, TS 7) / **runtime**
(Bun, Node, Go) / **DB + kernel** (SQLite, PG, epoll, io_uring). TS 7 nhanh ở tầng typecheck
nhưng không đụng tầng runtime; Bun nhanh ở tầng runtime nhưng không thay typecheck
([docs/04](04-so-sanh-ba-truong-phai.md)).

*Áp vào dự án cũ:* câu chậm thuộc tầng nào? Editor gõ chậm → typecheck. API responding chậm →
runtime/DB. Cài deps chậm → package manager. Chữa sai tầng là lãng phí.

### 4. Concurrency là ngân sách, không phải con số miễn phí

64k VU không phải 64k request đang dùng CPU. 50k goroutine chờ pool 20 connection mà không có
deadline/admission → RAM và tail latency phình vô hạn (PERFORMANCE-AUDIT §6).

*Áp vào dự án cũ:* đếm tổng connections = replica × worker × pool + jobs + migration. Có
deadline trên mỗi request? Có admission khi quá tải, hay queue vô hạn?

### 5. Ownership dữ liệu rõ ràng

#18 (Go) thắng nhờ một chủ connection gom write + group commit — ownership rõ. Ngược lại, nhiều
bản native vỡ vì buffer được trả về pool khi socket vẫn đang dùng.

*Áp vào dự án cũ:* mỗi tài nguyên (connection, buffer, file) có đúng một owner? Ai đóng, khi nào?

### 6. Batching + transaction ngắn + commit trước khi trả response

Group commit chia chi phí transaction/fsync cho nhiều write; nhưng response phải đợi commit
(không trả success trước durable nếu hợp đồng yêu cầu). Batch theo use case tự nhiên
(ingest/import), không gom mọi request độc lập vào một transaction.

*Áp vào dự án cũ:* xem chỗ ghi dữ liệu — mỗi row một transaction? hay giữ transaction mở chờ
gọi HTTP ngoài (vi phạm cả hai nguyên lý)?

### 7. Ít cấp gián tiếp, ít allocation

Nhóm native giữ token dạng spans/borrowed bytes, dựng output trong buffer tái sử dụng, không
tạo cây object đầy đủ rồi serialize lại (NATIVE-PHP-AUDIT §"Rust/C++ nhanh do đâu").

*Áp vào dự án cũ:* tìm serialize-then-parse-again, log full body trên đường nóng, DTO map qua
nhiều lớp. Mỗi lớp gián tiếp phải trả giá được đo.

### 8. Locality + cache-friendly

Range feed (một range scan) thay nhiều B-tree lookup riêng lẻ; dữ liệu cần cùng nhau nằm cạnh
nhau. Index đúng cho cặp sort ổn định (keyset pagination).

*Áp vào dự án cũ:* `EXPLAIN` query hot — bao nhiêu lookup riêng? Có index sort khớp ORDER BY?

### 9. Native hoá chỗ nóng chỉ khi biện minh được

Bun = transpiler + IO viết native (Zig); TS 7 = typecheck viết native (Go); PHP Swoole = C++
reactor làm việc nặng, PHP chỉ điều phối. Chung một mẫu: **viết native cho đoạn nóng, giữ ngôn
ngữ diễn đạt cho phần logic** — nhưng chỉ khi profile chứng minh đoạn đó chi phối.

*Áp vào dự án cũ:* sau khi hết nguyên lý 1-8, nếu đoạn nóng thật sự là CPU native-bound → cân
nhắc worker/service tách/module native. Đừng bắt đầu từ đây.

### 10. Tối ưu không được phá hợp đồng đúng

Các finding thật của audit: parser C++ #9 nhận framing mâu thuẫn (probe tái hiện), vài bản bỏ
kiểm `exp` của JWT, vài bản không bật FK → orphan data, SQLite NORMAL có thể mất write committed
khi mất điện. Tối ưu tốt là giả thuyết được đo **và vẫn đúng khi lỗi**.

*Áp vào dự án cũ:* mỗi tối ưu phải trả lời "lúc quá tải / lỗi DB / client disconnect thì sao?"

## Checklist debug một dự án cũ (thứ tự chạy)

1. Profile một luồng thật (CPU + wall) → xác định tầng chi phối (nguyên lý 1, 3).
2. Đếm query/round trip mỗi request; bắt N+1; projection + keyset pagination (2, 8).
3. Kiểm pool/admission/deadline/timeout; tính tổng connections (4).
4. Rà serialize/parse lặp, log nóng, middleware đọc body nhiều lần (7).
5. Xem pattern ghi: transaction ngắn? group commit chỗ hợp lệ? idempotency khi retry (6, 10)?
6. A/B runtime (Node vs Bun vs Go service tách) cùng code cùng query (3, 9).
7. DB: nếu SQLite → xem [docs/05](05-sqlite-sang-postgresql.md); nếu PG → planner + pool.
8. Đo lại sau mỗi bước; giữ kết quả "không đáng" như kết quả "đáng" — cả hai đều là tri thức.
