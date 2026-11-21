import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, ApiError, SalaryChangeStatus } from "../api";

// Same limit as the API (backend/app/routers/hr_admin.py), repeated only for instant feedback; the API decides.
const MAX_SALARY = 1_000_000;

const money = (n: number) => `$${n.toLocaleString()}`;

/** YYYY-MM-DD in the browser's local time (toISOString would use UTC and can be a day off). */
function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

interface Errors { salary?: string; effective_date?: string }

/** HR admins only: change an employee's salary. Shown on the employee page under the salary history.
 *  `onChanged` lets the page reload the history after a change. */
export default function SalaryChange({ empNo, onChanged }: { empNo: string; onChanged: () => void }) {
  const [status, setStatus] = useState<SalaryChangeStatus | null>(null);
  const [loadError, setLoadError] = useState("");
  const [salary, setSalary] = useState("");
  const [effective, setEffective] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [banner, setBanner] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState("");

  const load = useCallback(() => {
    setLoadError("");
    api.salaryChangeStatus(empNo)
      .then((s) => { setStatus(s); setEffective(s.earliest_date); })
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : `Could not reach the server: ${String(e)}`));
  }, [empNo]);

  useEffect(load, [load]);

  if (loadError) return <p role="alert" style={{ color: "crimson" }}>Salary changes unavailable: {loadError}</p>;
  if (!status) return <p>Loading salary change options…</p>;

  const current = status.current?.salary;

  function validate(): Errors {
    const e: Errors = {};
    const n = Number(salary);
    if (!salary.trim()) e.salary = "Required";
    else if (!Number.isInteger(n) || n < 1 || n > MAX_SALARY) e.salary = `Whole dollars, 1 to ${MAX_SALARY.toLocaleString()}`;
    else if (n === current) e.salary = "Same as the current salary";
    if (!effective) e.effective_date = "Required";
    else if (status && (effective < status.earliest_date || effective > status.latest_date)) {
      e.effective_date = `Between ${status.earliest_date} and ${status.latest_date}`;
    }
    return e;
  }

  function review(event: FormEvent) {
    event.preventDefault();
    const problems = validate();
    setErrors(problems);
    setBanner(Object.keys(problems).length ? "Please correct the highlighted fields." : "");
    setConfirming(!Object.keys(problems).length);
  }

  async function confirm() {
    if (submitting) return;
    setSubmitting(true);
    setBanner("");
    try {
      const result = await api.changeSalary(empNo, Number(salary), effective);
      const when = result.from_date === localToday() ? "effective today" : `taking effect ${result.from_date} (pending)`;
      setDone(`Salary changed from ${money(result.previous.salary)} to ${money(result.salary)}, ${when}.`);
      setSalary(""); setConfirming(false); setErrors({});
      onChanged();
      load();
    } catch (e) {
      setConfirming(false);
      if (e instanceof ApiError) {
        const { salary: s, effective_date: d, ...other } = e.fieldErrors;
        setErrors({ salary: s, effective_date: d });
        setBanner(s || d ? "Please correct the highlighted fields." : Object.values(other)[0] ?? e.message);
        if (e.status === 409) load();   // the salary changed meanwhile (e.g. now pending): refresh the status
      } else {
        setBanner(`Could not reach the server: ${String(e)}`);
      }
    } finally {
      setSubmitting(false);
    }
  }

  const box = { border: "1px solid #ccc", borderRadius: 6, padding: 12, marginTop: 12, maxWidth: 520 } as const;
  const input = { padding: 6, font: "inherit", width: "100%", boxSizing: "border-box" } as const;

  return (
    <div style={box}>
      <h4 style={{ marginTop: 0 }}>Change salary</h4>
      {done && <p role="status" style={{ color: "green" }}>{done}</p>}
      {status.pending && (
        <p>Pending: <strong>{money(status.pending.salary)}</strong> from {status.pending.from_date}.</p>
      )}
      {!status.can_change ? (
        <p role="note" style={{ color: "#555" }}>{status.reason}</p>
      ) : (
        <form onSubmit={review} noValidate>
          {banner && <p role="alert" style={{ color: "crimson" }}>{banner}</p>}
          <p>Current salary: <strong>{current !== undefined ? money(current) : "none"}</strong>
            {status.current && <> (since {status.current.from_date})</>}</p>
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="new_salary" style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>New salary (USD per year)</label>
            <input id="new_salary" type="number" inputMode="numeric" min={1} max={MAX_SALARY} step={1} style={input}
              value={salary} disabled={submitting || confirming}
              aria-invalid={errors.salary ? true : undefined} aria-describedby={errors.salary ? "new_salary-error" : undefined}
              onChange={(e) => { setSalary(e.target.value); setErrors((p) => ({ ...p, salary: undefined })); setDone(""); }} />
            {errors.salary && <small id="new_salary-error" role="alert" style={{ color: "crimson" }}>{errors.salary}</small>}
          </div>
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="effective_date" style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>Takes effect on</label>
            <input id="effective_date" type="date" min={status.earliest_date} max={status.latest_date} style={input}
              value={effective} disabled={submitting || confirming}
              aria-invalid={errors.effective_date ? true : undefined}
              aria-describedby={errors.effective_date ? "effective_date-error" : "effective_date-hint"}
              onChange={(e) => { setEffective(e.target.value); setErrors((p) => ({ ...p, effective_date: undefined })); setDone(""); }} />
            {errors.effective_date
              ? <small id="effective_date-error" role="alert" style={{ color: "crimson" }}>{errors.effective_date}</small>
              : <small id="effective_date-hint" style={{ color: "#555" }}>Today or later, up to a year ahead. A later date is a pending change; only one can be pending.</small>}
          </div>
          {!confirming ? (
            <button type="submit">Review change</button>
          ) : (
            <div role="group" aria-label="Confirm salary change">
              <p>
                Change salary from <strong>{current !== undefined ? money(current) : "none"}</strong> to{" "}
                <strong>{money(Number(salary))}</strong>
                {current ? <> ({Number(salary) >= current ? "+" : ""}{(((Number(salary) - current) / current) * 100).toFixed(1)}%)</> : null},
                taking effect {effective}?
              </p>
              <button type="button" onClick={confirm} disabled={submitting}>{submitting ? "Saving…" : "Confirm change"}</button>{" "}
              <button type="button" onClick={() => setConfirming(false)} disabled={submitting}>Back</button>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
