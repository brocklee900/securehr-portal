import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, EmployeeRow, Salary, Title } from "../api";
import { canSeeSalary, Role } from "../auth";
import SalaryChange from "./SalaryChange";

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

  if (!emp) return <p>Loading…</p>;
  return (
    <section>
      <h2>{emp.first_name} {emp.last_name} <small>#{emp.emp_no}</small></h2>
      <p>{emp.title} — {emp.dept_name} · hired {emp.hire_date}</p>
      <h3>Title history</h3>
      <ul>{titles.map((t, i) => (
        <li key={i}>{t.title}: {t.from_date} → {t.to_date === CURRENT ? "present" : t.to_date}{historyLabel(t, todayIso)}</li>
      ))}</ul>
      {canSeeSalary(role) && (
        <>
          <h3>Salary history</h3>
          {salaryMsg && <p>{salaryMsg}</p>}
          <ul>{salaries?.map((s, i) => (
            <li key={i}>${s.salary.toLocaleString()}: {s.from_date} → {s.to_date === CURRENT ? "present" : s.to_date}{historyLabel(s, todayIso)}</li>
          ))}</ul>
          {role === "hr_admin" && <SalaryChange key={id} empNo={id} onChanged={loadSalaries} />}
        </>
      )}
    </section>
  );
}
