# Trục 1 — TS + Bun: runtime chạy TypeScript kiểu gì?

Trả lời câu hỏi gốc: **"TS version có Bun hay TS version mới có Go thì tốt hơn?"** — hai thứ
không cùng tầng, không thay nhau (so sánh đủ ở [docs/04](04-so-sanh-ba-truong-phai.md)).

## Bun là gì

Runtime JS/TS thay Node, viết bằng **Zig**, dùng engine **JavaScriptCore** (không phải V8),
gộp luôn: package manager (`bun install`), bundler, test runner, SQLite native (`bun:sqlite`),
`Bun.serve()`, `Bun.file()`.

## Cơ chế chạy file .ts

Bun **transpile (strip types) lúc load** bằng transpiler viết trong Zig — bỏ type annotations
đi và chạy JS thuần trên JavaScriptCore. Nghĩa là:

- **Bun không kiểm tra kiểu.** `bun run file.ts` cho ra kết quả như nhau dù bạn viết TS 6 hay
  TS 7 trong `package.json` — version typescript chỉ dùng khi bạn gọi `tsc`.
- Type của TS không tồn tại lúc chạy: JSON từ internet không tự "đúng type" — vẫn cần runtime
  schema (zod/valibot) + authorization (PERFORMANCE-AUDIT §5).

## Bun nhanh ở đâu (và vì sao)

| Đoạn | Cơ chế |
|---|---|
| Startup + hot reload | transpile Zig rất nhanh, không pipeline tsc, không JIT warmup dài như V8 snapshot |
| IO | `Bun.serve`/`Bun.file` gọi thẳng native; `bun:sqlite` in-process — không TCP, không wire protocol |
| `bun install` | cache cứng + manifest nhanh |
| Deploy | một binary duy nhất, không `node_modules` |

## Bun chậm/đỡ hơn ở đâu

- **Query sync chặn event loop**: `bun:sqlite` chạy nhanh nhưng là sync — query chậm vẫn đóng
  băng toàn bộ loop (PERFORMANCE-AUDIT §5). Bun không biến sync thành async.
- CPU-bound JS lớn (JSON khổng lồ, crypto sync) vẫn chặn thread như Node; worker có chi phí
  copy/message.
- Compatibility: thư viện/driver/TLS/shutdown cần soak test đúng version pin; chọn Bun vì số đo
  ứng dụng, không vì hello-world RPS.

## Trong challenge

Submission Bun: `typescript-bun-xxmohamed012` (#3), `typescript-bun-tbsvttr` (#4), `bun-elysia-*`
(#59, #80) — chi tiết luồng ở
[TS-BUN-NODE-AUDIT.md](../reports/TS-BUN-NODE-AUDIT.md). Không có bản Bun nào đứng nhóm đầu
bảng — xác nhận lại nguyên lý [docs/00 §2](00-nguyen-ly-hieu-nang.md): runtime không cứu được
lượng việc dư mỗi request.

## Khi nào dùng Bun trong dự án thật

- Đáng thử ở **một service tách biệt** trước, code TS gọn + dùng trúng API native
  (`bun:sqlite`, `Bun.serve`).
- Chọn sau khi chạy A/B cùng app, cùng driver, cùng môi trường triển khai (ROADMAP đợt 1).
- Không chọn vì benchmark viral; không bê nguyên khi hệ đang phụ thuộc native module Node sâu.

## Tóm một dòng

Bun giải tầng **runtime** cho TS: chạy nhanh hơn, khởi động nhanh hơn, cài nhanh hơn — nhưng
kiểu TypeScript vẫn phải nhờ `tsc` kiểm, và đó là việc của trục 2.
