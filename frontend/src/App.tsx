import { Link, Route, Routes } from "react-router-dom";
import { currentRole, keycloak } from "./auth";
import Audit from "./pages/Audit";
import Departments from "./pages/Departments";
import EmployeeDetail from "./pages/EmployeeDetail";
import EmployeeSearch from "./pages/EmployeeSearch";
import NewEmployee from "./pages/NewEmployee";
import { BreadcrumbProps, Breadcrumb } from 'antd';
import { createStaticStyles } from 'antd-style';

export default function App() {
  const role = currentRole();
  const classNames = createStaticStyles(({ css }) => ({
        root: css`
          padding: 8px;
          border-radius: 4px;
        `,
        item: css`
          color: #1890ff;
        `,
        separator: css`
          color: rgba(0, 0, 0, 0.45);
        `,
      }));
  
  const breadItems = [
    {title: "Employees", href:"/"},
    {title: "Departments", href: "/departments"},
    {title: "New employee", href:"/employees/new"},
    {title: "Audit log", href:"/audit"},
  ];

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <header style={{ display: "flex", gap: 16, alignItems: "center", borderBottom: "1px solid #010101", paddingBottom: 8 }}>
        
        <strong><span style={{fontSize: "36px", color: "#000"}}>SecureHR</span></strong>
          <Breadcrumb 
            items={breadItems}
          />
          <span style={{ marginLeft: "auto", width: 'auto' }}>
            {keycloak.tokenParsed?.preferred_username} ({role}){" "}
            <button onClick={() => keycloak.logout({ redirectUri: window.location.origin })}>Sign out</button>
          </span>
        <hr />   
        
      </header>
      <Routes>
        <Route path="/" element={<EmployeeSearch />} />
        <Route path="/employees/new" element={role === "hr_admin" ? <NewEmployee /> : <p>Not authorized.</p>} />
        <Route path="/employees/:id" element={<EmployeeDetail role={role} />} />
        <Route path="/departments" element={<Departments />} />
        <Route path="/audit" element={role === "hr_admin" ? <Audit /> : <p>Not authorized.</p>} />
      </Routes>
    </div>
  );
}
