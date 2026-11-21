import { FormEvent, ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, CreatedEmployee, Department } from "../api";

// Same limits as the API (backend/app/routers/hr_admin.py). They are repeated here only to give instant feedback;
// the API checks everything again and is the one that decides.
const MAX_FIRST = 14;
const MAX_LAST = 16;
const MIN_AGE = 16;
const MAX_SALARY = 1_000_000;
const EARLIEST_BIRTH = "1900-01-01";

interface Form {
  first_name: string; last_name: string; gender: string; birth_date: string;
  hire_date: string; dept_no: string; title: string; salary: string;
}
type Errors = Partial<Record<keyof Form, string>>;
const FIELDS: (keyof Form)[] = ["first_name", "last_name", "gender", "birth_date", "hire_date", "dept_no", "title", "salary"];

/** YYYY-MM-DD in the browser's local time (toISOString would use UTC and can be a day off). */
function isoDate(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const emptyForm = (): Form => ({
  first_name: "", last_name: "", gender: "", birth_date: "", hire_date: isoDate(), dept_no: "", title: "", salary: "",
});

function ageOn(day: string, born: string): number {
  const [y, m, d] = day.split("-").map(Number);
  const [by, bm, bd] = born.split("-").map(Number);
  return y - by - (m < bm || (m === bm && d < bd) ? 1 : 0);
}

function validate(f: Form): Errors {
  const e: Errors = {};
  if (!f.first_name.trim()) e.first_name = "Required";
  if (!f.last_name.trim()) e.last_name = "Required";
  if (!f.gender) e.gender = "Required";
  if (!f.birth_date) e.birth_date = "Required";
  else if (f.birth_date < EARLIEST_BIRTH || f.birth_date > isoDate()) e.birth_date = `Must be between ${EARLIEST_BIRTH} and today`;
  if (!f.hire_date) e.hire_date = "Required";
  else if (f.hire_date > isoDate(366)) e.hire_date = "Cannot be more than a year in the future";
  else if (f.birth_date && !e.birth_date && ageOn(f.hire_date, f.birth_date) < MIN_AGE) e.hire_date = `Employee must be at least ${MIN_AGE} on the hire date`;
  if (!f.dept_no) e.dept_no = "Required";
  if (!f.title) e.title = "Required";
  const salary = Number(f.salary);
  if (!f.salary.trim()) e.salary = "Required";
  else if (!Number.isInteger(salary) || salary < 1 || salary > MAX_SALARY) e.salary = `Whole dollars, 1 to ${MAX_SALARY.toLocaleString()}`;
  return e;
}

const inputStyle = { padding: 6, font: "inherit", width: "100%", boxSizing: "border-box" } as const;

function Field({ id, label, error, hint, children }: { id: string; label: string; error?: string; hint?: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label htmlFor={id} style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>{label}</label>
      {children}
      {hint && !error && <small style={{ color: "#555" }}>{hint}</small>}
      {error && <small id={`${id}-error`} role="alert" style={{ color: "crimson" }}>{error}</small>}
    </div>
  );
}

export default function NewEmployee() {
  const [form, setForm] = useState<Form>(emptyForm);
  const [errors, setErrors] = useState<Errors>({});
  const [banner, setBanner] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState<CreatedEmployee | null>(null);
  const [depts, setDepts] = useState<Department[]>([]);
  const [titles, setTitles] = useState<string[]>([]);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    Promise.all([api.departments(), api.hireTitles()])
      .then(([d, t]) => { setDepts(d); setTitles(t); })
      .catch((e) => setLoadError(`Could not load the department and title lists: ${String(e)}`));
  }, []);

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((previous) => ({ ...previous, [key]: value }));
    setErrors((previous) => ({ ...previous, [key]: undefined }));   // clear a field's error as soon as it is edited
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    const problems = validate(form);
    setErrors(problems);
    setBanner("");
    if (Object.keys(problems).length) { setBanner("Please correct the highlighted fields."); return; }
    setSubmitting(true);
    try {
      setCreated(await api.createEmployee({
        first_name: form.first_name.trim(), last_name: form.last_name.trim(), gender: form.gender as "M" | "F",
        birth_date: form.birth_date, hire_date: form.hire_date, dept_no: form.dept_no, title: form.title,
        salary: Number(form.salary),
      }));
    } catch (e) {
      if (e instanceof ApiError) {
        const known: Errors = {};
        const other: string[] = [];
        for (const [field, message] of Object.entries(e.fieldErrors)) {
          if ((FIELDS as string[]).includes(field)) known[field as keyof Form] = message;
          else other.push(`${field}: ${message}`);
        }
        setErrors(known);
        setBanner(e.status === 403 ? "You do not have permission to create employees."
          : [Object.keys(known).length ? "Please correct the highlighted fields." : e.message, ...other].join(" "));
      } else {
        setBanner(`Could not reach the server: ${String(e)}`);
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (created) {
    return (
      <section>
        <h2>Employee created</h2>
        <p role="status">
          <strong>{created.first_name} {created.last_name}</strong> is employee <strong>#{created.emp_no}</strong>,{" "}
          {created.title} in {created.dept_name}, starting {created.hire_date}.
        </p>
        <p>
          <Link to={`/employees/${created.emp_no}`}>View employee</Link>{" · "}
          <button type="button" onClick={() => { setCreated(null); setForm(emptyForm()); setErrors({}); setBanner(""); }}>
            Add another
          </button>
        </p>
      </section>
    );
  }

  const bind = (key: keyof Form) => ({
    id: key, value: form[key], disabled: submitting, style: inputStyle,
    "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${key}-error` : undefined,
    onChange: (e: { target: { value: string } }) => set(key, e.target.value),
  });

  return (
    <section style={{ maxWidth: 520 }}>
      <h2>New employee</h2>
      {loadError && <p role="alert" style={{ color: "crimson" }}>{loadError}</p>}
      {banner && <p role="alert" style={{ color: "crimson" }}>{banner}</p>}
      <form onSubmit={submit} noValidate>
        <fieldset style={{ marginBottom: 16 }}>
          <legend>Personal details</legend>
          <Field id="first_name" label="First name" error={errors.first_name} hint={`Up to ${MAX_FIRST} characters`}>
            <input {...bind("first_name")} maxLength={MAX_FIRST} autoComplete="off" />
          </Field>
          <Field id="last_name" label="Last name" error={errors.last_name} hint={`Up to ${MAX_LAST} characters`}>
            <input {...bind("last_name")} maxLength={MAX_LAST} autoComplete="off" />
          </Field>
          <Field id="gender" label="Gender" error={errors.gender}>
            <select {...bind("gender")}>
              <option value="">Select…</option>
              <option value="F">Female</option>
              <option value="M">Male</option>
            </select>
          </Field>
          <Field id="birth_date" label="Date of birth" error={errors.birth_date}>
            <input {...bind("birth_date")} type="date" min={EARLIEST_BIRTH} max={isoDate()} />
          </Field>
        </fieldset>
        <fieldset style={{ marginBottom: 16 }}>
          <legend>Job details</legend>
          <Field id="hire_date" label="Hire date" error={errors.hire_date} hint="Also the start date of the department, title and salary">
            <input {...bind("hire_date")} type="date" max={isoDate(366)} />
          </Field>
          <Field id="dept_no" label="Department" error={errors.dept_no}>
            <select {...bind("dept_no")}>
              <option value="">Select…</option>
              {depts.map((d) => <option key={d.dept_no} value={d.dept_no}>{d.dept_name}</option>)}
            </select>
          </Field>
          <Field id="title" label="Job title" error={errors.title}>
            <select {...bind("title")}>
              <option value="">Select…</option>
              {titles.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field id="salary" label="Starting salary (USD per year)" error={errors.salary}>
            <input {...bind("salary")} type="number" inputMode="numeric" min={1} max={MAX_SALARY} step={1} />
          </Field>
        </fieldset>
        <button type="submit" disabled={submitting || !!loadError}>{submitting ? "Creating…" : "Create employee"}</button>{" "}
        <Link to="/">Cancel</Link>
      </form>
    </section>
  );
}
