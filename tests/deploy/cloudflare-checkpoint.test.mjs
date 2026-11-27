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

// @wu-test type=integration | scope=Cloudflare 独立批注持久化 | protects=每次批注重传页面数据、冷启动丢反馈或失败覆盖最后成功批注
test("annotation checkpoints restore after content without archiving content again", async () => {
  const db = new Database(":memory:");
  const storage = {
    sql: { exec(sql, ...args) { const rows = db.query(sql).all(...args); return { toArray: () => rows }; } },
    transactionSync: action => db.transaction(action)(),
  };
  const state = new WorkspaceCheckpoint(storage);
  const content = new TextEncoder().encode("saved content with parquet data");
  const notes = new TextEncoder().encode("persisted annotations");
  await state.save({ exec: async () => ({ stdout: [content], exitCode: 0 }) });
  const shareId = "a".repeat(32);
  let command;
  await state.saveAnnotations({ exec: async args => {
    command = args; return { stdout: [notes], exitCode: 0 };
  } }, shareId);
  expect(command.at(-1)).toBe(`runtime/private-shares/shares/${shareId}/annotations.sqlite3`);
  expect(Buffer.from(db.query("SELECT bytes FROM workspace").get().bytes)).toEqual(Buffer.from(content));
  await expect(state.saveAnnotations({ exec: async () => ({ stdout: [new Uint8Array([0])], exitCode: 1 }) }, shareId))
    .rejects.toThrow("Annotation checkpoint failed");
  const restored = [];
  await new WorkspaceCheckpoint(storage).restore({ exec: async (_args, { stdin }) => {
    restored.push(Buffer.from(await new Response(stdin).arrayBuffer())); return { exitCode: 0 };
  } });
  expect(restored).toEqual([Buffer.from(content), Buffer.from(notes)]);
  await state.save({ exec: async () => ({ stdout: [content, notes], exitCode: 0 }) });
  expect(db.query("SELECT count(*) AS count FROM annotation_parts").get().count).toBe(0);
  db.close();
});
