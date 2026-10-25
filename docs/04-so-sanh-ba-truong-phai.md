# So sánh 3 trường phái: TS+Bun vs TS7(Go) vs Go — và "trùm TS" là ai?

## Bảng hơn thua

| Chiều | TS + Bun | TS 7 (typescript-go) | Go thuần |
|---|---|---|---|
| Tầng đảm nhiệm | **runtime** chạy code | **typecheck + editor + build** | **runtime** service nền |
| Viết bằng | Zig + JavaScriptCore | Go (native binary) | Go (native binary) |
| Typecheck | ❌ strip types lúc load | ✅ ~10x nhanh hơn TS 6 (số công bố) | không liên quan (ngôn ngữ khác) |
| Runtime throughput | nhanh hơn Node ở IO/startup (tùy app, phải đo) | không đổi (không đụng runtime) | mạnh ở concurrency + p99 gắt |
| GC | JavaScriptCore GC | GC Go (phía tool, không ảnh hưởng app) | GC Go low-latency (phía app) |
| Deploy | 1 binary + lockfile | `tsc` native, không node_modules | 1 static binary |
| Ecosystem rủi ro | Node API compat, native module | tool compiler API chờ 7.1; tsconfig vỡ chỗ node10 | team phải biết Go; on-call thêm một ngôn ngữ |
| Đo lường | pprof Node-style + Bun metrics | thời gian typecheck | pprof/trace built-in |

**Đọc đúng bảng**: Bun và TS 7 **không cạnh tranh nhau** (khác tầng); cặp Bun + TS 7 cạnh tranh
với phương án "Node + tsc JS". Go cạnh tranh ở tầng service runtime với Bun/Node — và thường
thắng khi cần p99 gắt, concurrency lớn, binary đơn giản; thua về tốc độ phát triển API nghiệp vụ
và hệ sinh thái TS.

## Trả lời: "TS 7 + Bun = trùm của TS?"

**Ở tầng toolchain TS — gần đúng**: hiện nay (10/2026) combo `bun` chạy + `typescript@7` kiểm là
setup tốt nhất cho dev TS: typecheck/editor nhanh ~10x (số công bố, chưa đo lại), runtime nhanh
hơn Node ở đa số IO/startup, cài package nhanh. Ba điều giữ tử tế:

1. TS 7 không làm app chạy nhanh hơn — "trùm" chỉ đúng cho khâu kiểm kiểu + editor + CI.
2. Runtime "trùm" hay không phải đo trên **app thật** (driver, TLS, shutdown, telemetry) —
   Bun có thể thua Node ở vài native module/compat; ROADMAP đợt 1 để làm việc này.
3. Tool hệ sinh thái (typescript-eslint, ts-jest, ts-morph) còn nợ bản tương thích 7.1 — cần
   song song TS 6 tạm thời.

**Ở tầng runtime backend thuần**: không có "trùm" miễn phí. Thứ tự thắng của challenge chứng
minh lại: nhóm đầu là C/C++/Rust/Go rất chuyên biệt hoá — vì họ làm ít việc nhất mỗi request
(và chấp nhận rủi ro correctness mà audit đã chỉ ra). Bun đứng giữa bảng. Go service tách riêng
là cầu hợp lý khi TS không đủ ở một đoạn nóng đo được.

## Thứ tự ưu tiên cho server ~$12 (1-2 vCPU, ít RAM)

1. Giảm việc mỗi request (query/index/round-trip) — giá rẻ nhất, lợi lớn nhất.
2. Pattern DB đúng cho engine đang dùng ([docs/05](05-sqlite-sang-postgresql.md)); trên máy ít
   RAM, PostgreSQL ăn RAM — SQLite vẫn dùng page cache, mmap, native heap và kernel memory; lợi thế là không cần process DB server riêng.
3. A/B runtime (Node vs Bun) cùng code — chỉ đổi khi đo được.
4. Tách service Go cho đoạn nóng đo được — cuối cùng, khi 1-3 đã khai cạn.
5. Native/Rust/C++ — chỉ khi profile + latency SLA + năng lực vận hành cùng biện minh
   ([docs/06](06-case-study-rust-cpp-php.md)).

## Tóm một dòng

Ba trường phái là ba tầng ghép được: **Bun chạy, TS 7 kiểm, Go giữ phần nền nóng** — "trùm TS"
không có kết luận chung cho mọi ứng dụng; còn hệ thống nhanh thật thì luôn bắt đầu từ giảm việc, không bắt
đầu từ ngôn ngữ.
