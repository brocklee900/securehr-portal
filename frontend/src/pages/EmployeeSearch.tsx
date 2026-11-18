import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Department, EmployeeRow, EmployeeSortColumn, SortDirection } from "../api";

const columns: { key: EmployeeSortColumn; label: string }[] = [
  { key: "name", label: "Name" },
  { key: "title", label: "Title" },
  { key: "department", label: "Department" },
  { key: "hire_date", label: "Hired Date" },
];

export default function EmployeeSearch() {
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("");
  const [page, setPage] = useState(1);
  const [depts, setDepts] = useState<Department[]>([]);
  const [rows, setRows] = useState<EmployeeRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [sort, setSort] = useState<{ column: EmployeeSortColumn; direction: SortDirection }>({ column: "name", direction: "asc" });
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.departments().then(setDepts).catch((e) => setError(String(e))); }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    const t = setTimeout(() => {
      api.searchEmployees(q.length >= 2 ? q : "", dept, page, sort.column, sort.direction)
        .then((r) => { if (active) { setRows(r.items); setTotal(r.total); setError(""); } })
        .catch((e) => { if (active) setError(String(e)); })
        .finally(() => { if (active) setLoading(false); });
    }, 250);
    return () => { active = false; clearTimeout(t); };
  }, [q, dept, page, sort]);

  function sortBy(column: EmployeeSortColumn) {
    setSort((previous) => ({
      column,
      direction: previous.column === column && previous.direction === "asc" ? "desc" : "asc",
    }));
    setPage(1);
  }

  return (
    <section>
      <h2>Employee directory</h2>
      <input placeholder="Search by name…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />{" "}
      <select value={dept} onChange={(e) => { setDept(e.target.value); setPage(1); }}>
        <option value="">All departments</option>
        {depts.map((d) => <option key={d.dept_no} value={d.dept_no}>{d.dept_name}</option>)}
      </select>
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
      <table width="100%" aria-busy={loading} style={{ marginTop: 12, borderCollapse: "collapse" }}>
        <thead><tr>{columns.map(({ key, label }) => (
          <th key={key} scope="col" align="left" aria-sort={sort.column === key ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}>
            <button
              type="button"
              onClick={() => sortBy(key)}
              aria-label={`${label}, sort ${sort.column === key && sort.direction === "asc" ? "descending" : "ascending"}`}
              style={{ border: 0, background: "none", padding: "4px 0", font: "inherit", color: "inherit", cursor: "pointer" }}
            >
              {label} <span aria-hidden="true">{sort.column === key ? (sort.direction === "asc" ? "↑" : "↓") : "↕"}</span>
            </button>
          </th>
        ))}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.emp_no}>
              <td><Link to={`/employees/${r.emp_no}`}>{r.last_name}, {r.first_name}</Link></td>
              <td>{r.title}</td><td>{r.dept_name}</td><td>{r.hire_date}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        <button disabled={loading || page === 1} onClick={() => setPage(page - 1)}>Prev</button>{" "}
        Page {page} of {Math.max(1, Math.ceil(total / 25))} ({total.toLocaleString()} results){" "}
        <button disabled={loading || page * 25 >= total} onClick={() => setPage(page + 1)}>Next</button>
      </p>
    </section>
  );
}
