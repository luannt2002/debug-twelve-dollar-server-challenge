# Audit nhóm native và PHP: học cơ chế, giữ đúng giới hạn

Ngày lấy mã: 19/10/2026. SHA từng PR ở `../evidence/pr-manifest.json`. Đây là audit source các luồng chọn lọc, không phải chạy lại bảng xếp hạng video. PR head hiện tại có thể đã khác phiên bản được quay.

## Các bản cần đọc và luồng chính

| Bản | Đường đọc dưới snapshots | Luồng và lợi ích | Giới hạn production |
|---|---|---|---|
| C++ epoll #8 | `pr-8/submissions/cpp-epoll-khalefa-ow/src/main.cpp` | epoll → parser/view → JWT HMAC → prepared SQLite → bytes; ghi autocommit chạy RETURNING tới DONE; checkpoint thread riêng | Parser tự viết; SQLite sync chặn loop khi query chậm |
| C++ epoll v2 #9 | `pr-9/submissions/cpp-epoll_inmem-khalefa-ow/src/main.cpp` | Như #8; EXCLUSIVE, cache 500 trang + mmap, checkpoint sau batch, SIMD escaping | Tên thư mục inmem dễ gây hiểu lầm: mã này vẫn SQLite file. Không nhầm với memstore #21 |
| C++ uWS #15 | `pr-15/submissions/cpp-uwebsockets-v2-tbsvttr/server.cpp` | uWS nhận HTTP → auth → SQLite; BEGIN IMMEDIATE; defer COMMIT; queue sở hữu response bytes, đánh dấu onAborted; cả read trong transaction đợi commit | Có ngưỡng retire connection 60k ở head; queue/batch cần giới hạn và đo khi mở rộng workload |
| Rust #19 | `pr-19/submissions/rust-epoll-scooter1337/src/{main,db,uring,net}.rs` | httparse + serde_json + HMAC → SQLite C FFI; completion batch dưới Mutex<App> → COMMIT → flush → checkpoint; direct descriptors + provided receive buffers | Head hiện tại dùng nhiều issuer cùng connection serialized, không còn mô tả đơn giản một event loop. Không suy từ Rust sang an toàn tuyệt đối của unsafe/FFI |
| C io_uring #26 | `pr-26/submissions/c-iouring-raoz/src/server.c` | multishot accept/recv → parser → SQLite inline; nhóm write, trì hoãn response đọc/ghi trong transaction; quản lý memory pressure và backpressure | Header/crypto/JSON tự viết; read proc meminfo khác với budget cgroup; cần kiểm tra dưới giới hạn container thực |
| C++ EASTL #32 | `pr-32/submissions/cpp-eastl-io_uring-pgo-hendy643/src/{app,db,server,http,jwt}.cpp` | nhiều ring do một thread vận hành, pool buffer, range feed có fallback, PGO SQLite, batch completions | Chuyên biệt Linux/io_uring; các số local dùng nhiều generator và hold ngắn, không thay điểm chính thức |
| Zig #25 | `pr-25/submissions/zig-usockets-tbsvttr/src/{app,main}.zig` | uSockets + picohttpparser → std JSON/crypto → SQLite, nhóm transaction và giữ response phụ thuộc commit | Giới hạn 60k connection hiện là budget, không phải giới hạn ngôn ngữ; cần đo cả reconnect |
| Fortran #16 | `pr-16/submissions/fortran-microhttpd-tbsvttr/server.f90` + `bridge.c` | C HTTP bridge → Fortran dispatch → C HMAC + SQLite JSON validation/extraction → SQLite writes → app_flush trước release | Không đúng khi nói toàn bộ verify chữ ký nằm trong SQL: crypto_verify làm HMAC, SQL trích/check claims |
| C# #27 | `pr-27/submissions/csharp-aspnetcore-maks-march/{Program,FeedApp,Db,Jwt,Json}.cs` | Kestrel low-level IHttpApplication, pooled contexts/Utf8JsonWriter, stackalloc crypto, serialized SQLite | Đã đọc toàn bộ năm file ứng dụng; chưa chạy .NET. SQLite đồng bộ dưới lock trên I/O thread; read/encode trong lock làm tăng khoảng chặn |
| PHP #24 | `pr-24/submissions/php-swoole-mattsplat/server.php` | Swoole BASE reactor → PHP callback → native hash_hmac/PDO SQLite/json_encode → response; autocommit | Không có vòng đời framework mỗi request; workload DB nóng và ngắn rất hợp |
| PHP #28 | `pr-28/submissions/php-swoole-tzimpel/server.php` | Swoole BASE → callback → defer Writes::flush → BEGIN IMMEDIATE → từng write → COMMIT → response; checkpointer process riêng | Read handler trả ngay; ở mã này write thực thi trong flush đồng bộ nên không có khoảng callback read chen giữa write và commit. Không quy chung lỗi leak của kiến trúc khác cho bản này |

Phạm vi: đã đọc source xử lý DB/auth/dispatch/batching chính nêu trên; chưa đọc từng dòng thư viện bên thứ ba, toàn bộ parser/SIMD/ownership branches của mọi bản, chưa chạy sanitizer hoặc build đầy đủ nhóm native. C# đã đọc năm file ứng dụng. Không có cơ sở gọi đây là chứng nhận production.

## Phát hiện cần sửa trước khi lấy nguyên mã đi dùng

### 1. C++ #9 chấp nhận framing HTTP mâu thuẫn — đã tái hiện ở parser

`src/main.cpp:1004` bắt đầu parse_request; vòng header ghi đè content_length khi lặp, sau đó ưu tiên chunked nếu có. Probe trích **nguyên văn** các hàm parser, biên dịch g++ không cần SQLite/OpenSSL, cho kết quả:

- Hai Content-Length khác nhau: nhận `kOk`, body `{}`.
- Có cả Content-Length và Transfer-Encoding chunked: nhận `kOk`.
- HTTP/9.9: nhận `kOk`.

Tái lập: `python3 scripts/probe-cpp-parser.py`; output `evidence/cpp-parser-probes.json`. Đây là kiểm tra hàm parser, chưa phải exploit request smuggling qua proxy thật. Parser bất đồng với một hop trước/sau có thể gây mất đồng bộ request; cần parser chuẩn hoặc reject framing mâu thuẫn, duplicate auth và version không hỗ trợ. Khi đi production nên giữ HTTP server đã được kiểm chứng thay vì bê nguyên parser này.

### 2. Một số bản không yêu cầu exp tồn tại

C++ #8 `src/main.cpp:576` chỉ check exp nếu không phải NONE/NULL. PHP #28 `server.php:104` dùng isset(exp); absent hoặc null bỏ qua check. Token đúng chữ ký nhưng thiếu expiry vì thế được nhận. SPEC nói verify exp nhưng test gốc không thử missing/null expiry. Production phải chốt policy token cụ thể, yêu cầu exp, kiểm issuer/audience theo trust boundary, không tự coi mọi optional claim là vi phạm benchmark. Rust #19 hiện dùng `claims.exp.ok_or(...)`, nên không mắc chính trường hợp này.

### 3. FK bị bỏ qua trong một số luồng C++/PHP

C++ #8/#9/#32 và PHP #28 không bật `PRAGMA foreign_keys=ON` tại phần mở DB được đọc. Với SQLite mặc định trên máy kiểm tra, REFERENCES không tự bật enforcement: một JWT hợp lệ cho user không tồn tại có thể tạo orphan post. Probe fixture `scripts/probe-sqlite.py` xác nhận cơ chế FK OFF nhận orphan, ON từ chối. Đây là probe ngữ nghĩa engine, không chạy từng server; runtime compile defaults khác cần xác nhận bằng PRAGMA của connection thật. Contest không kiểm user tồn tại; production không được coi chữ ký JWT thay cho kiểm trạng thái tài khoản/tenant.

## Rust/C++ nhanh do đâu?

Không có một biến độc lập tên “Rust”. Các đường native giảm đồng thời nhiều loại công việc:

1. HTTP → handler ngắn, tránh proxy và middleware trên chính một CPU.
2. Token giữ spans/borrowed bytes, tái sử dụng HMAC key state, vẫn verify mỗi request.
3. SQLite ở cùng process: không TCP DB, không encode/decode wire protocol, không scheduling backend DB riêng.
4. Prepared statements giảm chuẩn bị SQL; index giúp mỗi lookup nhỏ. SQL count likes vẫn có chi phí theo số likes thật.
5. Range feed biến nhiều lần tìm B-tree thành scan có locality, nhưng kiểm live IDs và fallback khi dữ liệu không phù hợp.
6. Không tạo cây object đầy đủ rồi serialize; dựng output trong buffer tái sử dụng. SIMD scan chuỗi giúp thêm ở đường nóng.
7. Group commit chia overhead transaction, không trả response trước commit.
8. io_uring batching giảm số lần submit/wake; direct descriptors và lazy receive buffers giảm overhead giữ idle sockets.
9. PGO/LTO tối ưu nhánh gọi thật; đây là tối ưu compiler/workload, không tự chuyển thành mức tăng cho service khác.

Đổi mmap/cache không có một công thức chung: #9 giảm cache còn 500 trang; #26 head lại chủ động tắt mmap mặc định và đặt cache 128 MiB vì profile khác. Sao chép một PRAGMA không thay thế profile.

## PHP + C++ vì sao có thể nhanh?

Trong PHP Swoole, C/C++ đảm nhiệm reactor/socket/HTTP và các extension native làm crypto/SQLite/JSON; PHP chỉ điều phối một handler ngắn. App/DB/statements khởi tạo một lần, không bootstrap Laravel theo mỗi request. Đây là nguyên lý runtime dài hạn, không có bằng chứng PHP interpreter đã nhanh hơn native Rust ở cùng thao tác.

#28 tự báo cáo JIT gần trung tính vì phần lớn thời gian ở C. README cũng báo thử SQLite JSON chậm hơn cách dựng ở PHP. Đây là số tác giả tự đo trên môi trường riêng, chưa tái đo ở đây. Không dùng để suy ra “JIT + SQL JSON luôn nhanh”. Việc vá Swoole để giải phóng receive buffers nhàn rỗi giải quyết memory/connection cụ thể; khi đưa production nên ưu tiên bản upstream đã sửa và regression test cho patch.

## Độ tin cậy của dữ liệu kèm source

Rust #19 có IO_URING.md/BENCHMARKS.md/raw gzip; C #26 có số nhiều cloud; C++ #32 dùng Ryzen, k6 và raw generator, hold 90/120 giây; Zig #25 có benchmark-results/scoring/capacity JSON. Những artifact này hữu ích để truy nguyên, nhưng đều là số nguồn báo cáo. Không cộng chúng thành một bảng xếp hạng thống nhất.

Checkpoint chạy “sau response” chỉ dời stall sang request sau, không xóa thời gian. NORMAL không bảo đảm mọi acknowledged write tồn tại sau power loss. SIGKILL app và crash hệ điều hành/mất điện là hai phép thử khác nhau. Tổng RAM cần tính RSS/PSS/cgroup, OS page cache và kernel sockets; không lấy anonymous heap so với RSS toàn process của bản khác.

## C# raw Kestrel: đường đi đã kiểm source

Program cấu hình inline socket completions rồi StartAsync FeedApp; CreateContext tái dùng features; Handle route và Jwt.Verify; Db giữ một connection/lock, RETURNING được Read tới DONE; Json.Rent trả pooled writer và chỉ Return sau await Stream.WriteAsync. Giữ Kestrel giúp không phải tự parse HTTP. Không có app group commit ở bản này: mỗi insert autocommit. Cần phân biệt lợi ích từ context/buffer pooling với việc thực thi query đồng bộ trên I/O thread; query chậm vẫn kéo cả loop/lock.

FeedApp.CreatePostAsync dùng trimmed.Length đếm UTF-16 thay vì code points: 500 emoji hợp lệ theo length SQLite có thể bị từ chối. Db.cs tắt FK rõ ràng. Jwt.IsHs256Header trả ngay khi thấy alg thay vì consume cả JSON; ParsePayload không yêu cầu exp và không kiểm trailing bytes sau EndObject. Đây là giới hạn static cần test malformed signed token/duplicate claims nếu tái dùng, chưa chạy .NET. Json pool/context pool không có giới hạn retention nên cần đánh giá peak concurrency và high-water memory trong service lâu dài.
