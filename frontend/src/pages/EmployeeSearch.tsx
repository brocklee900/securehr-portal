import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Department, EmployeeRow, EmployeeSortColumn, SortDirection } from "../api";
import { Flex,  Table, TableProps, Tag } from "antd";


const PAGE_SIZE = 25;

export default function EmployeeSearch() {
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("");
  const [title, setTitle] = useState("");
  const [searchText, setSearchText] = useState({ q: "", title: "" });
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
  const debouncing = q !== searchText.q || title !== searchText.title;
  const busy = loading || debouncing;

  
  useEffect(() => { api.departments().then(setDepts).catch((e) => setError(String(e))); }, []);
  useEffect(() => {
    if (!debouncing) return;
    const t = setTimeout(() => {
      setSearchText({ q, title });
      // Reset together with the new text so we don't fetch page 1 with the old search.
      setPage(1);
    }, 250);
    return () => clearTimeout(t);
  }, [q, title, debouncing]);

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
    api.searchEmployees({ q: searchText.q.length >= 2 ? searchText.q : "", dept, title: searchText.title,
      hiredFrom, hiredTo, page, sortBy: sort.column, sortDir: sort.direction })
      .then((r) => { if (active) { setRows(r.items); setTotal(r.total); setError(""); } })
      .catch((e) => { if (active) setError(String(e)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [searchText, dept, hiredFrom, hiredTo, page, sort, invalidDateRange]);

  const sortOrderFor = (col: EmployeeSortColumn) =>
    sort.column === col ? (sort.direction === "asc" ? "ascend" : "descend") : null;

  const tableColumns: TableProps<EmployeeRow>["columns"] = [
    {
      title: "Name",
      key: "name",
      sorter: true,
      sortOrder: sortOrderFor("name"),
      sortDirections: ["ascend", "descend"],
      render: (_, r) => (
        <Link to={`/employees/${r.emp_no}`}>{r.last_name} {r.first_name}</Link>
      ),
    },
    {
      title: "Title",
      dataIndex: "title",
      key: "title",
      sorter: true,
      sortOrder: sortOrderFor("title"),
      sortDirections: ["ascend", "descend"],
    },
    {
      title: "Department",
      dataIndex: "dept_name",
      key: "department",
      sorter: true,
      sortOrder: sortOrderFor("department"),
      sortDirections: ["ascend", "descend"],
    },
    {
      title: "Hired Date",
      dataIndex: "hire_date",
      key: "hire_date",
      sorter: true,
      sortOrder: sortOrderFor("hire_date"),
      sortDirections: ["ascend", "descend"],
      render: (v: string) => new Date(v).toLocaleDateString(),
    },
  ];

  const handleTableChange: TableProps<EmployeeRow>["onChange"] = (pager, _filters, sorter) => {
    const s = Array.isArray(sorter) ? sorter[0] : sorter;
    const column = (s?.order ? s.columnKey : "name") as EmployeeSortColumn;
    const direction: SortDirection = s?.order === "descend" ? "desc" : "asc";

    if (column !== sort.column || direction !== sort.direction) {
      setSort({ column, direction });
      setPage(1); // new sort order: start from the first page
    } else {
      setPage(pager.current ?? 1);
    }
  };


  return (
    <section>
    
      <h2>Employee directory</h2>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end" }}>
        <label style={{ display: "grid", gap: 4 }}>
          Name
          <input placeholder="Search by name…" value={q} onChange={(e) => setQ(e.target.value)} />
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
          <input placeholder="Search by title…" value={title} onChange={(e) => setTitle(e.target.value)} />
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
      
      
      <Table<EmployeeRow>
        columns={tableColumns}
        dataSource={rows}
        rowKey="emp_no"
        loading={busy}
        onChange={handleTableChange}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showSizeChanger: false,
          showTotal: (t) => `Total ${t.toLocaleString()} results`,
        }}
      />
      
    </section>

  );
}
