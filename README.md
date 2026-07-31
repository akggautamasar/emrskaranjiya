# Salary Review Portal

A small web app for a monthly salary-verification workflow:

1. **Admin** logs into a password-protected panel and uploads the salary Excel sheet.
   This opens the batch for review (not yet final).
2. **Employees** go to the site, enter their Employee ID, and see their own row —
   every column from the sheet — and mark it **"Everything is OK"** or
   **"Something is wrong"** (with a comment).
3. **Admin** watches a live OK / Issue / Pending count on the batch page, and can
   read every reported issue with its comment.
4. Once everyone has confirmed, admin clicks **Publish Final** — this locks the
   batch so no more responses can be submitted, and the payslip page shows "Final".
5. Admin can **Reopen for Review** if a correction is needed, or **Export CSV**
   of everyone's status for record-keeping.

The Excel parser reads the sheet **generically from the header row** (row 1) —
it just needs an `EmpId` column and an `Employee` (name) column somewhere in the
header. Any other columns (Basic Pay, HRA, TDS, Net Payable, etc.) are picked up
automatically and shown to employees in the same order as your sheet, so this
will keep working if you add/remove allowance or deduction columns in future
months.

---

## Project structure

```
payroll-portal/
├── backend/
│   ├── main.py          FastAPI app & all routes
│   ├── models.py        SQLAlchemy models (Batch, EmployeeRecord, Review)
│   ├── database.py      DB engine/session setup
│   ├── excel_parser.py  Generic header-based Excel reader
│   └── auth.py          Simple signed-cookie admin login
├── templates/            Jinja2 HTML templates (Tailwind CDN, mobile-first)
├── static/
├── requirements.txt
├── render.yaml           Render deploy blueprint
└── .gitignore
```

---

## 1. Run it locally (optional, to try it first)

```bash
pip install -r requirements.txt --break-system-packages   # Termux/mobile
# or just: pip install -r requirements.txt                # normal machine

export ADMIN_PASSWORD=yourpassword
export SECRET_KEY=some-random-string

cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` for the employee side, and
`http://localhost:8000/admin` for the admin login.

---

## 2. Push to GitHub

```bash
cd payroll-portal
git init
git add .
git commit -m "Salary review portal"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

(Create the empty repo on GitHub first, or use `gh repo create` if you have the
GitHub CLI.)

---

## 3. Deploy on Render

**Option A — using the included `render.yaml` (Blueprint):**

1. On Render: **New → Blueprint**, pick your GitHub repo. Render reads
   `render.yaml` and sets up the web service automatically.
2. It will ask you to fill in the env vars marked `sync: false`:
   - `ADMIN_PASSWORD` — the password for `/admin`
   - `DATABASE_URL` — see the note below on persistence
   - `SECRET_KEY` is auto-generated for you.
3. Deploy. Render gives you a public URL like `https://salary-review-portal.onrender.com`.

**Option B — manual web service:**

1. **New → Web Service**, connect your GitHub repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables `ADMIN_PASSWORD` and `SECRET_KEY` under the
   service's **Environment** tab.

---

## ⚠️ Important: data persistence on Render's free tier

Render's **free** web service disk is not guaranteed to persist across
redeploys. The app defaults to a local SQLite file (`payroll.db`), which is
fine for testing, but for real monthly use you have two options:

- **Simplest (recommended):** get a free Postgres database — e.g. from
  [Neon](https://neon.tech) (free forever tier) or Render's own Postgres
  (free for 90 days, then paid) — and set the `DATABASE_URL` env var to its
  connection string. The app already supports Postgres out of the box
  (`psycopg2` is in `requirements.txt`); no code changes needed.
- Or add a **Render Persistent Disk** to the web service (small paid add-on)
  and point `DATABASE_URL` to a SQLite file on that disk.

Without one of these, redeploying the app (e.g. after a code change) could
wipe past batches and everyone's OK/Issue responses.

---

## Notes on the current design

- **Employee identification is Employee ID only** (as you asked), with no
  password — it's meant for quick self-checking, not as a secure login. If
  you want a bit more protection against someone guessing another employee's
  ID, a cheap addition is to also ask for e.g. last 4 digits of their phone
  number or date of birth and check it against a column you add to the sheet
  — happy to add this if you want it.
- Only **one admin password** is supported right now (shared by whoever
  handles this at your end). Say the word if you'd like separate named admin
  logins instead.
- The employee page shows **every column exactly as in your Excel sheet**
  (including zero values), with Total Earning / Total Deduction / Net Payable
  highlighted in bold at their natural position in the sheet.
- Uploading a new file for the same month currently creates a **new batch**
  rather than overwriting — this keeps history intact; just re-upload a
  corrected file and treat the old one as superseded (or delete it from the
  dashboard).
