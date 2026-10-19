# Audit luồng TypeScript, Bun, Node.js và Deno

## Kết luận để chọn hướng

**Nên all-in TypeScript/Bun hoặc Node.js theo bottleneck đo được, không nên all-in tự viết HTTP parser.** Trong các submission hiện tải, phần cốt lõi lặp lại là query có index, prepared statements, giảm chuyển dữ liệu DB→runtime, transaction/commit hợp lý, giữ connection có giới hạn. Fastify PR51 là ví dụ kết hợp framework với group commit; Elysia PR80 giữ use case/repository và prepared SQL. Không có bằng chứng từ đọc source rằng bắt buộc xóa kiến trúc ứng dụng để nhanh.

**“Bản TypeScript” không đồng nghĩa toàn bộ chi phí chạy bằng JavaScript.** Bun có SQLite/native crypto tích hợp; Node PR102 dùng addon C++ uWebSockets và better-sqlite3; Deno PR119 dùng **Rust epoll poller + C SQLite/render/commit threads**, phần JS vẫn xử lý HTTP/auth/route. Đây là tổ hợp kiến trúc, không phải thí nghiệm cô lập ngôn ngữ.

Không chạy benchmark tải cao, không cài runtime hay chạy install.sh/root. Các số hiệu năng trong comment/README là tác giả báo cáo, không phải số đo lại. Không xếp hạng các bản này theo hiệu năng production khi chưa có cùng dataset, độ bền, error budget, TLS và tải.

## Phạm vi và cách đọc lại

Đã đọc toàn bộ file xử lý ứng dụng của 11 submission trong snapshot: PR **3, 4, 49, 51, 59, 61, 78, 80, 102, 119, 127**. PR49 có hai entrypoint Bun/Node nên là 11 thư mục, 12 cấu hình entrypoint. Đã đọc PR119 cả `render.c` (263 dòng) và `poller.rs` (380 dòng). Đã đọc PR102 build.sh để xác định native dependency/patch. Đọc source vận hành entry→parse/auth→SQL→commit→response; không có nghĩa audit hết dependency upstream, lockfile, bộ test và lịch sử từng commit.

Mọi path dưới đây tương đối với `/home/luannt/application/opensource/debug-performance/`. Snapshot là nội dung PR tại lần tải, không phải toàn bộ commit graph. Dùng `nl -ba <path>` để kiểm tra dòng. Danh sách ứng dụng thu được bằng `rg --files snapshots | rg '\.(ts|js|mjs)$'`, loại JS của benchmark và Rails asset khỏi phạm vi server TS/JS.

| PR/thư mục dưới `snapshots/pr-N/submissions/` | Entry, DB và HTTP | Điểm tối ưu thật trong source | Giới hạn chính |
|---|---|---|---|
| 3 `typescript-bun-xxmohamed012` | `server.ts`: Bun.listen, bun:sqlite, Bun.CryptoHasher | JSON SQL→BLOB; một output buffer; prepared SQL; exclusive lock; LRU shed 64k→63k; libc listen backlog | Tự parse HTTP, nhận method theo byte đầu; FK không bật; single-thread DB sync |
| 4 `typescript-bun-tbsvttr` | `server.ts`, `pressure.ts`: Bun.serve routes | Prepared SQL; WAL; FK ON; Response.json; body limit 16KiB; safe integer; kết thúc RETURNING bằng all() | Object/JSON allocation còn; SQLite sync trên event loop; exclusive DB |
| 49 `typescript-effect-SeeThruHead` | `src/main.bun.ts`, `main.node.ts`→HttpApp→PostRoutes→Posts→PostRepo→Database | Prepared Drizzle queries; Effect batch resolver tối đa 512; semaphore một connection; transaction có finalize/rollback | Runtime/schema layers có chi phí cần đo; chưa đủ guard khi một statement tự rollback toàn transaction |
| 51 `typescript-fastify-melroy89` | `server.ts`: Fastify, @fastify/jwt, better-sqlite3 | Feed SQL JSON; response schema; setImmediate group commit, flush tại 128 jobs; FK ON; descriptor shedding | Native build/runtime pin; DB sync; queue cần overload/deadline production |
| 59 `bun-elysia-shashishsoni` | `src/index.ts`→auth/validation/db/http | AOT Elysia; prepared SQL; checkpoint riêng Worker; proportional connection close | UTF-16 body limit; sub chưa safe-integer; `/proc` FD heuristic cần kiểm chứng trên kernel |
| 61 `node-fastify-gmr458` | `src/server.ts`→app/auth/db/responses | Fastify giữ routing; raw body Buffer; SQL JSON→BLOB; better-sqlite3 pluck; mmap 1GiB | FK OFF; exclusive; checkpoint sync tới 10000 pages; requestTimeout=0 |
| 78 `node-net-barrard` | `index.js`: node:net, node:sqlite, node:crypto | Zero npm dependency ứng dụng; SQLite JSON; array rows; pipeline một write; pause/drain backpressure | HTTP tự viết; không chunked; header limit chỉ nhánh chưa đủ header; nbf không kiểm tra |
| 80 `bun-elysia-brocchirodrigo` | `src/server/main.ts`→api→middleware/routes→use cases→sqlitePostRepository | Repository prepared SQL; Bun native HMAC clone; giữ domain/use case; mmap | GC chủ động có thể tăng tail; không safe-ID guard đầy đủ; phụ thuộc API crypto toàn cục của Bun |
| 102 `node-uwebsockets-zahidcakici` | `server.js`: native uWS+better-sqlite3 | SQL JSON/pluck; group commit cuối poll phase; gửi sau COMMIT; aborted response guard; FD close | FK OFF; exclusive DB; addon patch/build maintenance; WAL NORMAL không phải power-loss durable |
| 119 `typescript-deno-JakeAve` | `server.ts`→sqlite.ts→render.c; Linux poller.rs | Native render một FFI; Rust epoll; background FULL COMMIT; separate reader/checkpointer; queued response theo generation | i32 ID truncation; same-batch read thấy uncommitted; reader snapshot stale; raw HTTP subset |
| 127 `node-httpserver-aliskhanoff` | `src/index.js`→routes→db/auth/utils | node:http; SQL JSON→BLOB read; prepared statements | Sai feed order khi time khác id; body không limit; split UTF-8 chunk; JWT secret fallback; UTF-16 limit |

## Luồng cụ thể từng bản

### PR3: Bun raw TCP — nhanh nhờ cắt object và encode

`Bun.listen.socket.data`→`onData` tích lũy request chưa đủ→quét CRLF/header→`route`→JWT HS256 mỗi write→JSON.parse + trim + đếm code point→prepared insert/like→send. Read `/feed`, `/posts/:id` chạy JSON SQL và CAST BLOB; write trả JSON với JSON.stringify cho body/username. SQLite WAL NORMAL, exclusive lock, một connection; không có explicit group commit. `createStmt.values(...)[0]` tiêu thụ row trước trả response. Send copy vào buffer chung 256KiB và giữ phần chưa gửi theo connection; drain giải phóng phần pending. Shedding chỉ bỏ connection không có input/output pending, dùng terminate/RST; đây là chính sách tránh FD/conntrack chứ không tăng sức tính toán business.

Cần tách **Bun.serve vs Bun.listen**: PR4 vẫn dùng HTTP parser/Request/Response của Bun; PR3 tự chịu trách nhiệm protocol, drain, framing, header limit và slow-client. Không có benchmark cùng commit/config trong audit này để quy toàn bộ chênh lệch cho Request/Response.

### PR4: Bun.serve — baseline đáng bắt đầu

Routes khai báo native→auth trước req.json→validate→SQL prepare→Response.json. Foreign keys bật. Post create dùng `all()` để bước RETURNING tới DONE trước xây response (comment source giải thích rõ). Feed trả row objects; serializer chạy runtime. ID kiểm tra decimal và Number.isSafeInteger. HMAC có keyed hasher dùng copy; timingSafeEqual so bytes. Không group commit. Đây là cấu trúc ngắn, dễ bảo trì, thích hợp làm baseline trước khi thử SQL JSON.

### PR49: Effect/Drizzle — abstraction và batching cùng tồn tại

Bun/Node layer chỉ đổi HTTP runtime/SQLite adapter; logic chung: HttpRouter→Auth/schema→Posts domain→PostRepo prepared Drizzle→Database semaphore. Feed chuẩn bị query 20 rows và like count; result schema decode, response schema encode. InsertPost/InsertLike đi RequestResolver.batchN(512), batch độc lập theo loại, `BEGIN IMMEDIATE`→Effect.forEach(writes, Effect.exit)→COMMIT→Request.complete. Semaphore giữ connection không cho read xen ngang transaction.

Điểm quan trọng: `Effect.exit` biến failure từng job thành giá trị; trường hợp statement lỗi constraint ABORT có thể giữ transaction và cho job khác thành công. Nhưng SQLite lỗi I/O/FULL có thể tự rollback transaction: code `Database.ts` không kiểm tra sqlite autocommit/inTransaction giữa job; nếu job sau autocommit và COMMIT cuối fail, có khả năng trả fail cho job đã commit. Đây là **rủi ro suy luận từ source**, chưa inject lỗi runtime. So với PR51/102 có guard inTransaction, cần kiểm thử trước dùng batch này cho nghiệp vụ.

### PR51: Fastify group commit — hướng thực dụng

Fastify onRequest authenticate→body parser→handler validation→write(run,finish). Feed đi SQL aggregate JSON, send string raw; single post dùng response schema serializer. Queue flush setImmediate hoặc đủ 128→db.transaction loop job→commit xong mới finish reply. Guard `if (!db.inTransaction) throw failure` ngăn job sau chạy tự commit khi DB đã rollback; batch failure truyền cho mọi reply. FK ON. Đây là thiết kế tốt để học cách giảm commit mà giữ framework, nhưng trong PostgreSQL không copy cơ chế bắt lỗi statement rồi tiếp tục trong cùng transaction (PG transaction bị aborted cho tới rollback/savepoint).

### PR59: Elysia + worker checkpoint

Index mở SQLite, chuẩn bị query và start FD watch. GET trả mapped row objects→JSON.stringify. POST tự auth, Request.json, validation, insert; like insert-select-exists ON CONFLICT. Auto-checkpoint tắt, Worker một connection chạy PASSIVE mỗi giây; lỗi/close worker bật lại auto-checkpoint. Lợi ích: tránh checkpoint fsync trên JS request thread. Vẫn cần theo dõi WAL bytes/checkpoint progress, worker alive và long reader; worker tồn tại không chứng minh checkpoint tiến triển. Body limit dùng `.length` chứ code points; auth chuyển sub decimal sang Number không có safe-integer bound. `statSync('/proc/self/fd').size` được code dùng làm FD count: không coi đó là API portable; verify giá trị với readdir trên kernel triển khai trước dùng làm overload guard.

### PR61: Fastify không cần bỏ framework để giảm object

Server→buildApp→Fastify parse body Buffer→auth helper→prepared SQLite BLOB queries→reply.send(Buffer). Feed/post/create SQL tự json_object; `pluck()` lấy duy nhất Buffer. Like dùng atomic insert-select-exists, 0 changes mới lookup exists. Không batch explicit; DB autocommit mỗi write. HTTP body parser có limit 16KiB nhưng auth trong handler sau body buffering; timeout request/connection =0 cần ingress/timeout policy. FK OFF và locking EXCLUSIVE là giả định benchmark một process owns DB, không nên bê nguyên vào service nhiều writer.

### PR78: Node thuần raw TCP

node:net data→concat remainder→parseHead→route exact method→JWT→prepared node:sqlite→SQL JSON→response string→pipeline một socket.write, pause input khi write false. Parser có kiểm tra HTTP version, CL digit/duplicate CL, reject TE, xử lý Expect:100-continue. Tốt hơn PR3 ở một số điều kiện nhưng vẫn là HTTP subset; không được gọi parser production hoàn chỉnh. Auth kiểm tra exp khi có, không kiểm tra nbf. Reads sync làm event loop đợi SQLite; một query slow ảnh hưởng cả health/connection.

### PR80: Elysia use case/repository

main→api compose repository/auth→routes→use case→prepared statements→presenter object→framework response. Không ORM runtime; domain tách file nhưng hàm sync đơn giản. Like dùng insert-select + lookup khi 0 changes. Body đếm Unicode code points khi UTF-16 length vượt 500. Memory guard đo RSS mỗi 2 giây, gọi Bun.gc(true) tối đa mỗi 30 giây khi quá 75% constrainedMemory. Đây là heuristic quản trị bộ nhớ, không chứng minh throughput tăng; nếu constrainedMemory()=0 thì soft limit=0 và GC định kỳ dễ xảy ra. Cần đo GC pause/tail và allocation trước bật trong production. Auth dùng `crypto.timingSafeEqual` toàn cục Bun: chưa chạy Bun ở máy này để xác nhận version-specific API.

### PR102: Node + C++ native transport + group commit

uWS route native→guard/auth→onData clone buffer nếu phải giữ sau callback→validate→Write job. setImmediate(flush) gom writes trong poll turn; BEGIN→job.run→COMMIT→res.cork(send). Reads sync không interleave với flush đang mở transaction. Abort guard tránh dùng res đã bị hủy; mutation vẫn có thể commit nếu client hủy, nên production cần idempotency key khi retry. `build.sh` pin uWS/uSockets commits, sửa timeout 10→75s, bỏ TLS/H3, compile addon; SQLite cũng build native. Những optimization native này không phải V8 tự nhiên làm HTTP nhanh như C++.

PR102 có comment “NORMAL COMMIT durable once returns”: **không dùng comment này như cam kết chống power loss**. WAL NORMAL khác FULL về fsync; đọc documentation SQLite trước quyết định durability. Group commit giảm số transaction nhưng không sửa được durability mode.

### PR119: Deno TS + Rust + C, topology quyết định kết quả

Linux JS thread block trong synchronous FFI `px_wait`, Rust epoll giữ sockets/buffers, JS parser/auth/router, sqlite.ts FFI xuống SQLite custom build. Read render C bước trực tiếp rows vào scratch→copy response bytes→Rust send. Writer JS batch→C commit thread `COMMIT; BEGIN` với synchronous FULL→eventfd wake→JS release response. Separate reader connection phục vụ khi writer busy; checkpointer thread riêng PASSIVE/TRUNCATE. Generation counter FD chống gửi response cũ cho socket mới tái sử dụng fd. Đây là bài học ownership/queue/backpressure đáng giá, nhưng đã đi vào tự xây runtime/service infrastructure.

Critical correctness boundaries bên dưới phải được giải trước nếu lấy thiết kế này làm production template.

### PR127: Node http, cần sửa tính đúng trước benchmark

node:http callback route bằng url string→auth→body Promise→prepared better-sqlite3→raw BLOB read/object write. Không group commit. Body concat string theo mỗi chunk; UTF-8 multibyte bị cắt giữa TCP chunks có thể thành replacement chars. Body không hard limit nên attacker/client lỗi giữ nhiều memory. JWT default secret khi thiếu env; signature so string; exp có nhưng nbf không kiểm tra. Feed order `p.id DESC` khác timestamp+id của các bản khác. Các hàm getAllPosts/updatePost không được router gọi nên không tính là feature thực chạy.

## Phát hiện và bằng chứng cần xử lý

| Mức | Path:dòng | Phát hiện / tình huống |
|---|---|---|
| Cao | `snapshots/pr-119/submissions/typescript-deno-JakeAve/sqlite.ts:24`, `:106`, `:145` | sqlite3_bind_int/column_int là signed 32-bit, trong khi parseId nhận tới 16 digits. `4294967297` xuống i32 thành 1; GET/like/user ID có thể trỏ nhầm record. C renderer lại đọc int64 nên miền ID không nhất quán. Chuyển bind/column int64, BigInt/string boundary và regression 2^31,2^32,2^53. |
| Cao | `snapshots/pr-119/submissions/typescript-deno-JakeAve/server.ts:112`, `:352`, `:358`, `:657` | Write trong batch chỉ set pending; wBusy đổi cuối batch. Read sau write trong cùng poll batch chọn writer connection, thấy uncommitted và có thể gửi trước COMMIT cho connection khác. Nếu commit fail, đã lộ dữ liệu rollback. Đây là source-derived execution path; chưa chạy native fault injection. |
| Vừa | PR119 `server.ts:65`, `:627` | Reader snapshot refresh có throttle 20ms, nhưng px_wait có timeout 1000ms. Không phải cam kết stale ≤20ms trong mọi lịch; khi writer busy read có thể lấy snapshot cũ. Cần xác định read-your-writes và snapshot contract. |
| Cao khi public | PR3 `server.ts:219`, `:228`, `:281`, `:295` | Method chỉ byte G/P: `PATCH /posts` được route như POST; version không validate; CL parse dừng tại non-digit, không reject conflicting duplicate CL/TE. Rủi ro framing khác ingress. Chưa chứng minh request smuggling với một proxy cụ thể; không gọi exploit đã chạy. |
| Vừa | PR78 `index.js:253`; PR3 `server.ts:275` | MAX_HEAD chỉ check khi chưa thấy delimiter. Một complete header quá limit trong một chunk không bị chặn theo MAX_HEAD. Probe parseHead PR78 với 9023-byte header vẫn trả request. |
| Cao khi public | PR127 `src/utils/request-body.js:6` | Body không bound, chuyển từng Buffer sang string riêng. Cần byte budget, decode UTF-8 bằng StringDecoder/Buffer.concat và abort/deadline. |
| Vừa | PR127 `src/db/feed.js:32` | Sort id thay created_at,id; fixture id1 time z, id2 time a cho hai thứ tự trái nhau. Không nên gọi nhanh nếu khác kết quả yêu cầu. |
| Vừa | PR59 `src/validation.ts:48`; PR119 `server.ts:278`; PR127 `src/utils/validate.js:32` | `.length > 500` đếm UTF-16; 500 emoji =1000 units nhưng 500 code points. Các bản PR3/4/51/61/78/80 xử lý đúng code points. |
| Cao theo integrity | PR61 `src/db.ts:9`; PR102 `server.js:29`; PR119 `server.ts:31` | FK OFF: token hợp lệ với sub không tồn tại có thể ghi post/like mồ côi nếu không có guard khác. Chữ ký JWT không chứng minh user vẫn tồn tại/active. PR3/59/80 cũng không bật FK trực tiếp. |
| Vừa | PR78 auth `index.js:72`; PR127 `src/auth/jwt.js:76`; PR119 `server.ts:250` | nbf không kiểm tra. Nếu hệ thống phát hành nbf, token được dùng trước thời điểm cho phép. Exp optional ở một số bản là chính sách cần đối chiếu; không tự coi thiếu exp là bug ngoài contract. |

## Probe đã chạy, giới hạn rõ

Đã lưu [script probe](/home/luannt/application/opensource/debug-performance/scripts/probe-ts-node.mjs) và [output JSON](/home/luannt/application/opensource/debug-performance/evidence/ts-node-probes.json). Tái lập từ thư mục gốc bằng `node scripts/probe-ts-node.mjs > evidence/ts-node-probes.json` (Node có `node:sqlite`; không network/server/load).

Chạy Node v24.16.0; extract nguyên hàm `parseHead` PR78 vào vm, không khởi động server. Kết quả: conflicting Content-Length→null; TE+CL→chunked=true (caller sẽ reject); header complete 9023 bytes→request hợp lệ. Dùng node:sqlite :memory: chứng minh sort id và timestamp có thể khác. Probe Unicode: 500 emoji→UTF-16 1000/code points500; bit coercion 4294967297→1 chỉ là **minh họa JavaScript**, chưa chạy Deno FFI hoặc C cast; finding miền ID dựa thêm vào chữ ký FFI i32 và SQLite bind_int trong source, không gọi là runtime reproduction.

Probe SQLite in-memory bổ sung: cùng connection SELECT thấy 1 row sau BEGIN+INSERT trước COMMIT, sau ROLLBACK còn 0; điều này xác nhận cơ chế nền của finding PR119 nhưng chưa chạy toàn bộ poller. Probe Buffer UTF-8: ghép string từ hai nửa emoji cho `���`, decode toàn Buffer cho `😀`, xác nhận failure mode PR127.

Máy có Node và Deno, không thấy Bun trên PATH. Chưa build native SQLite/uWS/poller, chưa chạy toàn bộ HTTP conformance/auth suite; vì vậy không gắn nhãn tested production. Không tự sửa upstream hay cài dependency.

## Áp dụng vào TypeScript service với PostgreSQL

1. **Giữ transport được bảo trì**: Bun.serve/Elysia hoặc Node/Fastify. Ingress/TLS/HTTP compliance, timeouts, tracing, graceful shutdown vẫn có giá trị. Chỉ bỏ một hop khi profile thực chứng minh hop đó chi phối latency và vẫn giữ các chức năng cần thiết.
2. **Tối ưu DB trước raw sockets**: đo query count/request, rows scanned/returned, lock waits, pool wait và EXPLAIN (ANALYZE, BUFFERS) trên dữ liệu đại diện. Index feed `(created_at DESC,id DESC)` và likes `(post_id)`; unique `(user_id,post_id)` để idempotent. Keyset pagination thay offset sâu. Multi-tenant cần tenant predicate/index thật, không dùng query benchmark nguyên trạng.
3. **Bounded pool/queue**: SQLite một connection sync không dịch thành một PG connection cho toàn service. Pool phải giới hạn theo DB capacity và số replica; đo pool wait, timeout, cancellation, queue bytes và pending count. JS async network I/O cho phép chờ PG không chặn event loop; query PostgreSQL nhiều vẫn tốn DB CPU/network.
4. **Ít roundtrip hơn**: insert RETURNING; ON CONFLICT; gộp read liên quan; batch độc lập hoặc multi-row insert khi semantics cho phép. PG có WAL/group commit của server; không tự gộp mọi HTTP request vào một transaction dài. Batch phải có max items/max delay và fail isolation. Trong PG, statement lỗi làm transaction aborted; dùng SAVEPOINT hoặc fail toàn batch đúng nghĩa.
5. **JSON DB là tradeoff**: json_build_object/json_agg có thể giảm mapping và runtime allocation nhưng chuyển CPU sang DB, vẫn truyền network bytes; jsonb còn có cost. So sánh raw rows→serializer với DB JSON cho payload thật. Không double stringify JSON string; quy định bigint/timestamp/null/escaping, schema và field-level auth. DB JSON không bỏ được N+1 hoặc thiếu index.
6. **BigInt boundary**: PostgreSQL bigint vượt 2^53; dùng string/BigInt và wire contract rõ. Không đổi sang Number để “nhanh” rồi mất precision như ID FFI PR119. Cursor cũng phải giữ chính xác.
7. **CPU job tách theo đo**: JWT native crypto, JSON payload nhỏ thường đủ. Compression/image/AI parsing/hash nặng cần worker/bounded work queue hoặc service chuyên dụng. Thêm worker không tự giải DB lock/pool exhaustion; cần tính overhead clone và queue.
8. **Đảm bảo hành vi trước throughput**: auth/tenant, idempotency khi timeout sau commit, retry transient lỗi có budget, read-after-write, rolling deploy/drain, pool shutdown, transactional outbox nếu ghi DB và phát event. Không giữ transaction qua HTTP request sang service khác.

## Checklist thử nghiệm có giá trị

Dùng cùng contract/data/durability và so từng thay đổi: (A) framework+rows baseline; (B) prepared SQL/index; (C) DB JSON chọn endpoint; (D) batch write có bound; (E) thay runtime giữ cùng query. Đo throughput hoàn tất ở cùng error/latency SLO, p50/p95/p99, event-loop lag, CPU/RSS/GC, DB CPU/I/O/pool wait và queue. Có read/write skew, burst, client chậm, body Unicode, ID lớn, duplicate request, DB timeout, rollback và shutdown. VU/connection count không thay thế requests/s: nhiều idle clients có thể ít công việc hơn ít clients hoạt động liên tục.

Điểm dừng hợp lý: khi query/network/DB pool chi phối, đổi TypeScript compiler hoặc viết raw HTTP parser không chữa đúng bottleneck. TypeScript compiler viết bằng Go tối ưu build/typecheck; không tự biến JavaScript server thành Go runtime.
