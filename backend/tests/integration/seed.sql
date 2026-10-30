-- Small, fixed dataset for integration tests (schema mirrors what pgloader creates; gender simplified to varchar).
--   d001 Marketing: 10001, 10002, 110022 (former manager), 110039 (current manager)   -> 4 people, 8 salary rows
--   d002 Finance:   10003, 10004, 10005 (moved from d001 in 1990), 110114 (manager)    -> 4 people, 8 salary rows
--   d003 Research:  nobody
CREATE SCHEMA hr;
CREATE TABLE hr.employees (emp_no int PRIMARY KEY, birth_date date NOT NULL, first_name varchar(14) NOT NULL,
  last_name varchar(16) NOT NULL, gender varchar(1) NOT NULL, hire_date date NOT NULL);
CREATE TABLE hr.departments (dept_no char(4) PRIMARY KEY, dept_name varchar(40) UNIQUE NOT NULL);
CREATE TABLE hr.dept_emp (emp_no int REFERENCES hr.employees, dept_no char(4) REFERENCES hr.departments,
  from_date date NOT NULL, to_date date NOT NULL, PRIMARY KEY (emp_no, dept_no));
CREATE TABLE hr.dept_manager (emp_no int REFERENCES hr.employees, dept_no char(4) REFERENCES hr.departments,
  from_date date NOT NULL, to_date date NOT NULL, PRIMARY KEY (emp_no, dept_no));
CREATE TABLE hr.titles (emp_no int REFERENCES hr.employees, title varchar(50) NOT NULL,
  from_date date NOT NULL, to_date date, PRIMARY KEY (emp_no, title, from_date));
CREATE TABLE hr.salaries (emp_no int REFERENCES hr.employees, salary int NOT NULL,
  from_date date NOT NULL, to_date date NOT NULL, PRIMARY KEY (emp_no, from_date));

INSERT INTO hr.departments VALUES ('d001','Marketing'), ('d002','Finance'), ('d003','Research');

INSERT INTO hr.employees VALUES
 (10001,  '1953-09-02','Georgi',   'Facello',    'M','1986-06-26'),
 (10002,  '1964-06-02','Bezalel',  'Simmel',     'F','1985-11-21'),
 (10003,  '1959-12-03','Parto',    'Bamford',    'M','1986-08-28'),
 (10004,  '1954-05-01','Chirstian','Koblick',    'M','1986-12-01'),
 (10005,  '1955-01-21','Kyoichi',  'Maliniak',   'M','1989-09-12'),
 (110022, '1956-09-12','Margareta','Markovitch', 'F','1985-01-01'),
 (110039, '1963-06-21','Vishwani', 'Minakawa',   'M','1986-04-12'),
 (110114, '1957-03-28','Isamu',    'Legleitner', 'F','1985-01-14');

INSERT INTO hr.dept_emp VALUES
 (10001,'d001','1986-06-26','9999-01-01'),
 (10002,'d001','1996-08-03','9999-01-01'),
 (110022,'d001','1985-01-01','9999-01-01'),
 (110039,'d001','1991-10-01','9999-01-01'),
 (10003,'d002','1995-12-03','9999-01-01'),
 (10004,'d002','1986-12-01','9999-01-01'),
 (10005,'d001','1989-09-12','1990-01-01'),   -- left Marketing...
 (10005,'d002','1990-01-01','9999-01-01'),   -- ...now in Finance
 (110114,'d002','1989-12-17','9999-01-01');

INSERT INTO hr.dept_manager VALUES
 (110022,'d001','1985-01-01','1991-10-01'),  -- FORMER manager of Marketing
 (110039,'d001','1991-10-01','9999-01-01'),  -- current manager of Marketing
 (110114,'d002','1989-12-17','9999-01-01');  -- current manager of Finance

INSERT INTO hr.titles VALUES
 (10001,'Senior Engineer','1986-06-26','1995-12-01'),
 (10001,'Staff','1995-12-01','9999-01-01'),
 (10002,'Staff','1996-08-03','9999-01-01'),
 (10003,'Senior Engineer','1995-12-03','9999-01-01'),
 (10004,'Engineer','1986-12-01','9999-01-01'),
 (10005,'Engineer','1989-09-12','1995-01-01'),
 (10005,'Senior Engineer','1995-01-01','9999-01-01'),
 (110022,'Manager','1985-01-01','9999-01-01'),
 (110039,'Manager','1991-10-01','9999-01-01'),
 (110114,'Manager','1989-12-17','9999-01-01');

INSERT INTO hr.salaries VALUES
 (10001,60117,'1986-06-26','1987-06-26'),(10001,62102,'1987-06-26','1988-06-25'),(10001,88958,'2001-06-22','9999-01-01'),
 (10002,65828,'1996-08-03','1997-08-03'),(10002,72527,'2001-08-02','9999-01-01'),
 (10003,40006,'1995-12-03','1996-12-02'),(10003,43616,'1996-12-02','9999-01-01'),
 (10004,40054,'1986-12-01','1987-12-01'),(10004,42283,'1987-12-01','9999-01-01'),
 (10005,78228,'1989-09-12','1990-09-12'),(10005,94692,'2001-09-09','9999-01-01'),
 (110022,84000,'1985-01-01','9999-01-01'),
 (110039,70000,'1991-10-01','1992-10-01'),(110039,75000,'1992-10-01','9999-01-01'),
 (110114,71000,'1989-12-17','1990-12-17'),(110114,76000,'1990-12-17','9999-01-01');
