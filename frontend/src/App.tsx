import { Link, Route, Routes } from "react-router-dom";
import { currentRole, keycloak } from "./auth";
import Audit from "./pages/Audit";
import Departments from "./pages/Departments";
import EmployeeDetail from "./pages/EmployeeDetail";
import EmployeeSearch from "./pages/EmployeeSearch";

export default function App() {
  const role = currentRole();
  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <header style={{ display: "flex", gap: 16, alignItems: "center", borderBottom: "1px solid #ccc", paddingBottom: 8 }}>
        <strong>SecureHR</strong>
        <Link to="/">Employees</Link>
        <Link to="/departments">Departments</Link>
        {role === "hr_admin" && <Link to="/audit">Audit log</Link>}
        <span style={{ marginLeft: "auto" }}>
          {keycloak.tokenParsed?.preferred_username} ({role}){" "}
          <button onClick={() => keycloak.logout({ redirectUri: window.location.origin })}>Sign out</button>
        </span>
      </header>
      <Routes>
        <Route path="/" element={<EmployeeSearch />} />
        <Route path="/employees/:id" element={<EmployeeDetail role={role} />} />
        <Route path="/departments" element={<Departments />} />
        <Route path="/audit" element={role === "hr_admin" ? <Audit /> : <p>Not authorized.</p>} />
      </Routes>
    </div>
  );
}
