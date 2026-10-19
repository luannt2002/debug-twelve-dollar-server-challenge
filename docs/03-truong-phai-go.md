# Trục 3 — Go thuần: Go + cái gì để nhanh và ổn định?

Câu hỏi gốc: **"golang + cái gì để nhanh được như thế?"** — trả lời bằng 6 cấu phần của runtime
Go, rồi rút bài học thật từ các submission Go của challenge.

## 6 cấu phần tạo hiệu năng của Go

1. **Goroutine + scheduler n:M (work-stealing)**: hàng trăm nghìn goroutine trên vài thread OS;
   tạo/switch rẻ. Nhưng goroutine **không phải ngân sách concurrency vô hạn** — 50k goroutine
   chờ pool 20 connection vẫn phình RAM + tail (PERFORMANCE-AUDIT §6).
2. **Netpoller**: epoll (Linux) / kqueue (BSD, macOS) tích hợp vào runtime — mỗi connection một
   goroutine mà không tốn một thread OS; blocking IO của goroutine chỉ treo goroutine, không treo
   thread.
3. **GC thế hệ hiện đại**: concurrent mark-sweep, pause thường sub-ms (nguồn go.dev — chưa đo
   lại tại máy này); thiết kế ưu tail latency hơn throughput thuần. `GOMEMLIMIT` phải chừa phần
   OS/cgo/SQLite/socket, không đặt bằng cả container RAM.
4. **Escape analysis + stack allocation**: biến không "thoát" nằm trên stack — không qua GC;
   compiler SSA + inlining tự động cho đường nóng.
5. **Static binary**: deploy không runtime, không `node_modules`, không warmup — hợp server $12
   không có RAM cho cả app lẫn runtime phình.
6. **Văn hoá đo built-in**: `pprof`, `trace`, `runtime/metrics` chuẩn từ đầu — nguyên lý 1 của
   [docs/00](00-nguyen-ly-hieu-nang.md) có sẵn công cụ.

## Bài học thật từ submission Go của challenge

Chi tiết 16 bản ở [GO-AUDIT.md](../reports/GO-AUDIT.md); cốt lõi:

- **#18 (`go-nethttp-tbsvttr`)**: net/http → queue 1024 → **một DB actor (owner)** gom batch
  256 → commit → response. Sự rõ ràng về ownership + chia chi phí transaction là giá trị lớn
  nhất, không phải tốc độ thô.
- **#44 (`go-stdlib-vkrishna03`)**: epoll + range scan feed — locality thay nhiều B-tree lookup.
- **#72/#76/#91**: đã gần như server chuyên dụng Go+C — đổi cả HTTP stack lẫn lượng C bên dưới.
  **Không quy chênh lệch cho GC hay scheduler** khi C engine làm parse/SQL/JSON.

Kết luận GO-AUDIT: bước nhảy của nhóm đầu đến từ **số việc mỗi request + chi phí mỗi connection
+ SQLite + kernel**, không phải chỉ "viết bằng Go". Go thường tạo binary đơn giản, nhưng số
goroutine không sửa query sai, fan-out vô hạn hay pool vô hạn.

## Go vs Bun/Node — ranh giới thực dụng

| Tình huống | Chọn |
|---|---|
| API nghiệp vụ, thời gian chủ yếu ở DB/network, cần hệ sinh thái + tốc độ phát triển | TS (Bun/Node) giữ nguyên |
| Đoạn nóng đo được: CPU work, stream, hàng chục nghìn connection, cần p99 gắt | service Go tách riêng |
| Vài phép nối chuỗi chậm | đừng tách RPC — hop mạng đắt hơn phần tiết kiệm (PERFORMANCE-AUDIT §1) |

## Khi nào Go KHÔNG giúp

- Query sai / N+1 / fan-out vô hạn — Go nhận lại đúng nợ đó.
- Workload I/O-bound đơn giản mà team đã rành TS — chi phí chuyển + on-call > lợi ích.
- Mà không đo: "Go phải thắng Bun" là mục tiêu đặt trước — GO-AUDIT ghi rõ điểm 22k cũ đo một
  phiên bản + workload + ngưỡng connection cụ thể, không phải trần Go.

## Tóm một dòng

Go = goroutine + netpoller + GC low-latency + static binary + văn hoá profile; thắng ở
**concurrency có kiểm soát và tail ổn định** — nhưng submission top thắng nhờ giảm việc mỗi
request trước, Go chỉ là phương tiện giữ đà đó.
