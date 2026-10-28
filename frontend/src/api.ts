import { keycloak } from "./auth";

export interface EmployeeRow {
  emp_no: number; first_name: string; last_name: string; hire_date: string;
  dept_no: string | null; dept_name: string | null; title: string | null;
}
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface Department { dept_no: string; dept_name: string; headcount: number }
export interface Salary { salary: number; from_date: string; to_date: string }
export interface Title { title: string; from_date: string; to_date: string }

async function get<T>(path: string): Promise<T> {
  await keycloak.updateToken(30);
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${keycloak.token}` } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  searchEmployees: (q: string, dept: string, page: number) =>
    get<Page<EmployeeRow>>(`/employees?page=${page}&page_size=25${q ? `&q=${encodeURIComponent(q)}` : ""}${dept ? `&dept_no=${dept}` : ""}`),
  employee: (id: string) => get<EmployeeRow & { gender?: string; birth_date?: string }>(`/employees/${id}`),
  titles: (id: string) => get<Title[]>(`/employees/${id}/titles`),
  salaries: (id: string) => get<Salary[]>(`/employees/${id}/salaries`),
  departments: () => get<Department[]>("/departments"),
  department: (no: string) => get<{ dept_no: string; dept_name: string; managers: { emp_no: number; first_name: string; last_name: string }[] }>(`/departments/${no}`),
};
