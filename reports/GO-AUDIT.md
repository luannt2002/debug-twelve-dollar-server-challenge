# Audit Go: đọc đường chạy, giữ lợi ích, bỏ phụ thuộc benchmark

Ngày đọc: 2026-10-19. Phạm vi: 16 submission Go trong `snapshots/pr-*`, snapshot PR head do luồng chính tải; không sửa submission. Đây là audit source và probe nhỏ, không phải kết quả capacity chạy lại.

**Kết luận:** có thể xây service Go thông thường rất nhanh từ ý tưởng của #18/#99. Bước nhảy lớn của nhóm đứng đầu đến từ số công việc thực hiện mỗi request, chi phí mỗi connection, SQLite và kernel; không phải chỉ đổi ngôn ngữ. #72/#76/#91 đã gần server chuyên dụng Go+C hơn là CRUD Go thông thường. Không copy nguyên parser/auth/transaction của chúng vào production.

## 1. Inventory và mức đọc

Mỗi đường dẫn bảng dưới có tiền tố `snapshots/`. Đã đọc README, nhận diện entrypoint và SQL/commit path của cả 16. Đọc sâu nghĩa là theo source từ route/auth đến query và publication response; không có nghĩa đọc từng dòng mọi dependency/generated code.

| PR | Submission | Đường chạy chính | Mức đọc |
|---|---|---|---|
|18|`pr-18/submissions/go-nethttp-tbsvttr`|net/http → queue1024 → một DB actor → group256 → commit → response|Toàn bộ main.go và README; map scripts/tests, chưa chạy toàn suite|
|34|`pr-34/submissions/go-rr-sirkostya009`|fib → auth → generated rr → controller → service → repository mutex → crawshaw SQLite|Đọc các lớp handwritten và auth; generated codecs/router chỉ kiểm điểm gọi, không từng dòng|
|38|`pr-38/submissions/go-gnet-Haris0059`|gnet → parser tay → JWT → C shim → SQLite JSON → socket|Đọc main/http/db; map tests|
|44|`pr-44/submissions/go-stdlib-vkrishna03`|epoll → inline → ba range scan feed → Go encode → write|Đọc API/SQLite hot path và map transport|
|48|`pr-48/submissions/go-gnet-kaikegm`|gnet → scanner JWT → C row-to-JSON → SQLite autocommit|Đọc DB/README và map parser/JWT; không chạy generator|
|52|`pr-52/submissions/go-epoll-damianoneill`|epoll → auth → C packed rows → Go encode → group commit → response → checkpoint|Đọc auth/http/api/db và finishBatch; map tests|
|56|`pr-56/submissions/go-fasthttp-b3nhard`|fasthttp → custom JSON/JWT → read pool/write mutex → direct cgo → autocommit|Đọc main/auth và map DB/scanner; chưa audit từng nhánh scanner538 dòng|
|65|`pr-65/submissions/go-epoll-Antheurus`|epoll nhiều process → auth/validate → pending writes → BEGIN retry → commit → deliver|Đọc workers/db/commit path; map HTTP/JSON/io|
|72|`pr-72/submissions/go-epoll-MegaPanchamZ`|epoll → op arena → một cgo/batch → SQLite internals+C encode → commit → scatter responses|Đọc db/shim/engine và enqueue/finish flow; parser map|
|76|`pr-76/submissions/go-epoll-champ3oy`|io_uring direct descriptors/epoll → Go auth → C SQLite render → group commit + checkpointer|Đọc JWT/DB/C and architecture; io_uring ownership map, chưa chứng minh lifecycle mọi CQE|
|91|`pr-91/submissions/go-lowlevel-janso123`|custom I/O → C read connection; bounded writer actor → savepoint/request → commit → generation-tagged completion|Đọc api/writer/db và map checkpointer/memory guards/ring; chưa audit mọi ring state|
|99|`pr-99/submissions/go-nethttp-fi5HiE`|net/http ServeMux → jwt/v5 → database/sql readers + writer1 → response|Đọc toàn bộ main/store/auth/handlers|
|100|`pr-100/submissions/go-nethttp-mattn-vedic`|epoll inline(default) → direct driver pool → QueryText fused C query → SQL JSON|Đọc main và parser/handoff points; không đọc toàn bộ vendored sqlite3 fork|
|103|`pr-103/submissions/go-gin-lincolng4`|Gin/net/http → HMAC pool → sql pool16 → row structs → JSON|Đọc toàn main + README|
|106|`pr-106/submissions/go-fasthttp-savak1990`|fasthttp → pooled request → DB actor4096 → reads first/writes group256 → C shim → commit|Đọc main/db/sqlite/shim/body và map JWT/JSON|
|111|`pr-111/submissions/go-epoll-brady1408`|epoll → auth → one SQLite loop connection → held writes → commit; second checkpointer thread|Đọc db/handlers/auth/http và process/finishBatch/flush; map tests|

Không đồng nhất số LOC với mức kiểm chứng: inventory `find snapshots -path '*/submissions/go-*/*.go' | xargs wc -l` cho 37,194 Go LOC, trong đó gồm generated code, driver fork, tests và load generator. Không tuyên bố đã đọc 37,194 dòng hay audit đầy đủ dependency.

## 2. Luồng #18: mẫu gần sản phẩm nhất để học group commit

`main.go:331+` mở đúng một connection, WAL + NORMAL + foreign_keys ON, EXCLUSIVE, busy_timeout0; prepare feed/post/create/like/exists/health. `GOMAXPROCS(1)` hợp với quota một CPU, không phải setting mặc định cho mọi service.

HTTP đọc body tối đa16KiB → enqueue job (queue1024) → worker `work()` drain tối đa256 request đã sẵn sàng, không chờ timer → `handle()` xác thực HS256/exp/nbf/sub/username cho POST → validate Unicode/body → `BEGIN IMMEDIATE` ở write đầu tiên → prepared SQL. Read trong cùng actor có thể thấy write provisional, nhưng **toàn bộ replies cùng batch chờ COMMIT**, nếu auto-rollback/commit lỗi thì cả batch500 → mỗi handler mới write response. `main.go:294-328` là phần nên đọc kỹ.

Điểm tốt: queue hữu hạn; cancellation trước enqueue; done buffered1 tránh actor kẹt nếu client đi mất; phát hiện SQLite auto-rollback bằng AutoCommit; commit thất bại không phát success; SQL uniqueness chống duplicate likes. Có diagnostic commit-fault/SIGKILL được tác giả lưu, nhưng lần audit này chưa chạy lại.

Giới hạn: mọi auth/read/write chung một actor nên slow query kéo cả service; không có request deadline trong DB (`context.Background`); job đã nhận có thể commit sau khi client cancel; success NORMAL không đồng nghĩa chịu mất điện. Queue bounded không chặn hàng chục nghìn goroutine đang chờ enqueue/body. Dùng idempotency key cho mutation để retry an toàn. EXCLUSIVE không hợp nhiều process cùng mở DB. Không mang `GOMAXPROCS(1)` vào deployment8CPU.

## 3. Các tối ưu thật sự và giá của từng bước

### 3.1 #99: đường thực dụng

Giữ net/http, ServeMux, database/sql, JWT library. Read pool `max(4,2*GOMAXPROCS)` và writer pool1; feed SQL trả một JSON scalar thay vì scan100 columns/cgo crossings; statement reuse, like một INSERT + chỉ check exists khi zero changes. Tác giả đo feed28.6→18.9µs và184→27 allocations; **đây là số tác giả**, chưa tái lập.

Điểm đáng chuyển sang production: shape SQL/response rõ; limit pool; graceful Shutdown10s; no per-request logger trên successful fast path. Điểm phải sửa: SQL không context nên timeout/cancel không giải phóng query đang chạy; `IdleTimeout10s` cố tình recycle connection để vừa FD budget, không phải bằng chứng giữ70k socket; `TrimSpace` khác JS trim; FK chưa bật. Đừng bỏ context chỉ để tiết kiệm watcher khi DB là remote PostgreSQL.

### 3.2 #34/#103: framework chưa quyết định kết quả

#34 giữ domain/service/repository và generated router/codec, đổi transport sang fib; #103 dùng Gin + net/http + stdlib JSON. Các layer function call thường nhỏ hơn query count, lock contention, body copies, connection memory. #34 thừa nhận trailing garbage được nhận; đây là ví dụ codegen nhanh không tự đảm bảo contract. #103 có cấu hình pool/EXCLUSIVE sai bên dưới. Tối ưu router trước sửa DB không giải quyết nút thắt đó.

### 3.3 #38/#44/#48/#52: giảm crossings và idle memory

Event loop giữ struct nhỏ, trả read/write buffer khi idle, thay goroutine+buffer mỗi socket. C shim gom bind/step/column/reset vào một crossing. Các bản chọn ba phương án khác nhau: SQLite JSON (#38/#99/#100/#106), C packed rows→Go JSON (#52), C rows→JSON (#48/#76). #44 đo SQL JSON chậm hơn Go encoder; #99 đo nhanh hơn scan rows. Hai kết quả không mâu thuẫn: khác query shape, SQLite build, driver và encoder.

#44/#72 tối ưu feed: lấy20 newest IDs → nếu range hẹp thì scan posts và likes theo range, ghép theo danh sách ID ban đầu → fallback reference nếu sparse/missing. Ý tưởng quan trọng là **thay nhiều B-tree seek bằng range scan**, không phải giả định ID luôn đúng thứ tự thời gian. #72 bảo vệ snapshot bằng transaction read; #44 dựa duy nhất một writer/connection không interleave. PostgreSQL nhiều writer phải dùng một statement hoặc snapshot phù hợp.

### 3.4 #65/#76/#91/#111: tối ưu nút nghẽn ngoài ngôn ngữ

#65 ba process được steer bằng SO_REUSEPORT+BPF để tăng FD capacity; queue writes cho BEGIN lock fail và retry sau, reads còn tiến. #76 dùng hai io_uring registered tables, direct descriptors để vượt process FD table; kernel TCP sockets vẫn tiêu kernel memory/conntrack. #91 giữ write queue4096, slot gồm queued/inflight/completion, rejects503, generation tags chống trả completion vào FD đã tái dùng; SAVEPOINT riêng cho request giúp cô lập lỗi trong batch. Đây là ý tưởng ownership/backpressure hữu ích hơn việc copy ring implementation.

#111 dành thread riêng checkpoint và pause writes cho WAL rewind; #106 chỉ TRUNCATE khi queue rỗng; #52 checkpoint sau flush; #65 RESTART thread riêng và writers retry nonblocking. Không có một chiến lược WAL đúng cho mọi workload: read transaction lâu, write liên tục, queue không bao giờ rỗng, storage fsync chậm sẽ đổi tradeoff. Muốn đưa production phải đo WAL bytes/frames, checkpoint duration/busy, queue age, commit duration.

## 4. Phát hiện có case cụ thể

### 4.1 [P1] #72 output arena có thể ghi vượt heap khi feed/batch lớn

Bằng chứng source: `pr-72/submissions/go-epoll-MegaPanchamZ/db.go:24-26` cho2048 ops và16MiB output; `server_linux.go:362` chỉ kiểm nOps. `pgo/engine.c:181-242,427+` format/append bằng pointer vào out_buf; `out_cap` chỉ được lưu lúc allocation `:251`, không có bounds check ở render. Không có budget bytes trước khi nhận op.

Case suy ra trực tiếp:20 newest posts mỗi body500 dấu `"` (hợp lệ theo500 Unicode scalar) encode thành khoảng20KiB/feed;2048 GET/feed responses cần trên40MiB, vượt16MiB. Một packet64KiB chứa được hơn2000 request GET/feed ngắn. Cũng có req arena2MiB ở `db.go:67-72`: copy có thể truncate nhưng reqPos vẫn tăng; request tiếp theo có thể panic hoặc C đọc ngoài arena. Đây là **finding static, chưa chạy ASAN/crash** vì host chưa có SQLite dev headers. Fix nhỏ nhất: budget số bytes worst-case mỗi op, flush sớm; C renderer nhận end pointer/check every append; kiểm allocation. Đọc SQLite internal Vdbe/Mem cũng khóa implementation vào exact SQLite revision, cần ABI tests khi nâng cấp.

### 4.2 [P1] #103 EXCLUSIVE lock + sql pool16 làm request đồng thời bị database locked

`pr-103/submissions/go-gin-lincolng4/main.go:49,54-55` bật `_locking_mode=EXCLUSIVE`, mở tối đa16 connections. Connection đầu truy cập DB giữ exclusive WAL lock suốt đời; query đang giữ rows khiến database/sql cấp connection thứ2, connection đó không thể đọc DB dù cùng process, chờ5s rồi500. Core count không ngăn concurrent goroutine lúc cgo/filesystem blocking.

Probe SQLite system (Python sqlite3): connection A bật WAL+EXCLUSIVE, đọc bảng, giữ open; B query cùng DB timeout50ms → `database is locked`. Probe chứng minh lock mechanism, **chưa phải full Gin server concurrency run**. Fix chọn một connection khi EXCLUSIVE, hoặc shared normal locking và pool giới hạn theo read/write workload. Đừng giữ cả hai.

### 4.3 [P1] #111 parser nhận Content-Length mâu thuẫn

`pr-111/submissions/go-epoll-brady1408/http.go:125-130` luôn overwrite contentLength, không nhớ giá trị trước. Probe copy nguyên http.go/auth.go vào temp, compile stdlib Go1.26.4 `GO111MODULE=off GOTOOLCHAIN=local go test -v` nhận input:

```http
POST /posts HTTP/1.1
Host: x
Content-Length: 999
Content-Length: 2

{}
```

Output thực: `duplicate_CL status=1 consumed=75 body="{}"` (`1=parseComplete`). Proxy/client parser chọn999 có thể lệch framing với backend chọn2; **chưa dựng reverse-proxy smuggling exploit**. Fix reject differing Content-Length, reject unsupported Transfer-Encoding và ambiguity TE/CL, differential tests với net/http. #52/#38 cũng có overwrite pattern; #72/#100 đã check duplicate mismatch, cho thấy không nên gom tất cả raw parsers thành một chất lượng.

### 4.4 [P1 khi policy dùng nbf] #111/#103 bỏ qua nbf được ký hợp lệ

#111 `auth.go:46-50,98-106` không có field/check nbf. Probe token ký secret thử, now1800000000, exp2000000000, nbf1900000000 → `future_nbf auth_status=0 user=1` (authOK). Chưa đến thời điểm được phép dùng token mà request đã được auth. #103 `main.go:263-267,315-322`, #100 tokenPayload/authenticate, #34 claims/Verify cũng không validate nbf (source findings, không chạy probe từng bản).

Đây là production policy gap, không gọi là vi phạm benchmark: SPEC của challenge chỉ yêu cầu exp. Fix dùng JWT validator thư viện với alg allowlist và validate nbf nếu có; yêu cầu exp theo policy sản phẩm, issuer/audience theo trust boundary. #52/#38/#56/#76/#100 cho phép thiếu exp theo source; điều này là **policy gap khi tái dùng production**, không mặc nhiên vi phạm SPEC (baseline JWT có thể cho phép không exp). Không đánh đổi semantics lấy allocation0.

### 4.5 [P1] #103 fallback secret công khai

`pr-103/submissions/go-gin-lincolng4/main.go:76` dùng `twelve-dollar-challenge` khi JWT_SECRET thiếu. Case deployment quên env, service vẫn chạy và attacker biết key để tự ký. Đây là deliberate seed tiện cho challenge, không an toàn cho production. Fail startup khi thiếu secret, load từ secret manager/config đã provision. Không ghi actual production secret vào log.

### 4.6 [P2] #111 read response phụ thuộc write rollback không bị invalidate

Cùng connection loop chạy write trong transaction rồi feed/getPost, các handler read luôn return `held=false` (`handlers.go:87-108,111+`). `loop.go:435-439,471-477` chỉ rewrite connections mang connHeld khi COMMIT fail. Case client A create, client B feed trong cùng epoll batch thấy row chưa commit; COMMIT fail → A500, B vẫn200 chứa row đã rollback. Response chỉ flush sau commit giúp timing nhưng không sửa body stale. **Suy luận source, chưa inject commit fault vào full loop.** Fix đánh dấu mọi read thấy open transaction là dependent/held hoặc reads dùng connection snapshot riêng; failure phải invalidate tất cả dependent replies. #18/#52 đã invalidate toàn batch; không suy rằng mọi group commit implementation có bảo đảm như nhau.

### 4.7 [P2] #106 phụ thuộc viết hoa header

`pr-106/submissions/go-fasthttp-savak1990/main.go:145-146,266` dùng PeekBytes(hdrAuth) và DisableHeaderNamesNormalizing=true; README tự xác nhận match case-sensitive. Request hợp lệ gửi `authorization:` lowercase có thể bị401 missing bearer. HTTP field names không phân biệt hoa thường. Fix bật normalization hoặc lookup EqualFold; test lowercase/mixedcase và deployment HTTP/2 proxy. Đây là source/documented behavior, chưa build fasthttp locally.

### 4.8 [P2] nhiều bản không bật FK: thành công nhưng row mồ côi

#48 `db.go:217` tắt foreign_keys rõ; #34 repository/db.go pragmas; #38 main.go pragmas; #44 api.go pragmas; #52 db.go pragmas; #65 db.go comment sqlLike; #99 store.go params; #100 main.go DSN; #103 DSN; #106 db.go pragmas đều không bật ON trong path đã đọc. Build có thể thay default; phải verify `PRAGMA foreign_keys` binary trước deploy, không suy duy nhất từ schema.

Case token ký hợp lệ cho user đã bị xóa: create userID không tồn tại vẫn insert nếu FK OFF; response201 lấy username từ token, nhưng feed JOIN users làm post biến mất. EXISTS trong like chỉ bảo vệ post, không bảo vệ user. Production cần FK ON mỗi connection hoặc business invariants mạnh tương đương, test deleted users/concurrent deletion. #18/#72/#91/#111 có bật ON trong source, nhưng #111 map mọi foreign-key failure thành post404 kể cả user missing (`handlers.go:193+`).

## 5. Tránh hiểu nhầm thành tích

- #18 tự ghi25,928req/s mixed,50k users155.5ms p99, có ARM64/local/container/setup riêng; chưa official. Đó là hai loại test khác nhau.
- #99 tự ghi70k users p99555–586ms trên Xeon cũ container, max active sockets khoảng55–62k và IdleTimeout10s. Logical users không bằng persistent connections.
- #48 tự ghi250–300k, nhưng hướng dẫn `ulimit -n 1048576`, hold10s, laptop loopback và pin physical core gồm CPUs0,4. Không so ngang FD65535/hold5min/one vCPU. Không gọi250k là official score.
- #65 tự đo120k trên M2 nhưng55k trên AMD VPS, còn thừa nhận cùng-host networking overhead. Đây là ví dụ vì sao so CPU architecture/harness trước so language.
- #91 tự ghi120k với error nhỏ khác0, custom Rust generator,3 sequential runs; không xóa error chỉ vì dưới threshold1%.
- #72 README có throughput rất cao dùng C internals+PGO trên workload riêng; nó không chứng minh typical Go microservice tự nhiên có cùng kết quả.

Mọi số trên do tác giả ghi README/artifacts; audit này không chạy k6, không xác nhận maximum, không tuyên bố binaries/source tương ứng số đo nếu chưa kiểm binary hash và raw outputs.

## 6. Chuyển sang PostgreSQL và service thực

| Ý tưởng SQLite | PostgreSQL/service tương ứng | Không được bê nguyên |
|---|---|---|
|Prepared statements, giảm100 column crossings|pgxpool, query shape phù hợp, scan typed rows hoặc một JSON field; EXPLAIN ANALYZE BUFFERS|SQLite one cgo call không xóa TCP/TLS/network RTT của Postgres|
|Một INSERT like + uniqueness|Unique(user_id,post_id), INSERT ON CONFLICT DO NOTHING RETURNING; FK thật|Không check-then-insert ngoài transaction|
|Group transaction nhiều writes|Batch/UNNEST/multirow INSERT cho ingest; pgx Batch giảm roundtrip; COPY cho bulk; acknowledge sau commit|Không gom requests người dùng/tenants tùy tiện, Pg statement error làm transaction aborted nếu không savepoint|
|Một actor serial writer|Bounded concurrent transactions và bounded admission; partition write hot keys|Postgres không có SQLite global single-writer constraint; serial hóa tất cả sẽ tạo bottleneck|
|SQLite renders JSON|json_build_object/json_agg hoặc app serialization tùy profile|DB CPU thường là tài nguyên chung đắt hơn app; aggregate ORDER BY rõ; jsonb có canonicalization/key ordering khác|
|3 range scans|CTE chọn20 IDs rồi lateral count/group aggregation + index; một statement/snapshot|Không giả định sequence ID theo commit time; sequence có gaps/out-of-order; READ COMMITTED statements khác snapshot|
|WAL checkpoint tuning|Theo WAL rate, checkpoints, replication lag, fsync, autovacuum; durable synchronous_commit phù hợp|Không tắt synchronous_commit chỉ để có headline nhanh; SQLite NORMAL là khác guarantee mặc định Pg|
|EXCLUSIVE/NOMUTEX/THREADSAFE0|Giữ server concurrency safe, pool hữu hạn, lock scope ngắn|Không có tương đương tắt lock/mutex để đổi ra production speed|
|Direct no Nginx|Đo gateway overhead riêng, keepalive upstream, TLS offload, proxy buffers, HTTP2/3|Bỏ gateway làm mất auth/WAF/rate limit/TLS/observability nếu ứng dụng chưa thay thế|
|io_uring/direct descriptors|Chỉ đánh giá khi CPU profile và socket/kernel budget là nút nghẽn|Không ưu tiên khi p99 bị DB wait, RPC fanout hoặc connection pool wait|

Với feed service production: HTTP timeout/body limit → validated auth → admission semaphore/queue deadline → pgxpool bounded → **một query read hoặc transaction business nhỏ** → encode → response. Track pool wait, query time, serialization time, bytes, queue age, p99, reject503, CPU/request, allocations/request, Pg locks/IO/rows. Mutation có idempotency key; event publish dùng outbox trong cùng transaction nếu yêu cầu không mất event. Request context truyền xuyên DB/RPC, deadline budget giảm dần; retry chỉ khi lỗi retryable và mutation an toàn.

Roadmap Go: (1) dựng baseline net/http hoặc Gin đang dùng với query/index/pool đúng; (2) fix N+1, contention, columns/rows thừa, paginate; (3) profile alloc/CPU/locks và SQL trước tối ưu; (4) thử JSON SQL vs app, pgx Batch/COPY khi workload ingest; (5) PGO từ traffic đại diện nếu compile path nóng; (6) chỉ cân nhắc custom transport/C sau khi chứng minh transport chiếm budget lớn và chấp nhận chi phí maintenance/security.

## 7. Đã kiểm và chưa kiểm

Đã chạy **hai probe nhỏ** trong temp, không root/install/load test: nguyên parser+auth #111 trên Go1.26.4 (thành công tái hiện defect, không phải contract test pass), SQLite WAL EXCLUSIVE hai connections qua Python system sqlite. Probe stdout: `duplicate_CL status=1 consumed=75 body="{}"`; `future_nbf auth_status=0 user=1`; `exclusive_second_connection=database is locked`.

Chưa build nguyên16 submissions; host Go1.26.4 khác toolchain pinned1.27.x, thiếu sqlite3 pkg-config/dev headers. Chưa test ASAN #72, fault injection #111, saturation/idle capacity, TLS/proxy, PostgreSQL. Chưa audit dependency/generated code toàn bộ, chưa chứng minh native io_uring ownership/cancellation mọi state, chưa xác minh tất cả README performance artifacts với binary hash. Các finding ghi rõ static/probe tương ứng; không lấy tests42/42 do tác giả nói thành xác nhận của lần audit.

**Ưu tiên đọc:** #18 main.go → #99 store/handlers → #52 db+finishBatch → #91 writer → #72 engine để hiểu ranh giới nơi tối ưu thành bespoke systems code. Thực dụng nhất để áp dự án là #18/#99 query, bounded queue/pool, commit semantics và observability; raw HTTP/parser, FK OFF, default secret, SQLite internals là phần phải lọc bỏ.


Bằng chứng tái lập được lưu bền: `python3 scripts/probe-go.py` → `evidence/go-probes.json`; `python3 scripts/probe-sqlite.py` → `evidence/sqlite-probes.json` (gồm lock EXCLUSIVE hai connection). PASS của fixture chỉ nghĩa probe chạy được, không có nghĩa implementation đạt contract.
