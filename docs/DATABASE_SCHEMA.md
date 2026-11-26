# ExamTrack — MySQL Database Schema

The schema is created automatically by Flask-SQLAlchemy with:

```powershell
flask --app app init-db
```

All tables use `utf8mb4`. Primary keys are auto-increment integers. Foreign keys use `RESTRICT` where deleting a parent would destroy academic history, and `CASCADE` for owned child records such as marks and results.

---

## Entity relationship overview

```text
users 1 ──── 0..1 students ──── * marks ──── * subjects
  │                │               │
  │                │               └── * examinations
  │                └── * results ─────── * examinations
  ├── * audit_logs
  ├── * notifications (specific recipient)
  └── * notification_reads ──── * notifications
```

```text
courses 1 ──── * students
        1 ──── * subjects
        1 ──── * examinations

semesters 1 ──── * students
          1 ──── * subjects
          1 ──── * examinations
```

---

## Tables

### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | INT | Primary key |
| `username` | VARCHAR(50) | UNIQUE, indexed |
| `email` | VARCHAR(120) | UNIQUE, indexed |
| `password_hash` | VARCHAR(255) | Werkzeug PBKDF2 hash (never plain text) |
| `role` | ENUM('admin','student') | Drives role-based access |
| `is_active` | BOOLEAN | Deactivation without deleting history |
| `created_at`, `last_login_at` | DATETIME | Audit timestamps |

### `courses`
`id` (PK), `code` (UNIQUE), `name`, `duration_years`, `description`, `is_active`, `created_at`.

### `semesters`
`id` (PK), `number`, `academic_year`, `is_active`, `created_at`.
UNIQUE (`number`, `academic_year`).

### `students`
| Column | Notes |
|---|---|
| `id` | Primary key |
| `user_id` | FK → `users.id`, UNIQUE, ON DELETE CASCADE |
| `student_code` | UNIQUE, indexed |
| `first_name`, `last_name`, `email`, `phone`, `gender`, `date_of_birth`, `address` | Profile data |
| `admission_date` | Date of admission |
| `course_id` | FK → `courses.id`, ON DELETE RESTRICT |
| `semester_id` | FK → `semesters.id`, ON DELETE RESTRICT |
| `is_active`, `created_at`, `updated_at` | Status/timestamps |

### `subjects`
`id` (PK), `code` (UNIQUE), `name`, `course_id` FK, `semester_id` FK, `credits`, `description`, `is_active`, `created_at`.
Index on (`course_id`, `semester_id`).

### `examinations`
`id` (PK), `name`, `exam_type` ENUM('Quiz','Midterm','Final','Practical'), `course_id` FK, `semester_id` FK, `academic_year`, `max_marks`, `start_date`, `end_date`, `is_published`, `is_active`, `created_at`, `published_at`.

### `marks`
| Column | Notes |
|---|---|
| `id` | Primary key |
| `student_id` | FK → `students.id`, ON DELETE CASCADE |
| `subject_id` | FK → `subjects.id`, ON DELETE RESTRICT |
| `examination_id` | FK → `examinations.id`, ON DELETE CASCADE |
| `marks_obtained`, `max_marks`, `percentage` | DECIMAL values |
| `grade`, `grade_points`, `status` | Calculated automatically |
| `remarks` | Optional |
| `entered_by` | FK → `users.id`, ON DELETE SET NULL |
| `created_at`, `updated_at` | Timestamps |

UNIQUE (`student_id`, `subject_id`, `examination_id`).
Index on (`examination_id`, `student_id`).

### `results`
`id` (PK), `student_id` FK, `examination_id` FK, `obtained_marks`, `total_marks`, `percentage`, `grade`, `gpa`, `status` ENUM('pass','fail'), `rank`, `calculated_at`, `published_at`, `published_by` FK → `users.id`.
UNIQUE (`student_id`, `examination_id`). Index on (`examination_id`, `status`).

### `notifications`
`id` (PK), `title`, `message`, `audience` ENUM('all','students','admins','specific'), `user_id` FK (specific recipient), `created_by` FK, `created_at`, `is_active`.

### `notification_reads`
Composite primary key (`user_id`, `notification_id`) with FKs to `users` and `notifications`, plus `read_at`.

### `audit_logs`
`id` (PK), `user_id` FK → `users.id` ON DELETE SET NULL, `action`, `entity_type`, `entity_id`, `details`, `ip_address`, `user_agent`, `created_at`. Indexed on `action` and `created_at`.

---

## Calculation flow

1. Admin saves a mark in `marks`.
2. `recalculate_result()` sums marks for that student/exam and computes percentage, grade points, GPA and pass/fail.
3. `update_ranks()` assigns dense ranks across the exam.
4. Publishing an exam sets `examinations.is_published`, `examinations.published_at` and each `results.published_at`.
5. Student queries only published exams, so unpublished results are never exposed.
