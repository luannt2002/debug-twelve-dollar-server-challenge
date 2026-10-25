# Go + chi + PostgreSQL: luồng hiệu năng và cách debug service cũ

Ngày đọc: 25/10/2026. “chi” được hiểu là router go-chi/chi. SHA source chi/pgx nằm trong [manifest](../evidence/go-chi-pgx-sources.json). Đây là audit source và hướng dẫn đo; chưa có benchmark PostgreSQL thực chạy trong lượt này, chưa chứng minh stack này nhanh nhất.

## Kết luận

Go + chi + pgxpool là hướng xây service thông thường đáng thử: HTTP chuẩn, router nhẹ, driver PostgreSQL và giới hạn concurrency rõ. Tốc độ lớn nhất thường đến từ **ít round trip, ít dữ liệu, ít lock contention và ít thời gian giữ connection**, sau đó mới tới allocation/router. Không có phần trăm tăng tốc nào được khẳng định khi chưa đo.

Các bản Go challenge nhanh vì nhiều biến cùng đổi: SQLite in-process tránh DB network/protocol; query nóng/index; C shim giảm crossings; JSON dựng trực tiếp; buffer tái dùng; group commit; connection state nhỏ. Một số bản dùng C engine rất sâu: không thể đem điểm đó gán cho Go+chi+PostgreSQL. [Audit 16 bản Go](GO-AUDIT.md) ghi rõ từng implementation và finding.

## 1. Bản đồ source đã lần theo

| Thành phần | Đường vào → ra | Cơ chế và giới hạn |
|---|---|---|
| chi | mux.go ServeHTTP → middleware chain → routeHTTP → tree.FindRoute → handler | sync.Pool tái dùng route context; vẫn WithContext/WithValue, không phải zero allocation tuyệt đối |
| chi timeout | middleware/timeout.go Timeout → context.WithTimeout → next.ServeHTTP → defer status | Cancellation hợp tác; handler không nghe context vẫn chạy. Không đảm bảo thay status sau khi response đã bắt đầu |
| pgxpool acquire | pgxpool/pool.go Acquire → underlying pool → expiry/health checks → connection | Acquire có thể chờ pool, ping hoặc tạo connection; đo riêng với query duration |
| read nhiều row | Pool.Query → Acquire → Conn.Query → poolRows | rows.go Close trả connection; Next false tự Close; phải kiểm Err sau vòng lặp |
| read một row | Pool.QueryRow → Acquire → poolRow.Scan | Không Scan thì chưa trả connection; lỗi cũng có thể chỉ lộ tại Scan |
| mutation | Pool.BeginTx → acquired connection → transaction SQL → Commit/Rollback | pgxpool/tx.go trả connection khi kết thúc; cancel begin context không tự rollback toàn transaction |
| batch | Pool.SendBatch → Conn.SendBatch → BatchResults.Close | Giảm round trip; giữ connection tới close/kết thúc transaction. Không quên kiểm lỗi Close |
| bulk | Pool.CopyFrom → Acquire → Conn.CopyFrom → Release | COPY thích hợp ingest, không tự cung cấp ON CONFLICT của online upsert |

Đã đọc các hàm điều phối trên và đối chiếu tài liệu chính thức. Chưa audit toàn bộ tree matching, pgconn wire protocol, TLS/cancel races hoặc PostgreSQL engine. Source head có thể khác release đang dùng: luôn pin driver/Go/DB trước đo.

## 2. HTTP → auth → admission

Giữ net/http và chi để được HTTP parsing/keep-alive đáng tin, tránh mang raw parser contest vào sản phẩm. Chain nên có request identity/trace, recover, body/header budget, deadline và auth/ACL theo endpoint. Chỉ thêm middleware có chức năng cần; đo CPU/copies của logging, compression, body parsing. Không log payload/SQL parameters nhạy cảm để lấy profile.

Giới hạn header/body/ReadHeaderTimeout và keep-alive theo ingress thật. Timeout riêng cho upload/stream; WriteTimeout quá ngắn có thể cắt stream hợp lệ. CORS không thay authentication. JWT signature không chứng minh user/tenant còn active; schema validation không thay quyền truy cập.

Admission hữu hạn trước công việc đắt: cap inflight và thời gian chờ; hết budget trả lỗi có kiểm soát. Semaphore chỉ cap executing, nếu mọi goroutine đứng chờ vô hạn thì memory vẫn tăng. Fan-out xuống nhiều service phải có concurrency và retry budget chung. Request deadline truyền xuyên pool/query/RPC; không thay bằng context.Background trên đường xử lý chỉ để bỏ overhead.

**Dấu hiệu cần đo:** p99 tăng nhưng CPU thấp → xem pool/locks/network/downstream, không vội thay router. CPU cao → CPU profile phân biệt JSON/auth/query/middleware. Goroutine tăng liên tục → trace/block profile tìm nơi chờ và cancellation bị bỏ qua.

## 3. Admission → pool → query

Tạo một pool dài hạn mỗi process; không connect/disconnect mỗi request. Tổng budget gồm replica × process × MaxConns, cộng workers/migration/admin; giữ chỗ DB vận hành. Không chọn MaxConns theo số VU hay công thức cố định theo core: tăng tới khi throughput không tăng hoặc lock/CPU/latency xấu đi thì đã qua điểm hữu ích.

Đo acquire wait, acquired/idle/total connection, canceled acquire, query time, transaction age. Pool wait cao có thể do query chậm, leaked rows, transaction giữ lâu hoặc pool quá nhỏ; tăng pool có thể làm DB tắc nặng hơn.

Với Query: defer rows.Close ngay sau kiểm lỗi, Scan typed fields, kiểm rows.Err sau Next. Với QueryRow: luôn Scan. Khi Acquire trực tiếp: defer Release. Không giữ rows/connection để chờ client đọc chậm nếu có thể đọc một page giới hạn rồi đóng. Streaming dữ liệu lớn cần đánh đổi rõ memory vs thời gian giữ connection và snapshot; giới hạn stream concurrent riêng.

Prepared statements/cache giúp bỏ parse/describe lặp khi query shape ổn định, nhưng lifecycle là theo connection. SQL sinh vô hạn theo danh sách placeholder có thể làm cache churn. PgBouncer/mode pool/protocol cần cấu hình tương thích; không mặc định tắt prepare hoặc bắt bật mọi nơi. Dùng parameter values, không nối chuỗi dữ liệu người dùng.

## 4. Luồng read feed/detail/list

1. ACL/tenant predicate và limit cứng trước.
2. Index khớp filter + order, ví dụ tenant_id, created_at DESC, id DESC; đây là ví dụ cần xác minh distribution, không index mặc định cho mọi app.
3. Keyset theo cặp thời gian/ID; không dùng sequence ID như commit time. Cursor phải giữ timezone/precision và sort ổn định.
4. Chỉ chọn cột cần. Page newest trước rồi lookup/count; tránh aggregate toàn likes mới LIMIT.
5. Một query có correlated index lookup không đồng nghĩa N network round trips. So actual plan và rows/loops, không đánh giá chỉ bằng hình thức SQL.
6. Exact count rất lớn có chi phí thật; nếu SLO cho phép dùng read model/counter/cache với staleness và reconcile rõ.
7. Đóng rows rồi encode/send; typed DTO trước custom byte writer. Đo bytes/allocs và app CPU so với DB CPU khi thử json_agg phía DB.

EXPLAIN (ANALYZE, BUFFERS) trên fixture đại diện: xem estimated vs actual rows, loops, sort spill, rows removed, heap fetches và buffers. ANALYZE thực thi query; mutation phải kiểm trong môi trường an toàn và lưu ý side effects không hoàn tác như sequence. Statistics lệch → ANALYZE/extended stats khi cột tương quan; không ép planner bằng cách tắt scan global.

Read replica tăng read capacity nhưng replication lag có thể phá read-your-writes. Route read sau write theo consistency contract. Cache key gồm tenant/quyền/filter/cursor; chống stampede bằng bounded coalescing, không lưu cache auth decision vô hạn.

## 5. Luồng create/like/update

Auth/validate → admission → BeginTx → SQL parameterized/constraints → outbox nếu cần → COMMIT → success. Không mở transaction trước khi đợi remote API. Transaction càng lâu giữ lock/connection/snapshot càng lâu.

Like: unique(user_id, post_id) + INSERT ON CONFLICT DO NOTHING; phân biệt duplicate với missing post/user theo nghiệp vụ. Không dùng check-then-insert ngoài transaction để “tránh lỗi”. Hot counter row có thể serialize updates: đo row-lock wait, không mặc định thêm goroutine. Counter sharding/read model chỉ khi có nhu cầu và đối soát được.

Update cạnh tranh: atomic UPDATE ... WHERE version=... RETURNING hoặc row lock cho invariant cần thiết; kiểm affected rows. Isolation Serializable có thể cần retry toàn transaction. Retry serialization/deadlock bounded với jitter; không retry mọi SQL error. Unique violation có thể là kết quả idempotency chứ không phải lỗi phải lặp.

Idempotency key gắn user/operation và request hash; lưu kết quả trong cùng transaction nghiệp vụ. Client mất kết nối lúc commit có thể không biết kết quả: timeout không chứng minh rollback. Tra idempotency state trước retry. Outbox cùng transaction tránh DB commit rồi publish thất bại làm mất event; consumer dedupe vì delivery có thể lặp.

Cleanup: defer rollback với context cleanup có giới hạn độc lập nếu request context đã canceled; vẫn kiểm commit error. Không để context.Background vô hạn. pgx không tự rollback vì begin context bị cancel. pgx Commit báo ErrTxCommitRollback nếu COMMIT kết thúc bằng rollback trên transaction aborted; đừng chỉ thấy đã gọi Commit là gửi 201.

## 6. Group commit, pgx Batch và COPY khác nhau

| Kỹ thuật | Phần chi phí giảm | Giá và điều kiện |
|---|---|---|
| PostgreSQL WAL group commit | Nhiều transaction chia sẻ WAL flush | DB tự phối hợp; không cần gom mọi request vào app transaction |
| Một transaction nhiều rows | BEGIN/COMMIT và commit cost mỗi item | Atomicity/failure chung; thích hợp cùng business operation hoặc ingest |
| pgx SendBatch | Client/server round trips | Đọc/đóng results đúng thứ tự; source đọc ghi default implicit transaction; một lỗi có thể ảnh hưởng các lệnh cùng batch |
| Multi-row/UNNEST | Command/protocol/row handling overhead | Cap rows/bytes, parameter types, result mapping và payload memory |
| COPY | Truyền bulk theo stream/protocol hiệu quả | Dedupe/upsert có thể cần staging rồi merge; constraints/errors vẫn có chi phí |

Không bê SQLite statement failure semantics sang PG: PG error trong transaction cần rollback hoặc savepoint. Savepoint/request cô lập được một số lỗi nhưng thêm command/complexity. Batch queue cần count + bytes + age + shutdown drain + retry/idempotency; low load không nên phải chờ timer dài chỉ để batch đẹp.

## 7. PostgreSQL vận hành quyết định tail latency

MVCC giúp read/write concurrency nhưng tạo tuple versions; transaction lâu có thể cản vacuum. Autovacuum, dead tuples, table/index bloat, replication slot retention và WAL/checkpoint phải quan sát cùng query latency. Index-only scan còn phụ thuộc visibility map, không chỉ có INCLUDE.

work_mem áp cho operation và có thể nhân theo query/concurrency/parallel worker; tăng global có thể OOM. Index thêm tăng write/WAL/storage/vacuum cost. Partial index phải khớp predicate; expression index phải khớp biểu thức. Không có bộ tham số “bùa chú” dùng cho mọi DB.

Durability: giữ synchronous_commit/fsync theo hợp đồng dữ liệu. SQLite NORMAL khác mức local durable PG thường dùng. Replication synchronous/async và backup/PITR là các bảo đảm khác nhau; replication không thay backup. Checkpoint tuning dàn I/O, không xóa tổng I/O.

## 8. Go runtime: tối ưu sau khi profile

- Reuse clients/transports; HTTP downstream connection reuse cần xử lý body/close đúng. Không tạo client/pool theo request.
- Goroutine rẻ nhưng không miễn phí: bounded worker cho CPU task; concurrency chờ IO khác parallel CPU.
- GOMAXPROCS theo CPU quota thực, không copy 1 từ benchmark vào deployment nhiều core.
- Allocation: scan struct, preallocate slice theo page limit, tránh map/interface/format dư trên hot path nếu profile chứng minh. Không pool mọi object.
- sync.Pool không phải cache bền hoặc hard memory bound; không trả buffer khi consumer/socket còn dùng; bỏ buffer quá lớn sau burst nếu retention đắt.
- GOMEMLIMIT chừa native/cgo/socket/OS memory; nó không phải hard cap RSS. GC tuning cần xem pause/CPU và throughput cùng lúc.
- PGO dùng profile đại diện và kiểm build repeatable; không hứa tăng tốc cố định. Custom C/unsafe thêm kiểm ABI/lifetime/race/sanitizer, không chỉ Go race detector.

## 9. Chuyển mindset vào dự án cũ

| Triệu chứng | Bằng chứng cần lấy | Thử nghiệm nhỏ đầu tiên |
|---|---|---|
| CPU cao, DB rảnh | pprof CPU/alloc, response bytes | Giảm hydrate/encode/log trùng trên một endpoint |
| CPU thấp, p99 cao | pool wait, locks, remote spans | Đóng rows/transaction sớm; giảm query/RPC round trip |
| Tải tăng rồi RAM tăng | inflight/queue/goroutine/cgroup | Cap queue + timeout; kiểm đường hủy và slow consumer |
| Write chậm theo burst | commit/row lock/WAL IO | Tách hot key; batch theo nghiệp vụ; giữ durability |
| Càng nhiều connection càng chậm | throughput vs pool size, DB runnable/waits | Giảm pool, admission trước DB |
| Sau deploy bị spike | connection churn, cache cold, migrations | Warmup có giới hạn, lifetime jitter, graceful drain |

Mỗi experiment: SHA/runtime/DB/schema/dataset → baseline → chỉ đổi một nhóm nguyên nhân → correctness/side effects → fixed arrival-rate + closed-loop → so p99/error/CPU/RAM/cost. Không lấy số connection/VU thay cho RPS. Kiểm generator dropped work và tài nguyên để tránh đo chính bottleneck client.

## 10. Phần đã kiểm và việc còn lại

Đã đọc source chi ServeHTTP/routeHTTP/Timeout, pgxpool Acquire/Query/QueryRow/BeginTx/SendBatch/CopyFrom, poolRows/poolRow release, pool Tx commit/rollback và Conn.SendBatch/BeginTx. Không chạy DB thật, chưa đo chi vs ServeMux/Gin, chưa integration-test cancellation/leak dưới overload. Vì vậy đây là map có source và hypothesis đo, không phải chứng nhận mọi luồng production đã pass.

Đợt tiếp theo nên dựng fixture Go+chi+pgxpool: feed/detail/create/like, fixture PostgreSQL riêng, test duplicate concurrent like, rollback/commit failure, expired deadline, rows leak negative case, retry idempotency và graceful drain; sau đó đo query/pool/serialization riêng. Không cần tự viết HTTP parser để làm đợt này.

Nguồn: [chi](https://github.com/go-chi/chi), [pgxpool](https://pkg.go.dev/github.com/jackc/pgx/v5/pgxpool), [Go diagnostics](https://go.dev/doc/diagnostics), [PostgreSQL performance](https://www.postgresql.org/docs/current/performance-tips.html), [PostgreSQL WAL](https://www.postgresql.org/docs/current/runtime-config-wal.html). Các gợi ý ngoài phần source đã đọc là thiết kế cần đo trên ứng dụng thật.
