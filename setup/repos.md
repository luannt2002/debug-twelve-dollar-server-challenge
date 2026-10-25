# setup/repos.md — danh mục repo tham khảo (name + link + ngôn ngữ)

Mục đích: **repo này không copy source ngoài vào git.** Ở máy khác, đọc file này, clone những
repo cần sang thư mục tools riêng (vd `~/opensource/tools/`), rồi làm theo [env.md](env.md).

Lệnh clone gợi ý dùng `--filter=blob:none` cho repo lớn (chỉ cần đọc code, không cần toàn bộ
blob lịch sử). Repo challenge thì clone đủ + fetch PR refs theo lệnh ở dưới.

## Nhóm 1 — đối tượng debug chính

| Name | Link | Ngôn ngữ | Vai trò | Ghi chú clone |
|---|---|---|---|---|
| twelve-dollar-server-challenge | https://github.com/arjaythedev/twelve-dollar-server-challenge | đa ngôn ngữ (120 submission: Go, TS/Bun, Rust, C++, C, Zig, PHP, Java, C#…) | **Đối tượng debug chính** — bài toán 1 CPU + SQLite + 64k VU | clone đủ lịch sử + fetch `refs/pull/*/head` (lệnh bên dưới) |

```bash
git clone https://github.com/arjaythedev/twelve-dollar-server-challenge upstream/twelve-dollar-server-challenge
cd upstream/twelve-dollar-server-challenge
git fetch origin '+refs/pull/*/head:refs/remotes/origin/pr/*'
# 124 PR head nằm dưới refs/remotes/origin/pr/N — xuất snapshot như scripts/ đã làm
```

## Nhóm 2 — 4 trục trọng tâm

| Name | Link | Ngôn ngữ | Trục | Vì sao đưa vào |
|---|---|---|---|---|
| typescript-go | https://github.com/microsoft/typescript-go | Go | 2 — TS 7 | compiler + typechecker TS viết native bằng Go; đọc cấu trúc song song hoá |
| bun | https://github.com/oven-sh/bun | Zig + JS (dùng JavaScriptCore) | 1 — TS + Bun | runtime chạy .ts bằng strip-types; đọc transpiler + native IO |
| go | https://github.com/golang/go | Go | 3 — Go thuần | runtime ngôn ngữ: scheduler, netpoller, GC |
| sqlite | https://github.com/sqlite/sqlite (mirror chính thức của fossil) | C | 4 — DB bên đi | engine luật contest: in-process, WAL, PRAGMA |
| postgres | https://github.com/postgres/postgres (mirror git) | C | 4 — DB bên tới | MVCC, planner, WAL, pool |
| node | https://github.com/nodejs/node | C++ / JS | 1 (so sánh) | baseline runtime đang dùng thật |
| python/cpython | https://github.com/python/cpython | C | phụ | baseline submission + probe script viết bằng Python |

## Nhóm 3 — phụ, pull khi đào sâu submission tương ứng

| Name | Link | Ngôn ngữ | Đọc để hiểu submission |
|---|---|---|---|
| gnet | https://github.com/panjf2000/gnet | Go | `go-gnet-*` (#38, #48) — event-loop Go |
| fasthttp | https://github.com/valyala/fasthttp | Go | `go-fasthttp-*` (#56, #106) |
| uWebSockets | https://github.com/uNetworking/uWebSockets | C++ | `cpp/node-uwebsockets-*` (#6, #15, #102) |
| h2o | https://github.com/h2o/h2o | C | `c-h2o-*` (#39) |
| swoole-src | https://github.com/swoole/swoole-src | C++ | `php-swoole-*` (#24, #28) — PHP + C++ reactor |
| tokio | https://github.com/tokio-rs/tokio | Rust | nền async cho `rust-*` (#17, #22, #90, #114) |
| libuv | https://github.com/libuv/libuv | C | nền event loop Node/Bun — hiểu runtime 2 trục 1 |

## Nhóm 4 — case study ngoài challenge (docs/06)

| Name | Link | Ngôn ngữ | Case study |
|---|---|---|---|
| hhvm | https://github.com/facebook/hhvm | C++ / Hack | PHP → bytecode JIT của Facebook; bài học "bùa chú PHP+C++" |
| kphp | https://github.com/VKCOM/kphp | C++ / PHP | VK compile PHP → C++ binary |
| php-src | https://github.com/php/php-src | C | Zend VM + JIT PHP 8 |
| clickhouse | https://github.com/ClickHouse/ClickHouse | C++ | vectorized execution, SIMD, cache-aware |
| ripgrep | https://github.com/BurntSushi/ripgrep | Rust | SIMD/memchr search — zero-cost trần cao |
| tigerbeetle | https://github.com/tigerbeetle/tigerbeetle | Zig | DB thiết kế cho tail latency + batching IO |

## Quy tắc dùng

1. Clone ra **ngoài** repo này (`~/opensource/tools/<name>`), không vào `upstream/` của máy khác
   ngoài máy gốc — `upstream/` ở đây đã có bản clone chuẩn + PR refs.
2. Ghi SHA checkout vào evidence khi đọc phần nào để kết luận gì (tái hiện được).
3. Repo chỉ để **đọc và đối chiếu** — không push lên fork trừ khi có ý định góp PR riêng.

## Go + chi + PostgreSQL

- `go-chi/chi` — https://github.com/go-chi/chi — Go; router/middleware trên net/http.
- `jackc/pgx` — https://github.com/jackc/pgx — Go; PostgreSQL driver/pool/protocol.
- SHA đã đọc: `evidence/go-chi-pgx-sources.json`. Clone local vào `upstream/chi`, `upstream/pgx`
  (gitignored), checkout SHA tương ứng trước đối chiếu report; không chạy build/install tự động.
