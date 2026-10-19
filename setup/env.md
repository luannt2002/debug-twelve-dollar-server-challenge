# setup/env.md — dựng môi trường ở máy khác

Mục tiêu: từ một máy sạch, dựng đủ toolchain để (a) chạy probe trong `scripts/`, (b) làm các
đợt trong [ROADMAP.md](../ROADMAP.md). Pin version khi làm đợt đo; bảng dưới là mức tối thiểu.

## 1. Toolchain gốc

| Tool | Mức cần | Cài gợi ý | Kiểm tra |
|---|---|---|---|
| git | bản mới | apt/brew | `git --version` |
| Node.js | LTS (baseline runtime) | nvm hoặc apt | `node --version` |
| Bun | bản mới ổn định | `curl -fsSL https://bun.sh/install \| bash` | `bun --version` |
| Go | bản mới ổn định | tarball chính thức hoặc apt | `go version` |
| Python 3 | ≥ 3.10 (chạy probe) | hệ thống | `python3 --version` |
| gcc/g++ | có C++17 (probe parser C++) | apt build-essential | `g++ --version` |
| Docker + compose | để chạy PostgreSQL đợt 3 | docker official | `docker compose version` |

Lưu ý máy này (đo 15/10/2026): 16 vCPU / 62GB RAM, box dùng chung — load test phải giới hạn
VU/thời gian, không đè service thật.

## 2. TypeScript 7 + Bun (trục 1 + 2) — cấu hình chuẩn dự án TS

```bash
# trong dự án TS của bạn (không phải repo nghiên cứu này)
bun add -d typescript@7 @types/bun
```

`tsconfig.json` tối thiểu cho dự án Bun (TS 7):

```json
{
  "compilerOptions": {
    "target": "esnext",
    "module": "esnext",
    "moduleResolution": "bundler",
    "types": ["bun"],
    "noEmit": true
  }
}
```

`package.json`:

```json
{ "scripts": { "typecheck": "tsc --noEmit" } }
```

Chạy app bằng Bun, kiểm kiểu bằng TS 7:

```bash
bun run src/index.ts    # runtime — Bun strip types, KHÔNG typecheck
bun run typecheck       # CI + editor — tsc native TS 7
```

Ba bẫy đã biết (chi tiết [docs/02](../docs/02-truong-phai-ts7-typescript-go.md)):

1. TS 7 gỡ `moduleResolution: node/node10` → dùng `bundler` / `node16` / `nodenext`.
2. `types` mặc định rỗng → phải khai báo `"types": ["bun"]`, không thì `Bun.serve()`... báo thiếu kiểu.
3. Tool dựa compiler API (typescript-eslint, ts-morph, ts-jest) cần 7.1+ hoặc chạy song song
   TS 6 (alias `@typescript/typescript6`) — kiểm từng cái trước khi tin CI xanh.

## 3. PostgreSQL local (trục 4, đợt 3)

```bash
mkdir -p labs/pg && cat > labs/pg/docker-compose.yml <<'YAML'
services:
  app_pg:
    image: postgres:17
    environment:
      POSTGRES_PASSWORD: debug12
      POSTGRES_DB: challenge
    ports:
      - "55432:5432"
    volumes:
      - ./pgdata:/var/lib/postgresql/data
YAML
docker compose -f labs/pg/docker-compose.yml up -d
# kiểm tra
psql "postgres://postgres:debug12@127.0.0.1:55432/challenge" -c 'select version();'
```

( Nếu chưa có psql client: `docker compose exec app_pg psql -U postgres -d challenge`. )

SQLite: không cần cài — Bun có sẵn `bun:sqlite`, Python có `sqlite3` chuẩn (probe dùng nó).

## 4. Dựng lại source tham khảo

Theo [repos.md](repos.md): clone các repo cần sang thư mục tools riêng. Repo challenge cần
lệnh fetch PR refs riêng (đã ghi ở đó).

## 5. Chạy lại probe nền (kiểm môi trường sống)

```bash
python3 scripts/probe-sqlite.py       # FK OFF mặc định, snapshot read, CHECK không hủy peer
python3 scripts/probe-cpp-parser.py   # parser #9 nhận framing mâu thuẫn
python3 scripts/probe-go.py
node   scripts/probe-ts-node.mjs
python3 scripts/probe-toolchain.py    # phiên bản toolchain tại máy
```

Kết quả JSON rơi vào `evidence/` — đối chiếu với bản 19/10/2026; lệch cơ chế (không phải lệch
số) thì dừng và ghi lại trước khi dùng docs.

## 6. An toàn

- Không chạy `install.sh` của submission với root; không đổi kernel/sysctl.
- Probe chỉ đụng fixture tự dựng trong `labs/`; không trỏ vào DB/service thật.
- Load test: giới hạn VU + duration; box dùng chung thì chạy giờ rảnh.
