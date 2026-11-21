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
  const [title, setTitle] = useState("");
  const [hiredFrom, setHiredFrom] = useState("");
  const [hiredTo, setHiredTo] = useState("");
  const [page, setPage] = useState(1);
  const [depts, setDepts] = useState<Department[]>([]);
  const [rows, setRows] = useState<EmployeeRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [sort, setSort] = useState<{ column: EmployeeSortColumn; direction: SortDirection }>({ column: "name", direction: "asc" });
  const [loading, setLoading] = useState(true);
  const invalidDateRange = Boolean(hiredFrom && hiredTo && hiredFrom > hiredTo);

  useEffect(() => { api.departments().then(setDepts).catch((e) => setError(String(e))); }, []);
  useEffect(() => {
    if (invalidDateRange) {
      setRows([]);
      setTotal(0);
      setError("");
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    const t = setTimeout(() => {
      api.searchEmployees({ q: q.length >= 2 ? q : "", dept, title, hiredFrom, hiredTo,
        page, sortBy: sort.column, sortDir: sort.direction })
        .then((r) => { if (active) { setRows(r.items); setTotal(r.total); setError(""); } })
        .catch((e) => { if (active) setError(String(e)); })
        .finally(() => { if (active) setLoading(false); });
    }, 250);
    return () => { active = false; clearTimeout(t); };
  }, [q, dept, title, hiredFrom, hiredTo, page, sort, invalidDateRange]);

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
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end" }}>
        <label style={{ display: "grid", gap: 4 }}>
          Name
          <input placeholder="Search by name…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          Department
          <select value={dept} onChange={(e) => { setDept(e.target.value); setPage(1); }}>
            <option value="">All departments</option>
            {depts.map((d) => <option key={d.dept_no} value={d.dept_no}>{d.dept_name}</option>)}
          </select>
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          Title
          <input placeholder="Search by title…" value={title} onChange={(e) => { setTitle(e.target.value); setPage(1); }} />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          Hired from
          <input type="date" value={hiredFrom} max={hiredTo || undefined}
            aria-invalid={invalidDateRange} aria-describedby="hire-date-help"
            onChange={(e) => { setHiredFrom(e.target.value); setPage(1); }} />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          Hired to
          <input type="date" value={hiredTo} min={hiredFrom || undefined}
            aria-invalid={invalidDateRange} aria-describedby="hire-date-help"
            onChange={(e) => { setHiredTo(e.target.value); setPage(1); }} />
        </label>
      </div>
      <p id="hire-date-help" role={invalidDateRange ? "alert" : undefined}
        style={{ color: invalidDateRange ? "crimson" : undefined }}>
        {invalidDateRange ? "Hired from must be on or before Hired to." : "Hire dates include both endpoints. Leave either date blank for no limit."}
      </p>
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
          {!loading && !error && !invalidDateRange && rows.length === 0 && (
            <tr><td colSpan={columns.length}>No employees match these filters.</td></tr>
          )}
        </tbody>
      </table>
      <p>
        <button disabled={loading || invalidDateRange || page === 1} onClick={() => setPage(page - 1)}>Prev</button>{" "}
        Page {page} of {Math.max(1, Math.ceil(total / 25))} ({total.toLocaleString()} results){" "}
        <button disabled={loading || invalidDateRange || page * 25 >= total} onClick={() => setPage(page + 1)}>Next</button>
      </p>
    </section>
  );
}
