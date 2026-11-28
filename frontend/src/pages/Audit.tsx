import { useEffect, useState } from "react";
import { Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import { api, AuditRow } from "../api";

const ACTIONS = ["", "search", "read", "list", "create", "denied"];
const PAGE_SIZE = 50;

const columns: ColumnsType<AuditRow> = [
  {
    title: "Time",
    dataIndex: "at",
    render: (v: string) => new Date(v).toLocaleString(),
    sorter: (a, b) => new Date(a.at).getTime() - new Date(b.at).getTime(),
  },
  {
    title: "User",
    dataIndex: "username",
    sorter: (a, b) => (a.username ?? "").localeCompare(b.username ?? ""),
  },
  {
    title: "Role",
    dataIndex: "role",
    sorter: (a, b) => (a.role ?? "").localeCompare(b.role ?? ""),
  },
  {
    title: "Action",
    dataIndex: "action",
    sorter: (a, b) => (a.action ?? "").localeCompare(b.action ?? ""),
  },
  {
    title: "Resource",
    dataIndex: "resource",
    sorter: (a, b) => (a.resource ?? "").localeCompare(b.resource ?? ""),
  },
  {
    title: "Detail",
    dataIndex: "detail",
    render: (v: unknown) => <code>{JSON.stringify(v)}</code>,
  },
];

export default function Audit() {
  const [username, setUsername] = useState("");
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      api.audit(username.trim(), action, page)
        .then((r) => { setRows(r.items); setTotal(r.total); setError(""); })
        .catch((e) => setError(String(e)))
        .finally(() => setLoading(false));
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
      <Table<AuditRow>
        style={{ marginTop: 12 }}
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={loading}
        scroll={{ x: "max-content" }}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showSizeChanger: false,
          showTotal: (t) => `${t.toLocaleString()} entries`,
          onChange: (p) => setPage(p),
        }}
      />
    </section>
  );
}