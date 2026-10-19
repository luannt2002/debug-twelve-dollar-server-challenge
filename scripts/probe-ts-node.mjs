import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';

// Chỉ dùng source snapshot và SQLite in-memory; không mở server hoặc kết nối mạng.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = 'snapshots/pr-78/submissions/node-net-barrard/index.js';
const source = fs.readFileSync(path.join(root, sourcePath), 'utf8');
const start = source.indexOf('function parseHead(');
const end = source.indexOf('\nfunction onConnection', start);
if (start < 0 || end < 0) throw new Error('parseHead source boundaries not found');
const context = vm.createContext({});
vm.runInContext(source.slice(start, end), context, { timeout: 1000 });
const heads = [
  ['conflicting_content_length', 'POST /posts HTTP/1.1\r\nContent-Length: 1\r\nContent-Length: 2'],
  ['transfer_encoding_with_content_length', 'POST /posts HTTP/1.1\r\nContent-Length: 2\r\nTransfer-Encoding: chunked'],
  ['complete_oversized_header', 'GET /feed HTTP/1.1\r\nX: ' + 'a'.repeat(9000)],
];
const httpParser = heads.map(([name, head]) => {
  const result = context.parseHead(head);
  return {
    name,
    bytes: Buffer.byteLength(head),
    result: result === null ? null : {
      method: result.method, length: result.length, chunked: result.chunked,
    },
  };
});
const db = new DatabaseSync(':memory:');
let feedOrdering;
let transactionVisibility;
try {
  db.exec("CREATE TABLE posts(id INTEGER PRIMARY KEY, created_at TEXT); INSERT INTO posts VALUES (1,'z'),(2,'a')");
  feedOrdering = {
    byId: db.prepare('SELECT id FROM posts ORDER BY id DESC').all().map(row => row.id),
    byTimestamp: db.prepare('SELECT id FROM posts ORDER BY created_at DESC,id DESC').all().map(row => row.id),
  };
  db.exec('CREATE TABLE pending_posts(id INTEGER); BEGIN; INSERT INTO pending_posts VALUES(1)');
  const beforeCommit = db.prepare('SELECT COUNT(*) n FROM pending_posts').get().n;
  db.exec('ROLLBACK');
  transactionVisibility = {
    sameConnectionBeforeCommit: beforeCommit,
    afterRollback: db.prepare('SELECT COUNT(*) n FROM pending_posts').get().n,
    scope: 'SQLite semantics only; not an end-to-end Deno poller or fault-injection test',
  };
} finally {
  db.close();
}
const emoji = Buffer.from('😀');
const result = {
  runtime: { node: process.version, platform: process.platform, arch: process.arch },
  sourcePath,
  httpParser,
  feedOrdering,
  transactionVisibility,
  unicode: { utf16Units: '😀'.repeat(500).length, codePoints: [...'😀'.repeat(500)].length },
  utf8Chunks: {
    splitBufferDecoded: emoji.subarray(0, 2).toString() + emoji.subarray(2).toString(),
    wholeBufferDecoded: emoji.toString(),
  },
  i32Illustration: {
    input: 4294967297,
    jsBitwiseI32: 4294967297 | 0,
    scope: 'JavaScript illustrative coercion only; Deno FFI and C cast not executed',
  },
};
process.stdout.write(JSON.stringify(result, null, 2) + '\n');
