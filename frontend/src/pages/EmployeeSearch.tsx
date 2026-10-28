import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Department, EmployeeRow } from "../api";

export default function EmployeeSearch() {
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("");
  const [page, setPage] = useState(1);
  const [depts, setDepts] = useState<Department[]>([]);
  const [rows, setRows] = useState<EmployeeRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => { api.departments().then(setDepts).catch((e) => setError(String(e))); }, []);
  useEffect(() => {
    const t = setTimeout(() => {
      api.searchEmployees(q.length >= 2 ? q : "", dept, page)
        .then((r) => { setRows(r.items); setTotal(r.total); setError(""); })
        .catch((e) => setError(String(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [q, dept, page]);

  return (
    <section>
      <h2>Employee directory</h2>
      <input placeholder="Search by name…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />{" "}
      <select value={dept} onChange={(e) => { setDept(e.target.value); setPage(1); }}>
        <option value="">All departments</option>
        {depts.map((d) => <option key={d.dept_no} value={d.dept_no}>{d.dept_name}</option>)}
      </select>
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
      <table width="100%" style={{ marginTop: 12, borderCollapse: "collapse" }}>
        <thead><tr><th align="left">Name</th><th align="left">Title</th><th align="left">Department</th><th align="left">Hired</th></tr></thead>
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
        <button disabled={page === 1} onClick={() => setPage(page - 1)}>Prev</button>{" "}
        Page {page} of {Math.max(1, Math.ceil(total / 25))} ({total.toLocaleString()} results){" "}
        <button disabled={page * 25 >= total} onClick={() => setPage(page + 1)}>Next</button>
      </p>
    </section>
  );
}
