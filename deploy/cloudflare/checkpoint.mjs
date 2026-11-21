export class WorkspaceCheckpoint {
  constructor(storage) {
    this.storage = storage;
    this.sql = storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS workspace (part INTEGER PRIMARY KEY, bytes BLOB NOT NULL)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS staging (part INTEGER PRIMARY KEY, bytes BLOB NOT NULL)");
    this.sql.exec("DELETE FROM staging");
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
    });
  }
}
