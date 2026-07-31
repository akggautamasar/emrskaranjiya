import csv
import io
import os
from datetime import datetime

from fastapi import FastAPI, Request, Depends, UploadFile, File, Form
from fastapi.responses import RedirectResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Batch, EmployeeRecord, Review
from excel_parser import parse_payroll_excel
from auth import check_password, create_session_token, is_admin, COOKIE_NAME

Base.metadata.create_all(bind=engine)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="EMRS Karanjiya Salary Review Portal")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


def batch_stats(db: Session, batch_id: int):
    records = db.query(EmployeeRecord).filter(EmployeeRecord.batch_id == batch_id).all()
    total = len(records)
    ok = issue = pending = 0
    for r in records:
        st = r.review.status if r.review else "pending"
        if st == "ok":
            ok += 1
        elif st == "issue":
            issue += 1
        else:
            pending += 1
    return {"total": total, "ok": ok, "issue": issue, "pending": pending}


# ---------------------------------------------------------------- employee side

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("employee_home.html", {"request": request})


@app.post("/lookup", response_class=HTMLResponse)
def lookup(request: Request, emp_id: str = Form(...), db: Session = Depends(get_db)):
    emp_id = emp_id.strip()
    record = (
        db.query(EmployeeRecord)
        .join(Batch)
        .filter(EmployeeRecord.emp_id == emp_id)
        .order_by(Batch.uploaded_at.desc())
        .first()
    )
    if not record:
        return templates.TemplateResponse(
            "employee_home.html",
            {"request": request, "error": f"No salary record found for Employee ID '{emp_id}'."},
        )
    return RedirectResponse(url=f"/payslip/{record.id}", status_code=303)


@app.get("/payslip/{record_id}", response_class=HTMLResponse)
def payslip(request: Request, record_id: int, db: Session = Depends(get_db), msg: str = ""):
    record = db.query(EmployeeRecord).filter(EmployeeRecord.id == record_id).first()
    if not record:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(
        "employee_payslip.html",
        {"request": request, "record": record, "batch": record.batch, "msg": msg},
    )


@app.post("/review")
def submit_review(
    record_id: int = Form(...),
    status: str = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
):
    record = db.query(EmployeeRecord).filter(EmployeeRecord.id == record_id).first()
    if not record:
        return RedirectResponse(url="/", status_code=303)

    if record.batch.status != "review":
        # batch already finalized -- don't allow further changes
        return RedirectResponse(url=f"/payslip/{record_id}?msg=locked", status_code=303)

    if status not in ("ok", "issue"):
        return RedirectResponse(url=f"/payslip/{record_id}", status_code=303)

    review = record.review
    if not review:
        review = Review(record_id=record.id)
        db.add(review)
    review.status = status
    review.comment = comment.strip()
    review.updated_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/payslip/{record_id}?msg=saved", status_code=303)


# ---------------------------------------------------------------- admin side

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_form(request: Request):
    if is_admin(request):
        return RedirectResponse(url="/admin")
    return templates.TemplateResponse("admin_login.html", {"request": request})


@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    if not check_password(password):
        return templates.TemplateResponse(
            "admin_login.html", {"request": request, "error": "Incorrect password."}
        )
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.set_cookie(COOKIE_NAME, create_session_token(), httponly=True, samesite="lax")
    return resp


@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse(url="/admin/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login")
    batches = db.query(Batch).order_by(Batch.uploaded_at.desc()).all()
    batch_rows = [(b, batch_stats(db, b.id)) for b in batches]
    return templates.TemplateResponse(
        "admin_dashboard.html", {"request": request, "batch_rows": batch_rows}
    )


@app.post("/admin/upload")
async def admin_upload(
    request: Request,
    label: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login")

    content = await file.read()
    try:
        headers, records = parse_payroll_excel(io.BytesIO(content))
    except ValueError as e:
        batches = db.query(Batch).order_by(Batch.uploaded_at.desc()).all()
        batch_rows = [(b, batch_stats(db, b.id)) for b in batches]
        return templates.TemplateResponse(
            "admin_dashboard.html",
            {"request": request, "batch_rows": batch_rows, "error": str(e)},
        )

    batch = Batch(
        label=label.strip(),
        filename=file.filename,
        status="review",
        columns=headers,
    )
    db.add(batch)
    db.flush()

    for rec in records:
        db.add(
            EmployeeRecord(
                batch_id=batch.id,
                emp_id=rec["emp_id"],
                name=rec["name"],
                department=rec["department"],
                designation=rec["designation"],
                net_payable=rec["net_payable"],
                data=rec["data"],
            )
        )
    db.commit()

    return RedirectResponse(url=f"/admin/batch/{batch.id}", status_code=303)


@app.get("/admin/batch/{batch_id}", response_class=HTMLResponse)
def admin_batch_detail(request: Request, batch_id: int, db: Session = Depends(get_db), msg: str = ""):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login")
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        return RedirectResponse(url="/admin")
    records = (
        db.query(EmployeeRecord)
        .filter(EmployeeRecord.batch_id == batch_id)
        .order_by(EmployeeRecord.name)
        .all()
    )
    stats = batch_stats(db, batch_id)
    return templates.TemplateResponse(
        "admin_batch.html",
        {"request": request, "batch": batch, "records": records, "stats": stats, "msg": msg},
    )


@app.post("/admin/batch/{batch_id}/publish")
def admin_publish(request: Request, batch_id: int, db: Session = Depends(get_db)):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login")
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if batch:
        batch.status = "published"
        batch.published_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(url=f"/admin/batch/{batch_id}", status_code=303)


@app.post("/admin/batch/{batch_id}/reopen")
def admin_reopen(request: Request, batch_id: int, db: Session = Depends(get_db)):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login")
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if batch:
        batch.status = "review"
        batch.published_at = None
        db.commit()
    return RedirectResponse(url=f"/admin/batch/{batch_id}", status_code=303)


@app.post("/admin/batch/{batch_id}/delete")
def admin_delete(request: Request, batch_id: int, db: Session = Depends(get_db)):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login")
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if batch:
        db.delete(batch)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/record/{record_id}/remark")
def admin_set_remark(request: Request, record_id: int, remark: str = Form(""), db: Session = Depends(get_db)):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login")
    record = db.query(EmployeeRecord).filter(EmployeeRecord.id == record_id).first()
    if not record:
        return RedirectResponse(url="/admin", status_code=303)
    record.admin_remark = remark.strip()
    db.commit()
    return RedirectResponse(url=f"/admin/batch/{record.batch_id}?msg=remark_saved", status_code=303)


@app.post("/admin/batch/{batch_id}/bulk_remark")
def admin_bulk_remark(
    request: Request,
    batch_id: int,
    remark: str = Form(""),
    overwrite: str = Form(""),
    db: Session = Depends(get_db),
):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login")
    remark = remark.strip()
    records = db.query(EmployeeRecord).filter(EmployeeRecord.batch_id == batch_id).all()
    for r in records:
        if overwrite == "yes" or not (r.admin_remark or "").strip():
            r.admin_remark = remark
    db.commit()
    return RedirectResponse(url=f"/admin/batch/{batch_id}?msg=remark_saved", status_code=303)


@app.get("/admin/batch/{batch_id}/export")
def admin_export(request: Request, batch_id: int, db: Session = Depends(get_db)):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login")
    records = (
        db.query(EmployeeRecord)
        .filter(EmployeeRecord.batch_id == batch_id)
        .order_by(EmployeeRecord.name)
        .all()
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["EmpId", "Name", "Department", "Designation", "Net Payable", "Status", "Employee Comment", "Admin Remark"])
    for r in records:
        writer.writerow(
            [
                r.emp_id,
                r.name,
                r.department,
                r.designation,
                r.net_payable,
                r.review.status if r.review else "pending",
                r.review.comment if r.review else "",
                r.admin_remark or "",
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=batch_{batch_id}_review_status.csv"},
    )
