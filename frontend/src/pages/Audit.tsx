import { useEffect, useState } from "react";
import { api, AuditRow } from "../api";

const ACTIONS = ["", "search", "read", "list"];

export default function Audit() {
  const [username, setUsername] = useState("");
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      api.audit(username.trim(), action, page)
        .then((r) => { setRows(r.items); setTotal(r.total); setError(""); })
        .catch((e) => setError(String(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [username, action, page]);

  return (
    <section>
      <h2>Audit log</h2>
      <input placeholder="Filter by username…" value={username}
        onChange={(e) => { setUsername(e.target.value); setPage(1); }} />{" "}
      <select value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }}>
        {ACTIONS.map((a) => <option key={a} value={a}>{a || "All actions"}</option>)}
      </select>
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
      <div style={{ overflowX: "auto" }}>
        <table width="100%" style={{ marginTop: 12, borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr><th align="left">Time</th><th align="left">User</th><th align="left">Role</th>
              <th align="left">Action</th><th align="left">Resource</th><th align="left">Detail</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{new Date(r.at).toLocaleString()}</td><td>{r.username}</td><td>{r.role}</td>
                <td>{r.action}</td><td>{r.resource}</td>
                <td><code>{JSON.stringify(r.detail)}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        <button disabled={page === 1} onClick={() => setPage(page - 1)}>Prev</button>{" "}
        Page {page} of {Math.max(1, Math.ceil(total / 50))} ({total.toLocaleString()} entries){" "}
        <button disabled={page * 50 >= total} onClick={() => setPage(page + 1)}>Next</button>
      </p>
    </section>
  );
}
