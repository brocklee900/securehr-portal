import { useEffect, useState } from "react";
import { api, Department } from "../api";
import { Table } from "antd";

export default function Departments() {
  const [depts, setDepts] = useState<Department[]>([]);
  useEffect(() => { api.departments().then(setDepts).catch(() => setDepts([])); }, []);
  
  interface DataType {
    key: string;
    dept_name: string;
    dept_no: string;
  }
  
  const columns: TableProps<DataType>= [
    {
      title: "Code",
      dataIndex: "dept_no",
      key: "dept_no"
    },
    {
      title: "Department",
      dataIndex: "dept_name",
      key: "dept_name"
    },
    {
      title: "Headcount",
      dataIndex: "headcount",
      key: "headcount"
    }
  ];

  return (
    <section>
      <h2>Departments</h2>
      {/* <table width="100%">
        <thead><tr><th align="left">Code</th><th align="left">Name</th><th align="right">Headcount</th></tr></thead>
        <tbody>{depts.map((d) => (
          <tr key={d.dept_no}><td>{d.dept_no}</td><td>{d.dept_name}</td><td align="right">{d.headcount.toLocaleString()}</td></tr>
        ))}</tbody>
      </table> */}

      <Table<DataType> columns={columns} dataSource={depts} />

    </section>
  );
}
