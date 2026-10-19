# Trục 2 — TS 7 (typescript-go): tsc viết bằng Go, nhanh vì gì, KHÔNG đụng gì

Repo: [microsoft/typescript-go](https://github.com/microsoft/typescript-go) — công bố 11/3/2025,
**TS 7.0 phát hành 8/7/2026**, npm đang ở dòng `typescript@7` (kiểm 19/10/2026; **TS 6 là dòng
JS cuối cùng** — nguồn: devblog Microsoft + npm).

## Nó làm nhanh cái gì

Chỉ tầng **typecheck / build / editor** (`tsc --noEmit`, LSP, `tsc -b`). Số công bố của team
(nguồn devblogs, **chưa đo lại trên máy này**): build nhanh **8–12x**; VS Code typecheck
~77,8s → ~7,5s (~10x).

## Nó KHÔNG làm gì

- **Runtime không nhanh hơn**: app TS của bạn vẫn chạy bằng Bun/Node trên JS emit. Không có
  "app chạy bằng Go", không có binary Go từ code TS.
- Request API không nhanh theo tỷ lệ build nhanh — hai bài toán độc lập (PERFORMANCE-AUDIT §5).

→ Trả lời luôn câu "TS 7 có Bun hay không có Bun": **Bun vẫn giữ nguyên vai trò runtime; TS 7
chỉ thay `tsc`.** Hai cái ghép trực tiếp, không giẫm nhau vì Bun không gọi tsc khi chạy file.

## Vì sao viết bằng Go lại nhanh được (bùa chú cụ thể)

1. **Song song thật**: scanner/parser/checker chia việc qua goroutines — tsc JS vốn bị khóa một
   luồng event loop cho phần lớn khâu.
2. **GC áp lực thấp hơn nhiều**: AST của kho lớn là hàng chục triệu object JS nằm trên heap Node;
   struct Go cấp phát dự đoán được, GC quét rẻ hơn.
3. **Dữ liệu liền mạch, ít con trỏ gián tiếp**: symbol links dạng array thay object graph —
   cache-friendly (cùng mẫu với [docs/00 §7-8](00-nguyen-ly-hieu-nang.md)).
4. **Binary native**: không startup Node, không JIT warmup, không `node_modules` để chạy tsc.

Không phải "Go thần thánh" — là kiến trúc song song + giảm allocation, dùng đúng đặc tính Go
(goroutine, struct). Chính pattern này là case học cho đợt 2 (tách service Go).

## Breaking changes cần biết (nguồn devblog/báo cáo TS 7)

| Đổi gì | Ảnh hưởng | Việc phải làm |
|---|---|---|
| Gỡ `moduleResolution: node` / `node10` | tsconfig cũ vỡ | dùng `bundler` / `node16` / `nodenext` (bun init mặc định `bundler`) |
| `types` mặc định rỗng `[]` | `Bun.serve()`, `Bun.file()`… báo thiếu kiểu | khai báo `"types": ["bun"]` + cài `@types/bun` |
| Compiler API đổi | typescript-eslint, ts-morph, ts-jest vỡ | đợi bản hỗ trợ 7.1+; tạm thời chạy song song TS 6 (alias `@typescript/typescript6`) |

## Cấu hình chuẩn với Bun (copy cho đợt 1)

Xem [setup/env.md §2](../setup/env.md) — `bun add -d typescript@7 @types/bun`,
`moduleResolution: bundler`, `types: ["bun"]`, script `typecheck: tsc --noEmit`,
CI chạy `bun run typecheck`, app chạy `bun run src/index.ts`.

## Tactic debug dự án cũ với TS 7

1. **Dùng TS 7 làm đèn soi nhanh**: typecheck toàn kho 10x nhanh hơn → nhận dự án lạ, chạy
   `tsc --noEmit` trước để thấy toàn bộ nợ kiểu trong vài giây-chục giây thay vì vài phút.
2. Giữ TS 6 song song cho tool chưa nâng (eslint/ts-jest) — không cần chờ 7.1 mới bắt đầu.
3. Pin `typescript@7.0.x` đầu dòng — bản 7.x đầu có thể dính bug; ghi version vào evidence khi đo.

## Tóm một dòng

TS 7 = tsc native: **cùng ngữ cảnh kiểm kiểu, nhanh hơn ~10x (số công bố)** vì song song hoá +
GC rẻ + ít gián tiếp; runtime của bạn không đổi — muốn runtime nhanh thì đó là việc của Bun
(trục 1) hoặc Go (trục 3).
