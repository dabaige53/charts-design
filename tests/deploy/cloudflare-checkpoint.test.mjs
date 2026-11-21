import { test, expect } from "bun:test";
import { Database } from "bun:sqlite";
import { WorkspaceCheckpoint } from "../../deploy/cloudflare/checkpoint.mjs";

// @wu-test type=integration | scope=Cloudflare 工作区保存和恢复 | protects=失败的归档覆盖上次确认的数据或冷启动遗漏分块
test("only a complete archive replaces the last recoverable workspace", async () => {
  const db = new Database(":memory:");
  const storage = {
    sql: { exec(sql, ...args) {
      const rows = db.query(sql).all(...args);
      return { toArray: () => rows };
    } },
    transactionSync: action => db.transaction(action)(),
  };
  const state = new WorkspaceCheckpoint(storage);
  const bytes = crypto.getRandomValues(new Uint8Array(8192));
  const container = (chunks, exitCode) => ({ exec: async () => ({ stdout: chunks, exitCode }) });
  await state.save(container([bytes, bytes], 0));
  await expect(state.save(container([new Uint8Array([0])], 1))).rejects.toThrow("checkpoint failed");
  let restored;
  await new WorkspaceCheckpoint(storage).restore({
    async exec(command, { stdin }) {
      restored = await new Response(stdin).arrayBuffer();
      return { exitCode: 0 };
    },
  });
  expect(Buffer.from(restored)).toEqual(Buffer.concat([bytes, bytes]));
  db.close();
});
