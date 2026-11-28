import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, EmployeeRow, Salary, Title } from "../api";
import { canSeeSalary, Role } from "../auth";
import SalaryChange from "./SalaryChange";
import { Card, Listy, Space } from "antd";

const CURRENT = "9999-01-01";

/** Marks title and salary entries in effect today or starting later (dates are YYYY-MM-DD strings). */
function historyLabel(entry: Title | Salary, today: string): string {
  if (entry.from_date > today) return " (pending)";
  if (entry.to_date === CURRENT || entry.to_date > today) return " (current)";
  return "";
}

export default function EmployeeDetail({ role }: { role: Role }) {
  const { id = "" } = useParams();
  const [emp, setEmp] = useState<(EmployeeRow & { gender?: string; birth_date?: string }) | null>(null);
  const [titles, setTitles] = useState<Title[]>([]);
  const [salaries, setSalaries] = useState<Salary[] | null>(null);
  const [salaryMsg, setSalaryMsg] = useState("");

  const loadSalaries = useCallback(() => {
    if (!canSeeSalary(role)) return;
    setSalaryMsg("");
    api.salaries(id).then(setSalaries).catch(() => setSalaryMsg("Salary data not available for this employee."));
  }, [id, role]);

  useEffect(() => {
    api.employee(id).then(setEmp).catch(() => setEmp(null));
    api.titles(id).then(setTitles).catch(() => setTitles([]));
    loadSalaries();
  }, [id, loadSalaries]);

  const today = new Date();
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  
  interface Item {
    id: number;
    content: string;
  }

  const salariesItems = salaries?.map((item, k)=> {return {
    id: k,
    content: `${item?.salary?.toLocaleString()} : ${item?.from_date} →  ${item?.to_date === CURRENT ? "present" : item?.to_date} ${historyLabel(item, todayIso)}`
  }});

  const titleItems = titles?.map((item, i) => {
    return {
      id:i,
      content:`${item.title}: ${item.from_date} → ${item.to_date === CURRENT ? "present" : item.to_date} ${historyLabel(item, todayIso)}`
    }
  });

  if (!emp) return <p>Loading…</p>;
  return (
    <section>
       <Space orientation="vertical" size="medium" style={{ display: 'flex' }}>
      <h2>{emp.first_name} {emp.last_name} <small>#{emp.emp_no}</small></h2>
      <p>{emp.title} — {emp.dept_name} · hired {emp.hire_date}</p>
      {/* <h3>Title history</h3> */}
      {/* v<Divider titlePlacement="start">Title history</Divider> */}
      {/* <ul>{titles.map((t, i) => (
        <li key={i}>{t.title}: {t.from_date} → {t.to_date === CURRENT ? "present" : t.to_date}{historyLabel(t, todayIso)}</li>
      ))}</ul> */}
      <Card title="Title history" size="small">
      <Listy<Item>
          items={titleItems}
          height={400} 
          rowKey="id" 
          itemRender={(item) => item.content} 
      />
      </Card>

      {canSeeSalary(role) && (
        <>
          {/* <h3>Salary history</h3> */}
          {/* <Divider titlePlacement="start" dashed>Salary history</Divider> */}
          {salaryMsg && <p>{salaryMsg}</p>}
          {/* <ul>{salaries?.map((s, i) => (vs
            <li key={i}>${s.salary.toLocaleString()}: {s.from_date} → {s.to_date === CURRENT ? "present" : s.to_date}{historyLabel(s, todayIso)}</li>
          ))}</ul> */}
           <Card title="Salary history" size="small">
          <Listy<Item>
             items={salariesItems}
             height={400} 
             rowKey="id" 
             itemRender={(item) => item.content} 
          />
            </Card>
            
          {role === "hr_admin" && <SalaryChange key={id} empNo={id} onChanged={loadSalaries} />}
        </>
      )}
      </Space>
      
    </section>
  );
}
