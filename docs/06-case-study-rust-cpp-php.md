# Case study — Rust, C++, PHP+C++ ("bùa chú" làm sao để nhanh?)

Ngoài 4 trục trọng tâm. Bài học ở mức **nguyên lý để mượn**, không phải lý do để viết lại hệ.
Bằng chứng trong challenge: [NATIVE-PHP-AUDIT.md](../reports/NATIVE-PHP-AUDIT.md).

## Rust — nhanh nhờ gì

- **Ownership/borrow**: không GC — hủy đúng lúc, biên dịch thời điểm đó đã biết lifetime; p99 không có spike
  GC. (Case kinh điển ngoài challenge: Discord chuyển service Read States Go → Rust vì spike
  GC đều kỳ — nguồn blog Discord 2020, chưa đo lại.)
- **Zero-cost abstraction**: trait/iterator compile xuống code máy như viết tay; LLVM tối ưu.
- **Fearless concurrency**: Send/Sync bắt data race lúc compile.
- Trong challenge: **#19 rust-epoll** — httparse + serde_json + HMAC + SQLite C FFI, completion
  batch qua io_uring, direct descriptors + provided receive buffers (chi tiết luồng ở
  NATIVE-PHP-AUDIT).

Giá trị mang đi: **p99 ổn định không GC** + kiểm soát allocation. Chi phí: build chậm, unsafe
FFI/socket vẫn tự chịu trách nhiệm — Rust không tự miễn nhiễm bug ownership ở phần unsafe.

## C++ — nhanh nhờ gì

- **Kiểm soát thủ công từng byte**: RAII, template/inlining, allocator riêng, SIMD tay.
- Trong challenge: **#8/#9 cpp-epoll** (parser tự viết, EXCLUSIVE + cache 500 trang + mmap,
  checkpoint thread riêng, SIMD escaping), **#15 cpp-uWS**, **#32 cpp-eastl-io_uring-pgo**
  (nhiều ring một thread, pool buffer, PGO SQLite).
- Case ngoài: ClickHouse — vectorized execution + SIMD + cache-aware cho DB analytics.

Giá trị mang đi: trần hiệu năng cao nhất khi có người giỏi giữ. Chi phí: audit thật tìm được
**parser #9 nhận framing mâu thuẫn** (2 Content-Length, CL+TE, HTTP/9.9 — probe tái hiện,
evidence/cpp-parser-probes.json) → tự viết parser = tự nhận toàn bộ rủi ro HTTP. Production nên
giữ server HTTP đã kiểm chứng.

## PHP + C++ ("bùa chú") — nhanh nhờ gì

Bài toán gốc: PHP interpreter chậm, nhưng Facebook/VK chạy hàng tỷ request PHP mỗi ngày. Ba
"phép" thật:

1. **HHVM (Facebook)**: PHP → bytecode HIP → **JIT compile ra code máy** lúc chạy; sau đó chuyển
   sang ngôn ngữ Hack. Case AOT/JIT kinh điển của "PHP tăng tốc bằng C++".
2. **KPHP (VK)**: compile **toàn bộ** PHP → C++ source → binary native (AOT). Nhanh hơn PHP-FPM
   nhiều lần theo README của repo (số công bố, chưa đo lại).
3. **PHP 8 JIT (Zend)**: JIT built-in trong interpreter chính thức.

Trong challenge, bản PHP thắng cao (#24/#28 **php-swoole**) không dùng JIT làm chính:

- **Swoole = C++ reactor** giữ server/socket/HTTP lâu dài; extension native (`hash_hmac`,
  PDO SQLite, `json_encode`) làm việc nặng; PHP chỉ còn **callback điều phối ngắn**.
- App/DB/prepared statements khởi tạo **một lần**, không bootstrap framework mỗi request.
- #28: defer write → BEGIN IMMEDIATE → batch → COMMIT → response; checkpointer process riêng.
- Phản biện đáng học: README #28 tự báo **JIT gần trung tính** — thời gian nằm ở C, bật JIT không
  đổi gì; thử SQLite JSON tại DB xong **bỏ**, vì dựng JSON ở PHP nhanh hơn (số tác giả, chưa đo
  lại). Tối ưu tốt = giả thuyết được đo, không phải checklist bật hết.

Giá trị mang đi: **"ngôn ngữ script + lõi native" là pattern thật** (y hệt Bun/Zig, TS7/Go,
Python/Cython #96). Không có nghịch lý "PHP nhanh hơn Rust" — là C++ làm phần lớn công việc.

## Bảng "bùa chú" chung của mọi ngôn ngữ nhanh

| Bùa chú | Thấy ở |
|---|---|
| AOT compile / JIT đoạn nóng | TS7 (AOT tool), HHVM, KPHP, PHP 8 JIT, PGO #32 |
| Song song hoá khâu độc lập | TS7 goroutines, Go scheduler, io_uring multishot #26 |
| Giảm allocation + buffer tái sử dụng | Rust ownership, EASTL pool #32, Utf8JsonWriter C# #27 |
| Dữ liệu liền mạch cache-friendly | symbol array TS7, range scan #44, ClickHouse |
| Batching IO + group commit | Go #18, C #26, Rust #19, PHP #28 |
| In-process DB (bỏ network hop) | SQLite mọi bản top; Bun `bun:sqlite` |
| SIMD đường nóng | escaping #9, memchr/ripgrep |
| Zero-copy / spans giữ bytes gốc | Rust #19, parser các bản native |
| PGO/LTO theo workload thật | SQLite PGO #32 — tối ưu compiler/workload, không tự lan sang app khác |

## Khi nào KHÔNG dùng case này

- Chưa đo được đoạn nóng → không viết lại bằng native (nguyên lý 9, [docs/00](00-nguyen-ly-hieu-nang.md)).
- Đội không giữ được on-call native (sanitizer/fuzz/lifecycle test) → mượn nguyên lý, không mượn code.
- Bê nguyên parser/auth/transaction của submission benchmark vào production — audit đã chỉ nhiều
  bản thiếu FK/exp/ framing check; benchmark hợp lệ ≠ production hợp lệ.
