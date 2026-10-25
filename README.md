# debug-twelve-dollar-server-challenge

Dự án **debug và học hiệu năng** từ repo
[arjaythedev/twelve-dollar-server-challenge](https://github.com/arjaythedev/twelve-dollar-server-challenge):
hàng trăm người cùng viết một service API (feed / post / like) chạy trên droplet ~$12/tháng —
1 CPU, SQLite in-process, cấm Redis / PostgreSQL / result cache, cấm đổi schema/index,
seed 50k user / 500k post / 2M like, đo bằng k6 với VU có thời gian nghỉ. Điểm là số VU cao nhất giữ được 5 phút với
p95 < 500ms, p99 < 1s, lỗi < 1%; 64k là kết quả nguồn video báo cáo, chưa tái đo tại đây.

Mục tiêu của repo này: **rút nguyên lý tối ưu từ các submission top, biến thành mindset debug
dự án cũ của mình**, với 4 trục chú tâm ghi ở dưới. Kết quả audit và giới hạn phạm vi nằm ở
[PERFORMANCE-AUDIT.md](PERFORMANCE-AUDIT.md).

Repo này **KHÔNG copy code của repo nào vào git.** Source tham khảo clone ở `upstream/` và
xuất snapshot ở `snapshots/` (cả hai đã gitignore). Ở máy khác, dựng lại bằng:
[setup/repos.md](setup/repos.md) (chỉ name + link + ngôn ngữ) và [setup/env.md](setup/env.md).

## Trọng tâm chính — 4 trục (chốt của chủ dự án)

| Trục | Câu hỏi trung tâm | Tài liệu |
|---|---|---|
| 1. TS + Bun | Bun chạy `.ts` kiểu gì, nhanh ở tầng nào, chậm ở đâu? | [docs/01](docs/01-truong-phai-ts-bun.md) |
| 2. TS 7 (typescript-go) | `tsc` viết bằng Go nhanh vì gì — và nó **không** làm gì cho runtime? | [docs/02](docs/02-truong-phai-ts7-typescript-go.md) |
| 3. Go thuần | Go + cái gì (scheduler, netpoller, GC, binary) đạt hiệu năng cao? | [docs/03](docs/03-truong-phai-go.md) |
| 4. SQLite → PostgreSQL | Chuyển DB đổi gì ở **tất cả luồng**: gì giữ nguyên lý, gì thay cơ chế? | [docs/05](docs/05-sqlite-sang-postgresql.md) |

Ngoài 4 trục:

- Rust / C++ / PHP+C++: chỉ rút case study và giá trị — [docs/06](docs/06-case-study-rust-cpp-php.md).
- Nguyên lý chung để debug dự án cũ — [docs/00](docs/00-nguyen-ly-hieu-nang.md).
- So sánh chốt 3 trường phái + trả lời câu hỏi "TS 7 + Bun có phải trùm TS?" — [docs/04](docs/04-so-sanh-ba-truong-phai.md).

## Top repo nào đang được debug?

Bảng đầy đủ (name + link + ngôn ngữ + vai trò + lệnh clone) nằm ở
[setup/repos.md](setup/repos.md). Tóm tắt:

- **Đối tượng debug chính**: `arjaythedev/twelve-dollar-server-challenge` (đa ngôn ngữ, 120
  submission qua 124 PR head) — đã clone đủ + fetch PR refs.
- **4 trục**: `microsoft/typescript-go` (Go), `oven-sh/bun` (Zig + JavaScriptCore),
  `golang/go` (Go), `sqlite/sqlite` + `postgres/postgres` (C).
- **Phụ theo nhu cầu**: framework của các submission top (`gnet`, `fasthttp`, `uWebSockets`,
  `h2o`, `swoole-src`, `tokio`/`axum`…).

## Cấu trúc repo

```text
README.md                  ← file này: tổng chương trình
PERFORMANCE-AUDIT.md       ← audit chính (kết luận, thước đo, luồng, khuyến nghị)
ROADMAP.md                 ← lộ trình các đợt debug/đo
PLAN.md                    ← flow + scope commit + template ghi kết quả
docs/                      ← đào sâu theo trục (nguyên lý → từng ngôn ngữ → DB)
  00-nguyen-ly-hieu-nang.md          mindset debug dự án cũ
  01-truong-phai-ts-bun.md           trục 1
  02-truong-phai-ts7-typescript-go.md trục 2
  03-truong-phai-go.md               trục 3
  04-so-sanh-ba-truong-phai.md       bảng hơn thua + verdict "trùm TS?"
  05-sqlite-sang-postgresql.md       trục 4 — tất cả luồng
  06-case-study-rust-cpp-php.md      ngoài scope — case study
reports/                   ← audit từng nhóm submission (Go, TS/Bun/Node, native/PHP…)
setup/                     ← repos.md + env.md để dựng lại ở máy khác
scripts/                   ← probe đo nhỏ, chạy được độc lập
evidence/                  ← JSON kết quả probe + manifest SHA (pulls.json giữ local)
upstream/                  ← [gitignore] clone repo gốc + typescript-go
snapshots/                 ← [gitignore] source xuất từ từng PR head
labs/                      ← [gitignore output] thí nghiệm cục bộ
```

## Thứ tự đọc khuyên dùng

1. README này → nắm chương trình.
2. [PERFORMANCE-AUDIT.md](PERFORMANCE-AUDIT.md) → kết luận audit đã làm.
3. [docs/00](docs/00-nguyen-ly-hieu-nang.md) → mindset, rồi docs theo trục cần đào sâu.
4. `reports/` → khi cần bằng chứng từng submission cụ thể.
5. [ROADMAP.md](ROADMAP.md) + [PLAN.md](PLAN.md) → khi bắt đầu đợt làm mới.

## Quy ước số liệu (bắt buộc)

Mọi con số trong repo này phải thuộc một trong ba loại, và ghi rõ loại khi dùng:

1. **Đo tại máy này** — phải kèm script trong `scripts/` + JSON trong `evidence/` + ngày đo.
2. **Số công bố của tác giả/repo gốc** — ghi nguồn (README PR, devblog, docs chính thức).
3. **Ước tính / mô hình lý thuyết** — ghi rõ là ước tính, không trình bày như số đo.

Không viết số chưa chạy lệnh ra. Số của bài video/bảng xếp hạng chưa tái hiện được thì ghi rõ
"nguồn báo cáo, chưa đo lại".

## Cái gì được commit vào git

- Được: `README.md`, `PERFORMANCE-AUDIT.md`, `ROADMAP.md`, `PLAN.md`, `docs/`, `reports/`,
  `scripts/`, `setup/`, `evidence/*.json` gọn (manifest + probe).
- Không: `upstream/`, `snapshots/` (dựng lại từ `setup/repos.md`), `node_modules/`, `*.db`,
  `.env`, metadata GitHub thô (`evidence/pulls.json`), file cá nhân (`luannt.md`).
  Chi tiết xem `.gitignore` và [PLAN.md](PLAN.md).

## An toàn khi tái hiện

Không chạy `install.sh` của submission với quyền root, không đổi kernel/sysctl, không tác động
service đang phục vụ trên cùng máy. Probe chỉ chạy trên fixture tự dựng trong `labs/`.

## Dùng lại ở máy khác

1. Clone repo này.
2. Chạy `python3 scripts/setup-sources.py` để dựng source challenge đúng SHA trong manifest
   vào `upstream/` và `snapshots/` đã gitignore; các repo khác xem [setup/repos.md](setup/repos.md).
3. Làm theo [setup/env.md](setup/env.md) → dựng bun/go/TS 7/postgres → chạy lại probe.
4. Bắt đầu đợt mới theo [ROADMAP.md](ROADMAP.md), ghi kết quả theo [PLAN.md](PLAN.md).

## Các submission trọng tâm cần đọc

Đây là danh sách học kỹ thuật, không phải bảng điểm đã tái đo cùng điều kiện. Tất cả nằm trong repo challenge:

| Nhóm | PR | Giá trị cần đọc |
|---|---|---|
| TS thực dụng | [4](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/4), [51](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/51), [80](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/80) | Bun.serve, Fastify batching, Elysia use case/repository |
| TS/native chuyên biệt | [3](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/3), [102](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/102), [119](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/119) | raw TCP, C++ addon, Rust/C FFI; đọc cả finding trước tái dùng |
| Go thực dụng | [18](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/18), [99](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/99) | DB owner/group commit và net/http/pool/query shape |
| Go chuyên biệt | [52](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/52), [72](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/72), [91](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/91) | packed rows, C arenas, bounded writer; có giới hạn correctness phải kiểm |
| Native/PHP | [9](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/9), [19](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/19), [26](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/26), [28](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/28), [32](https://github.com/arjaythedev/twelve-dollar-server-challenge/pull/32) | mmap/cache, io_uring, buffers, checkpoint và Swoole dài hạn |

**TS7 + Bun bổ sung nhau, không bảo đảm runtime nhanh nhất.** TS7 thay compiler/tooling;
Bun chạy app. So TS7 với service Go như hai runtime là sai thước đo.

## Đào sâu Go + chi + PostgreSQL

Đọc [audit từng luồng Go+chi+pgxpool](reports/GO-CHI-POSTGRES-FLOW-AUDIT.md): router, middleware,
admission, connection lifecycle, read/write, idempotency/outbox, Batch/COPY, MVCC/vacuum,
WAL và debug theo triệu chứng. Đây là audit source; benchmark PostgreSQL còn ở roadmap.
