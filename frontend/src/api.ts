import { keycloak } from "./auth";

export interface EmployeeRow {
  emp_no: number; first_name: string; last_name: string; hire_date: string;
  dept_no: string | null; dept_name: string | null; title: string | null;
}
export type EmployeeSortColumn = "name" | "title" | "department" | "hire_date";
export type SortDirection = "asc" | "desc";
export interface EmployeeSearchParams {
  q: string; dept: string; title: string; hiredFrom: string; hiredTo: string;
  page: number; sortBy: EmployeeSortColumn; sortDir: SortDirection;
}
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface Department { dept_no: string; dept_name: string; headcount: number }
export interface Salary { salary: number; from_date: string; to_date: string }
export interface AuditRow {
  id: number; at: string; username: string; role: string;
  action: string; resource: string; detail: Record<string, unknown>;
}
export interface Title { title: string; from_date: string; to_date: string }

async function get<T>(path: string): Promise<T> {
  await keycloak.updateToken(30);
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${keycloak.token}` } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  searchEmployees: ({ q, dept, title, hiredFrom, hiredTo, page, sortBy, sortDir }: EmployeeSearchParams) => {
    const params = new URLSearchParams({ page: String(page), page_size: "25", sort_by: sortBy, sort_dir: sortDir });
    if (q) params.set("q", q);
    if (dept) params.set("dept_no", dept);
    if (title) params.set("title", title);
    if (hiredFrom) params.set("hired_from", hiredFrom);
    if (hiredTo) params.set("hired_to", hiredTo);
    return get<Page<EmployeeRow>>(`/employees?${params}`);
  },
  employee: (id: string) => get<EmployeeRow & { gender?: string; birth_date?: string }>(`/employees/${id}`),
  titles: (id: string) => get<Title[]>(`/employees/${id}/titles`),
  salaries: (id: string) => get<Salary[]>(`/employees/${id}/salaries`),
  audit: (username: string, action: string, page: number) =>
    get<Page<AuditRow>>(`/audit?page=${page}&page_size=50${username ? `&username=${encodeURIComponent(username)}` : ""}${action ? `&action=${encodeURIComponent(action)}` : ""}`),
  departments: () => get<Department[]>("/departments"),
  department: (no: string) => get<{ dept_no: string; dept_name: string; managers: { emp_no: number; first_name: string; last_name: string }[] }>(`/departments/${no}`),
};
