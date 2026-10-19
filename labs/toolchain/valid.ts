import { Database } from "bun:sqlite";

const db = new Database(":memory:");
const query = db.query<{ value: number }, []>("SELECT 42 AS value");
const server = Bun.serve({
  hostname: "127.0.0.1",
  port: 0,
  fetch() {
    return Response.json(query.get());
  },
});
try {
  const response = await fetch(server.url);
  console.log(JSON.stringify({ status: response.status, data: await response.json() }));
} finally {
  server.stop(true);
  db.close();
}
