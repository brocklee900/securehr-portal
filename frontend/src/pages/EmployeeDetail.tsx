import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, EmployeeRow, Salary, Title } from "../api";
import { canSeeSalary, Role } from "../auth";

export default function EmployeeDetail({ role }: { role: Role }) {
  const { id = "" } = useParams();
  const [emp, setEmp] = useState<(EmployeeRow & { gender?: string; birth_date?: string }) | null>(null);
  const [titles, setTitles] = useState<Title[]>([]);
  const [salaries, setSalaries] = useState<Salary[] | null>(null);
  const [salaryMsg, setSalaryMsg] = useState("");

  useEffect(() => {
    api.employee(id).then(setEmp).catch(() => setEmp(null));
    api.titles(id).then(setTitles).catch(() => setTitles([]));
    if (canSeeSalary(role)) {
      api.salaries(id).then(setSalaries).catch(() => setSalaryMsg("Salary data not available for this employee."));
    }
  }, [id, role]);

  if (!emp) return <p>Loading…</p>;
  return (
    <section>
      <h2>{emp.first_name} {emp.last_name} <small>#{emp.emp_no}</small></h2>
      <p>{emp.title} — {emp.dept_name} · hired {emp.hire_date}</p>
      <h3>Title history</h3>
      <ul>{titles.map((t, i) => <li key={i}>{t.title}: {t.from_date} → {t.to_date}</li>)}</ul>
      {canSeeSalary(role) && (
        <>
          <h3>Salary history</h3>
          {salaryMsg && <p>{salaryMsg}</p>}
          <ul>{salaries?.map((s, i) => <li key={i}>${s.salary.toLocaleString()}: {s.from_date} → {s.to_date}</li>)}</ul>
        </>
      )}
    </section>
  );
}
