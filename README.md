# ExamTrack — Examination & Student Result Management System

A complete full-stack **Examination and Student Result Management System** built for a B.Sc. IT college project and developer portfolio.

- **Frontend:** HTML, CSS, JavaScript, Bootstrap 5, Chart.js
- **Backend:** Python + Flask (blueprints, application factory)
- **Database:** **MySQL only** — Flask-SQLAlchemy + PyMySQL
- **PDF:** ReportLab digital marksheets and result reports
- **Authentication:** Flask-Login, role-based access, hashed passwords (Werkzeug PBKDF2), CSRF protection

> No MongoDB, PyMongo or any NoSQL database is used anywhere in this project.

---

## Open the website with NO server (recommended for quick use)

If you just want to open the website normally:

1. Double-click **`index.html`** in the project folder.  
   *Or double-click the **ExamTrack Offline** shortcut on your Desktop.*
2. It opens directly in your browser — **no Flask, no MySQL, no command prompt, no installation**.
3. Log in:

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `Admin@123` |
| Student | `student1` … `student8` | `Student@123` |

The offline edition includes working admin/student logins, dashboards, marks entry, results, grades/GPA/ranks, charts, notifications, audit logs and printable marksheets. All changes are saved in your browser's local storage. Use **Settings → Reset demo data** to restore the original sample data.

> A browser cannot connect to MySQL without a backend server, so the offline edition uses built-in sample data. The full MySQL/Flask version below is still available when you need the real database project.

---

## Optional full-stack version — one double-click

You do **not** need to type Flask commands.

1. Open the project folder.
2. Double-click **`START.bat`**.
3. Wait a few seconds. Your browser opens automatically at **<http://127.0.0.1:5000>**.
4. Log in with the demo accounts below.

A shortcut named **ExamTrack** is also placed on your Desktop on the first run, so you can launch the website from there.

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `Admin@123` |
| Student | `student1` … `student8` | `Student@123` |

To shut everything down, double-click **`STOP.bat`**.

`START.bat` automatically:
- creates/activates the Python environment and installs packages on first run,
- creates `.env` with safe local settings,
- initialises and starts the local MySQL 8.4 server if it is not running,
- creates the `esrms` database and user,
- creates the tables and loads demo data,
- starts the website and opens your browser.

If you want to understand the manual commands or move the project to another PC, read the full setup below.

---

## 1. Features

### Admin
- Dashboard with live summary cards, charts, recent results and audit activity.
- Full CRUD for **students, courses, semesters, subjects and examinations** (soft-safe deletes with reference checks).
- Bulk **mark entry grid** for every student/subject of an exam.
- Automatic calculation of **percentage, grade, grade points, credit-weighted GPA and pass/fail**.
- Dense **ranking** and one-click result publishing / unpublishing.
- Analytics: exam performance, course enrolment, subject averages (Chart.js).
- Notification management with audience targeting (everyone / students / admins / specific user).
- Audit trail for login, record changes, mark entry, publishing and PDF downloads.
- PDF generation: consolidated exam report and individual digital marksheet.

### Student
- Personal dashboard with academic summary, latest result and performance trend.
- View personal/academic profile.
- View published subject-wise results with grade, percentage, GPA, rank and status.
- Download **digital marksheet PDF**.
- Performance charts (marks trend, pass-mark line, subject comparison).
- Notifications with read tracking and "mark all as read".

### Security & quality
- Secure login with hashed passwords and account deactivation support.
- Role-based access enforced on every admin/student route (including JSON APIs).
- CSRF tokens on all state-changing requests.
- Safe redirect handling, input validation, parameterised ORM queries (no string-built SQL).
- Responsive Bootstrap 5 interface with a modern sidebar dashboard.
- Audit logging for important actions.

---

## 2. Windows 11 installation (beginner-friendly)

### Step 1 — Install Python

1. Download Python 3.12 (64-bit) from <https://www.python.org/downloads/windows/>.
2. Run the installer.
3. **Important:** tick **“Add python.exe to PATH”** on the first screen.
4. Click **Install Now**.
5. Verify in **PowerShell**:

```powershell
python --version
```

You should see something like `Python 3.12.x`.

> If Windows shows the Microsoft Store instead, go to **Settings → Apps → Advanced app settings → App execution aliases** and disable the `python.exe` / `python3.exe` store aliases, then open a new PowerShell window.

---

### Step 2 — Install MySQL Server

1. Download MySQL Community Server from <https://dev.mysql.com/downloads/mysql/>.
2. Choose the Windows MSI installer and use the **Full** or **Server only** setup.
3. Set a **root password** during configuration (remember it — you will need it in `.env`).
4. Keep the default port **3306** and make sure the MySQL service is running.

Verify the service:

```powershell
Get-Service -Name MySQL*
```

If it is stopped:

```powershell
Start-Service -Name MySQL80
```

(The service name may be `MySQL80`, `MySQL84` or similar.)

---

### Step 3 — Create the MySQL database

Open **MySQL Command Line Client** from the Start menu, enter your root password, then run:

```sql
CREATE DATABASE esrms
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

Optional (recommended) dedicated user:

```sql
CREATE USER 'esrms_user'@'localhost' IDENTIFIED BY 'StrongPass@123';
GRANT ALL PRIVILEGES ON esrms.* TO 'esrms_user'@'localhost';
FLUSH PRIVILEGES;
```

Type `exit;` to close MySQL.

---

### Step 4 — Copy the project and install Python packages

Open **PowerShell**, go to the project folder:

```powershell
cd "C:\Users\isakh\OneDrive\Документи\Default Project\ESRMS"
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks the activation script, run this once first:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then install dependencies:

```powershell
pip install -r requirements.txt
```

Upgrade pip first if you want:

```powershell
python -m pip install --upgrade pip
```

---

### Step 5 — Configure environment variables

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Open `.env` in Notepad or VS Code and edit:

```env
SECRET_KEY=replace-with-a-long-random-secret-key
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=esrms_user
MYSQL_PASSWORD=StrongPass@123
MYSQL_DATABASE=esrms
```

Generate a strong `SECRET_KEY`:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the generated value into `.env`.

> If your password contains special characters and you use the optional `DATABASE_URL`, URL-encode it (for example `@` becomes `%40`). Using the separate `MYSQL_*` variables avoids this problem entirely — recommended.

---

### Step 6 — Create tables and seed data

Still in the activated virtual environment:

```powershell
flask --app app init-db
```

Seed the admin account plus courses, semesters and subjects:

```powershell
flask --app app seed
```

Add optional sample students, marks and published results (useful for demonstration and screenshots):

```powershell
flask --app app seed --demo
```

The seed command is safe to run again — it skips records that already exist.

---

### Step 7 — Run the application

```powershell
flask --app app run --debug
```

Open your browser:

<http://127.0.0.1:5000>

### Default demo logins

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `Admin@123` |
| Student | `student1` … `student8` | `Student@123` |

Change the admin password immediately after login using **Settings → Change Password**.

---

## 3. Daily use

```powershell
cd "C:\Users\isakh\OneDrive\Документи\Default Project\ESRMS"
.\.venv\Scripts\Activate.ps1
flask --app app run --debug
```

Stop the server with `Ctrl + C` in PowerShell.

Alternative entry point:

```powershell
python app.py
```

---

## 4. Typical admin workflow

1. **Courses** → add a course (already seeded).
2. **Semesters** → add the academic term (already seeded).
3. **Subjects** → add subjects for that course + semester.
4. **Students** → add students (login account is created automatically).
5. **Examinations** → create an exam (Midterm / Final / Quiz / Practical) and set maximum marks.
6. **Enter Marks** → choose the exam, then fill the grid and save.
7. **Results** → review calculated grades, GPA, ranks and pass/fail.
8. **Examinations** → click the eye button to publish results for students.
9. **PDF Reports** → download the consolidated report or a student marksheet.
10. **Notifications** → announce published results.

---

## 5. Grading rules

Defined in `exatrms/utils.py` (`GRADE_SCALE`):

| Percentage | Grade | Grade point |
|---|---:|---:|
| ≥ 90 | O | 10.0 |
| ≥ 80 | A+ | 9.0 |
| ≥ 70 | A | 8.0 |
| ≥ 60 | B+ | 7.0 |
| ≥ 50 | B | 6.0 |
| ≥ 40 | C | 5.0 |
| ≥ 35 | D | 4.0 |
| < 35 | F | 0.0 |

- Pass threshold: **35%** in every subject.
- GPA = `Σ(grade point × subject credits) / Σ(credits)`.
- Result status = **Pass** only when the overall percentage ≥ 35 and no subject is failed.
- Ranks use dense ranking by percentage, then obtained marks as a tie-breaker.

---

## 6. Project structure

```text
ESRMS/
├── index.html                  # Offline website — double-click, no server needed
├── START.bat                   # Double-click to launch the full-stack version
├── STOP.bat                    # Double-click to stop everything
├── start.ps1 / stop.ps1        # Launcher / stopper logic
├── app.py                      # Entry point
├── requirements.txt
├── .env.example / .env
├── README.md
├── docs/
│   └── DATABASE_SCHEMA.md
└── exatrms/
    ├── __init__.py             # App factory, CSRF, error pages, CLI
    ├── config.py
    ├── extensions.py           # SQLAlchemy + Flask-Login
    ├── models.py               # MySQL tables and relationships
    ├── utils.py                # Grading, validation, audit, helpers
    ├── pdf.py                  # ReportLab marksheets/reports
    ├── cli.py                  # init-db and seed commands
    ├── blueprints/
    │   ├── auth.py
    │   ├── admin.py
    │   └── student.py
    ├── templates/
    │   ├── base.html
    │   ├── auth/
    │   ├── admin/
    │   ├── student/
    │   ├── errors/
    │   └── _pagination.html
    └── static/
        ├── css/style.css
        └── js/{main.js, charts.js}
```

See [`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md) for the full relational design.

---

## 7. Troubleshooting (Windows 11)

| Problem | Fix |
|---|---|
| `python` opens Microsoft Store | Disable Python app execution aliases in Windows settings, then reopen PowerShell. |
| `pip is not recognised` | Reinstall Python with **Add python.exe to PATH** ticked, or use `python -m pip`. |
| `Access denied for user 'root'@'localhost'` | Check `MYSQL_USER` / `MYSQL_PASSWORD` in `.env`, or use the dedicated `esrms_user` created in Step 3. |
| `Unknown database 'esrms'` | Run the `CREATE DATABASE esrms ...` SQL statement again. |
| `Can't connect to MySQL server` | Start the MySQL service: `Start-Service -Name MySQL80`. |
| Tables missing | Run `flask --app app init-db` again. |
| Login shows CSRF error | Refresh the page (session expired) and submit again. |
| Charts do not render | The app loads Bootstrap/Chart.js from a CDN — check your internet connection. |
| PDF download opens blank | Make sure results exist for the selected exam and student before generating. |
| Port 5000 already in use | Double-click `STOP.bat`, then `START.bat` again. |
| Website does not open at all | Double-click `START.bat` and wait until it prints “ExamTrack is open…”. Do not open `index.html` directly — this is a Flask/MySQL website. |
| MySQL error log needed | Look in `C:\Users\<your-name>\ExamTrack-MySQL\Data\*.err` or `examtrack-server-error.log`. |

---

## 8. Notes for college submission / portfolio

- All results, charts and PDFs are generated from MySQL data — no hardcoded marks.
- The `seed --demo` command is optional and only creates reproducible sample records for demonstration.
- The app uses the Flask application factory pattern and blueprint-based separation of concerns, which is easy to explain during a viva.
- For deployment, set `SESSION_COOKIE_SECURE=True`, use HTTPS, change all default passwords and set a strong `SECRET_KEY`.

---

## 9. License / authorship

Created as an academic project for B.Sc. IT. You may customise it for your institution and portfolio.
