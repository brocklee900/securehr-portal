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
export interface NewEmployee {
  first_name: string; last_name: string; gender: "M" | "F"; birth_date: string; hire_date: string;
  dept_no: string; title: string; salary: number;
}
export interface CreatedEmployee extends NewEmployee { emp_no: number; dept_name: string }
/** GET /hr/employees/{n}/salary-change: everything the salary-change form needs. */
export interface SalaryChangeStatus {
  can_change: boolean; reason: string | null;
  current: Salary | null;   // the salary in effect today
  pending: Salary | null;   // a change that starts later (at most one)
  earliest_date: string; latest_date: string;
}
export interface SalaryChanged extends Salary { emp_no: number; previous: Salary }

/** A failed request. `fieldErrors` maps a form field to the API's message when the API says which field was wrong. */
export class ApiError extends Error {
  constructor(public status: number, message: string, public fieldErrors: Record<string, string> = {}) {
    super(message);
  }
}

async function get<T>(path: string): Promise<T> {
  await keycloak.updateToken(30);
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${keycloak.token}` } });
  if (!res.ok) throw await apiError(res);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  await keycloak.updateToken(30);
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${keycloak.token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) return res.json() as Promise<T>;
  throw await apiError(res);
}

/** Turns a failed response into an ApiError, using the API's own message when it sent one. */
async function apiError(res: Response): Promise<ApiError> {
  let detail: unknown;
  try { detail = (await res.json()).detail; } catch { /* the error body was not JSON */ }
  const fieldErrors: Record<string, string> = {};
  let message = `${res.status} ${res.statusText}`;
  if (typeof detail === "string") {
    message = detail;
  } else if (Array.isArray(detail)) {   // FastAPI validation errors: [{ loc: ["body", "salary"], msg: "..." }]
    for (const item of detail as { loc?: unknown[]; msg?: unknown }[]) {
      const field = item.loc?.[item.loc.length - 1];
      if (typeof field === "string" && typeof item.msg === "string" && !(field in fieldErrors)) {
        fieldErrors[field] = item.msg.replace(/^Value error, /, "");
      }
    }
  }
  return new ApiError(res.status, message, fieldErrors);
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
  hireTitles: () => get<string[]>("/hr/titles"),
  createEmployee: (employee: NewEmployee) => post<CreatedEmployee>("/hr/employees", employee),
  salaryChangeStatus: (id: string) => get<SalaryChangeStatus>(`/hr/employees/${id}/salary-change`),
  changeSalary: (id: string, salary: number, effective_date: string) =>
    post<SalaryChanged>(`/hr/employees/${id}/salaries`, { salary, effective_date }),
  department: (no: string) => get<{ dept_no: string; dept_name: string; managers: { emp_no: number; first_name: string; last_name: string }[] }>(`/departments/${no}`),
};
