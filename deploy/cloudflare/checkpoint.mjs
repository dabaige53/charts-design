export class WorkspaceCheckpoint {
  constructor(storage) {
    this.storage = storage;
    this.sql = storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS workspace (part INTEGER PRIMARY KEY, bytes BLOB NOT NULL)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS staging (part INTEGER PRIMARY KEY, bytes BLOB NOT NULL)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS annotation_parts (share_id TEXT, part INTEGER, bytes BLOB NOT NULL, PRIMARY KEY(share_id, part))");
    this.sql.exec("CREATE TABLE IF NOT EXISTS annotation_staging (share_id TEXT, part INTEGER, bytes BLOB NOT NULL, PRIMARY KEY(share_id, part))");
    this.sql.exec("DELETE FROM staging");
    this.sql.exec("DELETE FROM annotation_staging");
  }

  async restore(container) {
    const [{ parts }] = this.sql.exec("SELECT count(*) AS parts FROM workspace").toArray();
    if (!parts) return;
    let part = 0;
    const stream = new ReadableStream({
      pull: controller => {
        const [{ bytes }] = this.sql.exec("SELECT bytes FROM workspace WHERE part=?", part++).toArray();
        controller.enqueue(new Uint8Array(bytes));
        if (part === parts) controller.close();
      },
    });
    const restore = await container.exec(["tar", "-xzf", "-", "-C", "/data"], {
      stdin: stream, stdout: "ignore", stderr: "ignore", user: "10001:10001",
    });
    if (await restore.exitCode !== 0) throw new Error("Workspace restore failed");
    for (const { share_id, parts } of this.sql.exec(
      "SELECT share_id, count(*) AS parts FROM annotation_parts GROUP BY share_id").toArray()) {
      let part = 0;
      const stream = new ReadableStream({
        pull: controller => {
          const [{ bytes }] = this.sql.exec("SELECT bytes FROM annotation_parts WHERE share_id=? AND part=?", share_id, part++).toArray();
          controller.enqueue(new Uint8Array(bytes));
          if (part === parts) controller.close();
        },
      });
      const restored = await container.exec(["tar", "-xzf", "-", "-C", "/data"], {
        stdin: stream, stdout: "ignore", stderr: "ignore", user: "10001:10001",
      });
      if (await restored.exitCode !== 0) throw new Error("Annotation restore failed");
    }
  }

  async save(container) {
    const archive = await container.exec(["tar", "-czf", "-", "-C", "/data", "."], {
      stdout: "pipe", stderr: "ignore", user: "10001:10001",
    });
    this.sql.exec("DELETE FROM staging");
    let part = 0;
    for await (const bytes of archive.stdout) {
      for (let offset = 0; offset < bytes.length; offset += 256 * 1024) {
        this.sql.exec("INSERT INTO staging VALUES (?, ?)", part++, bytes.slice(offset, offset + 256 * 1024));
      }
    }
    if (!part || await archive.exitCode !== 0) throw new Error("Workspace checkpoint failed");
    this.storage.transactionSync(() => {
      this.sql.exec("DELETE FROM workspace");
      this.sql.exec("INSERT INTO workspace SELECT * FROM staging");
      this.sql.exec("DELETE FROM staging");
      // The successful full snapshot now includes every prior annotation write.
      this.sql.exec("DELETE FROM annotation_parts");
    });
  }

  async saveAnnotations(container, shareId) {
    if (!/^[0-9a-f]{32}$/.test(shareId)) throw new Error("Invalid share ID");
    const archive = await container.exec(["tar", "-czf", "-", "-C", "/data",
      `runtime/private-shares/shares/${shareId}/annotations.sqlite3`], {
      stdout: "pipe", stderr: "ignore", user: "10001:10001",
    });
    this.sql.exec("DELETE FROM annotation_staging WHERE share_id=?", shareId);
    let part = 0;
    for await (const bytes of archive.stdout) {
      for (let offset = 0; offset < bytes.length; offset += 256 * 1024) {
        this.sql.exec("INSERT INTO annotation_staging VALUES (?, ?, ?)", shareId, part++, bytes.slice(offset, offset + 256 * 1024));
      }
    }
    if (!part || await archive.exitCode !== 0) throw new Error("Annotation checkpoint failed");
    this.storage.transactionSync(() => {
      this.sql.exec("DELETE FROM annotation_parts WHERE share_id=?", shareId);
      this.sql.exec("INSERT INTO annotation_parts SELECT * FROM annotation_staging WHERE share_id=?", shareId);
      this.sql.exec("DELETE FROM annotation_staging WHERE share_id=?", shareId);
    });
  }
}
