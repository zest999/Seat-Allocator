from fastapi import FastAPI, Depends, Body, HTTPException, Query
from sqlalchemy.orm import Session
from database import Base, engine, SessionLocal
from db_models import StudentDB, ClassroomDB, BenchDB, AllocationDB, ExamDB, ExamRegistrationDB
import pandas as pd
import json
from math import ceil
import heapq
import random
from collections import defaultdict, deque
from layouts import generate_layout
from pydantic import BaseModel
from fastapi.responses import FileResponse
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from fastapi.middleware.cors import CORSMiddleware



app = FastAPI(title = "Seat Allocator API")

Base.metadata.create_all(bind = engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
    

@app.get("/")
def root():
    return {"message": "Seat Allocator API is running !"}


@app.get("/students")
def get_students(db: Session = Depends(get_db)):
    students = db.query(StudentDB).order_by(StudentDB.stu_id).all()

    return [
        {
            "stu_id": s.stu_id,
            "stu_name": s.stu_name,
            "year": s.year,
            "dept": s.dept,
            "section": s.section,
            "phone": s.phone
        }
        for s in students
    ]


@app.post("/students/import")
def import_students(db: Session = Depends(get_db)):
    file_path = Path(__file__).resolve().parent.parent / "students.xlsx"

    if not file_path.exists():
        return {"error": f"students.xlsx not found at {file_path}"}

    df = pd.read_excel(file_path)

    required_cols = ["stu_id", "stu_name", "year", "dept", "section"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        return {"error": f"Missing columns in Excel: {missing}"}

    inserted = 0
    updated = 0

    for _, row in df.iterrows():
        stu_id = int(row["stu_id"])
        stu_name = str(row["stu_name"]).strip()
        year = int(row["year"])
        dept = str(row["dept"]).strip().upper()
        section = str(row["section"]).strip().upper()

        phone = None
        if "phone" in df.columns and not pd.isna(row["phone"]):
            phone = str(row["phone"]).strip()

        # upsert logic (update if exists, else insert)
        existing = db.query(StudentDB).filter(StudentDB.stu_id == stu_id).first()

        if existing:
            existing.stu_name = stu_name
            existing.year = year
            existing.dept = dept
            existing.section = section
            existing.phone = phone
            updated += 1
        else:
            db.add(StudentDB(
                stu_id=stu_id,
                stu_name=stu_name,
                year=year,
                dept=dept,
                section=section,
                phone=phone
            ))
            inserted += 1

    db.commit()

    return {
        "message": "Student import completed !",
        "inserted": inserted,
        "updated": updated,
        "total_rows": len(df)
    }

@app.post("/exams/{exam_id}/registrations/import-excel")
def import_exam_registrations(exam_id: int, db: Session = Depends(get_db)):

    exam = db.query(ExamDB).filter(ExamDB.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    file_path = Path(__file__).resolve().parent.parent / "students_exams.xlsx"

    if not file_path.exists():
        return {"error": f"students_exams.xlsx not found at {file_path}"}

    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel read failed: {str(e)}")

    required_cols = {"stu_id", "subject_code"}
    if not required_cols.issubset(df.columns):
        missing = required_cols - set(df.columns)
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")

    inserted = 0
    skipped_missing_student = 0

    db.query(ExamRegistrationDB).filter(ExamRegistrationDB.exam_id == exam_id).delete()
    db.commit()

    for _, row in df.iterrows():
        stu_id = int(row["stu_id"])
        subject_code = str(row["subject_code"]).strip().upper()

        student = db.query(StudentDB).filter(StudentDB.stu_id == stu_id).first()
        if not student:
            skipped_missing_student += 1
            continue

        reg = ExamRegistrationDB(
            exam_id=exam_id,
            student_id=student.id,
            subject_code=subject_code
        )

        db.add(reg)
        inserted += 1

    db.commit()

    return {
        "message": "Exam registration import completed !",
        "exam_id": exam_id,
        "inserted": inserted,
        "skipped_missing_student": skipped_missing_student,
        "total_rows": len(df)
    }

@app.get("/exams/{exam_id}/registrations")
def get_exam_registrations(exam_id: int, db: Session = Depends(get_db)):
    regs = (
        db.query(ExamRegistrationDB, StudentDB)
        .join(StudentDB, ExamRegistrationDB.student_id == StudentDB.id)
        .filter(ExamRegistrationDB.exam_id == exam_id)
        .order_by(StudentDB.stu_id)
        .all()
    )

    return [
        {
            "stu_id": s.stu_id,
            "stu_name": s.stu_name,
            "year": s.year,
            "dept": s.dept,
            "section": s.section,
            "subject_code": r.subject_code
        }
        for r, s in regs
    ]

@app.get("/exams/{exam_id}/registrations")
def get_exam_registrations(exam_id: int, db: Session = Depends(get_db)):
    regs = (
        db.query(ExamRegistrationDB, StudentDB)
        .join(StudentDB, ExamRegistrationDB.student_id == StudentDB.id)
        .filter(ExamRegistrationDB.exam_id == exam_id)
        .order_by(StudentDB.stu_id)
        .all()
    )

    return [
        {
            "stu_id": s.stu_id,
            "stu_name": s.stu_name,
            "year": s.year,
            "dept": s.dept,
            "section": s.section,
            "subject_code": r.subject_code
        }
        for r, s in regs
    ]

class ClassroomCreateRequest(BaseModel):
    room_id: str
    seats_per_bench: int
    layout: dict

@app.post("/classrooms/create")
def create_classroom(
    room_id: str = Body(...),
    seats_per_bench: int = Body(2),
    layout: dict = Body(...),
    db: Session = Depends(get_db)
):
    """
    Example request body:
    {
      "room_id": "B201",
      "seats_per_bench": 2,
      "layout": {"1": 4, "2": 5, "3": 3}
    }
    """

    # check duplicate classroom
    existing = db.query(ClassroomDB).filter(ClassroomDB.room_id == room_id).first()
    if existing:
        return {"message": f"Classroom {room_id} already exists", "room_id": room_id}

    # save classroom
    classroom = ClassroomDB(
        room_id=room_id,
        seats_per_bench=seats_per_bench,
        layout_json=json.dumps(layout)
    )
    db.add(classroom)
    db.commit()
    db.refresh(classroom)

    # generate benches using your layout logic
    benches = generate_layout({int(k): int(v) for k, v in layout.items()})

    # store benches into DB
    for b in benches:
        db_bench = BenchDB(
            bench_id=b.bench_id,
            row=b.row,
            column=b.column,
            classroom_id=classroom.id
        )
        db.add(db_bench)

    db.commit()

    return {
        "message": "Classroom created !",
        "room_id": room_id,
        "seats_per_bench": seats_per_bench,
        "benches_created": len(benches)
    }


@app.get("/classrooms")
def get_classrooms(db: Session = Depends(get_db)):
    classrooms = db.query(ClassroomDB).all()
    return [
        {
            "room_id": c.room_id,
            "seats_per_bench": c.seats_per_bench,
            "layout": json.loads(c.layout_json)
        }
        for c in classrooms
    ]


@app.get("/classrooms/{room_id}/benches")
def get_benches(room_id: str, db: Session = Depends(get_db)):
    classroom = db.query(ClassroomDB).filter(ClassroomDB.room_id == room_id).first()
    if not classroom:
        return {"error": "Classroom not found"}

    benches = db.query(BenchDB).filter(BenchDB.classroom_id == classroom.id).all()

    return {
        "room_id": room_id,
        "total_benches": len(benches),
        "benches": [
            {"bench_id": b.bench_id, "row": b.row, "column": b.column}
            for b in benches
        ]
    }


@app.get("/capacity-check")
def capacity_check(room_id: str, db: Session = Depends(get_db)):
    # Total students
    total_students = db.query(StudentDB).count()

    classroom = db.query(ClassroomDB).filter(ClassroomDB.room_id == room_id).first()
    if not classroom:
        return {"error": "Classroom not found"}

    total_benches = db.query(BenchDB).filter(BenchDB.classroom_id == classroom.id).count()
    seats_per_bench = classroom.seats_per_bench

    total_seats = total_benches * seats_per_bench

    shortage = max(0, total_students - total_seats)
    benches_needed = ceil(shortage / seats_per_bench) if shortage > 0 else 0

    return {
        "room_id": room_id,
        "total_students": total_students,
        "total_benches": total_benches,
        "seats_per_bench": seats_per_bench,
        "total_seats": total_seats,
        "shortage_students": shortage,
        "additional_benches_needed": benches_needed
    }


class AllocateRequest(BaseModel):
    exam_id: int
    room_id: str

@app.post("/allocate")
def allocate_students_to_room(req: AllocateRequest, db: Session = Depends(get_db)):
    room_id = req.room_id

    classroom = db.query(ClassroomDB).filter(ClassroomDB.room_id == room_id).first()
    if not classroom:
        return {"error": "Classroom not found"}

    seats_per_bench = classroom.seats_per_bench  # 2 or 3

    students = (
    db.query(StudentDB)
    .join(ExamRegistrationDB, ExamRegistrationDB.student_id == StudentDB.id)
    .filter(ExamRegistrationDB.exam_id == req.exam_id)
    .order_by(StudentDB.stu_id)
    .all()
    )

    benches = (
        db.query(BenchDB)
        .filter(BenchDB.classroom_id == classroom.id)
        .order_by(BenchDB.column, BenchDB.row)
        .all()
    )

    db.query(AllocationDB)\
        .filter(AllocationDB.exam_id == req.exam_id)\
        .filter(AllocationDB.classroom_id == classroom.id)\
        .delete()

    db.commit()


    total_seats = len(benches) * seats_per_bench

    allocated = 0
    waiting = 0

    for i, student in enumerate(students):
        if i >= total_seats:
            waiting += 1
            continue

        bench_index = i // seats_per_bench
        seat_no = (i % seats_per_bench) + 1

        bench = benches[bench_index]

        alloc = AllocationDB(
            exam_id=req.exam_id,
            student_id=student.id,
            classroom_id=classroom.id,
            bench_id=bench.id,
            seat_no=seat_no,
            exam_name="Demo Exam"
        )
        db.add(alloc)
        allocated += 1

    db.commit()

    return {
        "message": "Allocation completed !",
        "room_id": room_id,
        "seats_per_bench": seats_per_bench,
        "total_benches": len(benches),
        "total_seats": total_seats,
        "allocated": allocated,
        "waiting": waiting
    }


@app.get("/public/seat-lookup")
def public_seat_lookup(
    exam_id: int = Query(...),
    stu_id: int = Query(...),
    db: Session = Depends(get_db)
):
    # Find student
    student = db.query(StudentDB).filter(StudentDB.stu_id == stu_id).first()
    if not student:
        return {"error": "Student not found"}

    # Find allocation for this student and exam
    result = (
        db.query(AllocationDB, BenchDB, ClassroomDB, ExamDB)
        .join(BenchDB, AllocationDB.bench_id == BenchDB.id)
        .join(ClassroomDB, AllocationDB.classroom_id == ClassroomDB.id)
        .join(ExamDB, AllocationDB.exam_id == ExamDB.id)
        .filter(AllocationDB.exam_id == exam_id)
        .filter(AllocationDB.student_id == student.id)
        .first()
    )

    if not result:
        return {"error": "Seat not allocated for this exam"}

    alloc, bench, classroom, exam = result

    return {
        "exam_id": exam.id,
        "exam_name": exam.exam_name,
        "stu_id": student.stu_id,
        "stu_name": student.stu_name,
        "room_id": classroom.room_id,
        "bench_id": bench.bench_id,
        "seat_no": alloc.seat_no,
        "row": bench.row,
        "column": bench.column
    }

 
@app.get("/export/allocation/excel")
def export_allocation_excel(
    exam_id: int = Query(...),
    room_id: str = Query(...),
    db: Session = Depends(get_db)
):
    classroom = db.query(ClassroomDB).filter(ClassroomDB.room_id == room_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    rows = (
        db.query(AllocationDB, StudentDB, BenchDB, ExamRegistrationDB)
        .join(StudentDB, AllocationDB.student_id == StudentDB.id)
        .join(BenchDB, AllocationDB.bench_id == BenchDB.id)
        .join(
            ExamRegistrationDB,
            (ExamRegistrationDB.student_id == StudentDB.id) &
            (ExamRegistrationDB.exam_id == AllocationDB.exam_id)
        )
        .filter(AllocationDB.exam_id == exam_id)
        .filter(AllocationDB.classroom_id == classroom.id)
        .order_by(BenchDB.column, BenchDB.row, AllocationDB.seat_no)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No allocation found for this exam+room. Run allocation first.")

    export_dir = Path(__file__).resolve().parent / "exports"
    export_dir.mkdir(exist_ok=True)

    file_path = export_dir / f"allocation_exam{exam_id}_{room_id}.xlsx"

    data = []
    for alloc, student, bench, reg in rows:
        data.append({
            "exam_id": alloc.exam_id,
            "stu_id": student.stu_id,
            "stu_name": student.stu_name,
            "year": student.year,
            "dept": student.dept,
            "section": student.section,
            "phone": student.phone,
            "subject_code": reg.subject_code,
            "room_id": room_id,
            "bench_id": bench.bench_id,
            "seat_no": alloc.seat_no,
            "column": bench.column,
            "row": bench.row
        })

    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False)

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.get("/export/allocation/pdf")
def export_allocation_pdf(
    exam_id: int = Query(...),
    room_id: str = Query(...),
    db: Session = Depends(get_db)
):
    classroom = db.query(ClassroomDB).filter(ClassroomDB.room_id == room_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    rows = (
        db.query(AllocationDB, StudentDB, BenchDB, ExamRegistrationDB, ExamDB)
        .join(StudentDB, AllocationDB.student_id == StudentDB.id)
        .join(BenchDB, AllocationDB.bench_id == BenchDB.id)
        .join(ExamDB, AllocationDB.exam_id == ExamDB.id)
        .join(
            ExamRegistrationDB,
            (ExamRegistrationDB.student_id == StudentDB.id) &
            (ExamRegistrationDB.exam_id == AllocationDB.exam_id)
        )
        .filter(AllocationDB.exam_id == exam_id)
        .filter(AllocationDB.classroom_id == classroom.id)
        .order_by(BenchDB.column, BenchDB.row, AllocationDB.seat_no)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No allocation found for this exam+room. Run allocation first.")

    export_dir = Path(__file__).resolve().parent / "exports"
    export_dir.mkdir(exist_ok=True)

    file_path = export_dir / f"allocation_exam{exam_id}_{room_id}.pdf"

    c = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4

    exam_name = rows[0][4].exam_name  # ExamDB

    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, f"Seating Arrangement - Exam {exam_id} ({exam_name}) - Room {room_id}")
    y -= 30

    # Header row
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50,  y, "Stu ID")
    c.drawString(95,  y, "Name")
    c.drawString(240, y, "Sub Code")
    c.drawString(305, y, "Bench")
    c.drawString(355, y, "Seat")
    c.drawString(395, y, "Col")
    c.drawString(430, y, "Row")
    y -= 12
    c.line(50, y, 550, y)
    y -= 15

    c.setFont("Helvetica", 9)

    for alloc, student, bench, reg, exam in rows:
        if y < 60:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, f"Seating Arrangement - Exam {exam_id} ({exam_name}) - Room {room_id}")
            y -= 30

            c.setFont("Helvetica-Bold", 9)
            c.drawString(50,  y, "Stu ID")
            c.drawString(95,  y, "Name")
            c.drawString(240, y, "Sub Code")
            c.drawString(305, y, "Bench")
            c.drawString(355, y, "Seat")
            c.drawString(395, y, "Col")
            c.drawString(430, y, "Row")
            y -= 12
            c.line(50, y, 550, y)
            y -= 15
            c.setFont("Helvetica", 9)

        c.drawString(50,  y, str(student.stu_id))
        c.drawString(95,  y, student.stu_name[:23])
        c.drawString(240, y, str(reg.subject_code))
        c.drawString(305, y, str(bench.bench_id))
        c.drawString(355, y, str(alloc.seat_no))
        c.drawString(395, y, str(bench.column))
        c.drawString(430, y, str(bench.row))
        y -= 14

    c.save()

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/pdf"
    )


class ExamCreateRequest(BaseModel):
    exam_name: str
    exam_date: str | None = None
    session: str | None = None

@app.post("/exams/create")
def create_exam(req: ExamCreateRequest, db: Session = Depends(get_db)):
    exam = ExamDB(exam_name=req.exam_name, exam_date=req.exam_date, session=req.session)
    db.add(exam)
    db.commit()
    db.refresh(exam)

    return {
        "message": "Exam created !",
        "exam_id": exam.id,
        "exam_name": exam.exam_name
    }

@app.get("/exams")
def get_exams(db: Session = Depends(get_db)):
    exams = db.query(ExamDB).order_by(ExamDB.id.desc()).all()
    return [
        {
            "exam_id": e.id,
            "exam_name": e.exam_name,
            "exam_date": e.exam_date,
            "session": e.session
        }
        for e in exams
    ]

class RegisterYearRequest(BaseModel):
    year: int

@app.post("/exams/{exam_id}/register/year")
def register_students_by_year(exam_id: int, req: RegisterYearRequest, db: Session = Depends(get_db)):
    exam = db.query(ExamDB).filter(ExamDB.id == exam_id).first()
    if not exam:
        return {"error": "Exam not found"}

    students = db.query(StudentDB).filter(StudentDB.year == req.year).all()
    if not students:
        return {"error": "No students found for that year"}

    # clear old registration for this exam
    db.query(ExamRegistrationDB).filter(ExamRegistrationDB.exam_id == exam_id).delete()
    db.commit()

    for s in students:
        db.add(ExamRegistrationDB(exam_id=exam_id, student_id=s.id))

    db.commit()

    return {
        "message": "Students registered !",
        "exam_id": exam_id,
        "registered_students": len(students)
    }

@app.get("/exams/{exam_id}/registrations")
def get_exam_registrations(exam_id: int, db: Session = Depends(get_db)):
    regs = (
        db.query(ExamRegistrationDB, StudentDB)
        .join(StudentDB, ExamRegistrationDB.student_id == StudentDB.id)
        .filter(ExamRegistrationDB.exam_id == exam_id)
        .order_by(StudentDB.stu_id)
        .all()
    )

    return [
        {
            "stu_id": s.stu_id,
            "stu_name": s.stu_name,
            "year": s.year,
            "dept": s.dept,
            "section": s.section,
            "subject_code": r.subject_code   
        }
        for r, s in regs
    ]

@app.post("/exams/{exam_id}/registrations/import-excel")
def import_exam_registrations(exam_id: int, db: Session = Depends(get_db)):
    
    exam = db.query(ExamDB).filter(ExamDB.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    file_path = Path(__file__).resolve().parent.parent / "students_exams.xlsx"

    if not file_path.exists():
        return {"error": f"students_exams.xlsx not found at {file_path}"}

    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel read failed: {str(e)}")

    required_cols = {"stu_id", "subject_code"}
    if not required_cols.issubset(df.columns):
        missing = required_cols - set(df.columns)
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")

    # Clear old registrations for this exam
    db.query(ExamRegistrationDB).filter(ExamRegistrationDB.exam_id == exam_id).delete()
    db.commit()

    inserted = 0
    skipped_missing_student = 0

    for _, row in df.iterrows():
        stu_id = int(row["stu_id"])
        subject_code = str(row["subject_code"]).strip().upper()

        student = db.query(StudentDB).filter(StudentDB.stu_id == stu_id).first()
        if not student:
            skipped_missing_student += 1
            continue

        db.add(
            ExamRegistrationDB(
                exam_id=exam_id,
                student_id=student.id,
                subject_code=subject_code,
            )
        )
        inserted += 1

    db.commit()

    return {
        "message": "Exam registrations imported !",
        "exam_id": exam_id,
        "inserted": inserted,
        "skipped_missing_student": skipped_missing_student,
        "total_rows": len(df),
    }

@app.get("/exams/{exam_id}/allocations")
def get_allocations(exam_id: int, room_id: str | None = None, db: Session = Depends(get_db)):
    q = (
        db.query(AllocationDB, StudentDB, BenchDB, ClassroomDB)
        .join(StudentDB, AllocationDB.student_id == StudentDB.id)
        .join(BenchDB, AllocationDB.bench_id == BenchDB.id)
        .join(ClassroomDB, AllocationDB.classroom_id == ClassroomDB.id)
        .filter(AllocationDB.exam_id == exam_id)
    )

    if room_id:
        q = q.filter(ClassroomDB.room_id == room_id)

    rows = q.order_by(ClassroomDB.room_id, BenchDB.column, BenchDB.row, AllocationDB.seat_no).all()

    return [
        {
            "stu_id": student.stu_id,
            "stu_name": student.stu_name,
            "room_id": classroom.room_id,
            "bench_id": bench.bench_id,
            "seat_no": alloc.seat_no,
            "column": bench.column,
            "row": bench.row
        }
        for alloc, student, bench, classroom in rows
    ]

class RoomsRequest(BaseModel):
    exam_id: int
    rooms: list[str]

@app.post("/capacity-check/multi")
def capacity_check_multi(req: RoomsRequest, db: Session = Depends(get_db)):
    # 1) Get classroom objects
    classrooms = db.query(ClassroomDB).filter(ClassroomDB.room_id.in_(req.rooms)).all()
    if not classrooms:
        return {"error": "No valid classrooms found"}

    # 2) Get registered students for exam
    students = (
        db.query(StudentDB)
        .join(ExamRegistrationDB, ExamRegistrationDB.student_id == StudentDB.id)
        .filter(ExamRegistrationDB.exam_id == req.exam_id)
        .order_by(StudentDB.stu_id)
        .all()
    )

    total_students = len(students)

    room_details = []
    total_seats = 0

    for c in classrooms:
        benches_count = db.query(BenchDB).filter(BenchDB.classroom_id == c.id).count()
        seats = benches_count * c.seats_per_bench
        total_seats += seats

        room_details.append({
            "room_id": c.room_id,
            "benches": benches_count,
            "seats_per_bench": c.seats_per_bench,
            "total_seats": seats
        })

    shortage = max(0, total_students - total_seats)

    return {
        "exam_id": req.exam_id,
        "registered_students": total_students,
        "selected_rooms": req.rooms,
        "total_seats": total_seats,
        "shortage_students": shortage,
        "room_details": room_details
    }


@app.post("/allocate/multi")
def allocate_multi_advanced(req: RoomsRequest, db: Session = Depends(get_db)):
    # 1) Validate classrooms
    classrooms = db.query(ClassroomDB).filter(ClassroomDB.room_id.in_(req.rooms)).all()
    if not classrooms:
        return {"error": "No valid classrooms found"}

    room_map = {c.room_id: c for c in classrooms}
    ordered_classrooms = [room_map[r] for r in req.rooms if r in room_map]

    # 2) Fetch registered students for the exam WITH subject_code
    regs = (
        db.query(ExamRegistrationDB, StudentDB)
        .join(StudentDB, ExamRegistrationDB.student_id == StudentDB.id)
        .filter(ExamRegistrationDB.exam_id == req.exam_id)
        .order_by(StudentDB.stu_id)
        .all()
    )

    if not regs:
        return {"error": "No exam registrations found. Import students_exams.xlsx first."}

    students = [{"student": s, "subject_code": r.subject_code} for r, s in regs]

    # 3) Clear old allocations for this exam
    db.query(AllocationDB).filter(AllocationDB.exam_id == req.exam_id).delete()
    db.commit()

    # 4) Build seat slots
    slots = build_seat_slots(db, ordered_classrooms)
    if not slots:
        return {"error": "No benches/seats found in selected rooms"}

    # 5) Build adjacency map
    adj_map = build_adjacency_map(slots)

    # 6) Run advanced allocator
    allocations, report = advanced_allocate(students, slots, adj_map)

    # 7) Save allocations to DB
    allocated = 0
    for a in allocations:
        slot = slots[a["slot_idx"]]
        student = a["student"]

        db.add(AllocationDB(
            exam_id=req.exam_id,
            student_id=student.id,
            classroom_id=slot["classroom_id"],
            bench_id=slot["bench_id"],
            seat_no=slot["seat_no"],
            exam_name="Advanced Exam"
        ))
        allocated += 1

    db.commit()

    waiting = max(0, len(students) - len(slots))

    return {
        "message": "Advanced multi-room allocation completed !",
        "exam_id": req.exam_id,
        "selected_rooms": req.rooms,
        "registered_students": len(students),
        "total_seats": len(slots),
        "allocated": allocated,
        "waiting": waiting,
        "quality_report": report
    }


# ------------------ ADVANCED ALLOCATOR HELPERS ------------------

def build_seat_slots(db: Session, classrooms_ordered):
    """
    Returns seat slots in order:
    [
      {"classroom_id":..., "room_id":..., "bench_id":..., "bench_key":(room_id,col,row), "seat_no":1},
      ...
    ]
    bench_key is used for adjacency.
    """
    slots = []

    for c in classrooms_ordered:
        benches = (
            db.query(BenchDB)
            .filter(BenchDB.classroom_id == c.id)
            .order_by(BenchDB.column, BenchDB.row)
            .all()
        )
        for bench in benches:
            for seat_no in range(1, c.seats_per_bench + 1):
                slots.append({
                    "classroom_id": c.id,
                    "room_id": c.room_id,
                    "bench_id": bench.id,
                    "bench_key": (c.room_id, bench.column, bench.row),
                    "seat_no": seat_no,
                    "col": bench.column,
                    "row": bench.row,
                })

    return slots


def build_adjacency_map(slots):
    """
    adjacency is based on benches:
      - same bench (strong)
      - left/right benches (col-1 / col+1 same row)
      - front/back benches (same col row-1/row+1)
    """
    # map bench_key -> indices of slots in that bench
    bench_to_slot_idxs = defaultdict(list)
    bench_exists = set()

    for i, s in enumerate(slots):
        bench_to_slot_idxs[s["bench_key"]].append(i)
        bench_exists.add(s["bench_key"])

    # adjacency map per slot index -> neighbor slot indices
    adj = defaultdict(set)

    for bench_key, idxs in bench_to_slot_idxs.items():
        room_id, col, row = bench_key

        # 1) Same bench adjacency: all seats on same bench are neighbors
        for a in idxs:
            for b in idxs:
                if a != b:
                    adj[a].add(b)

        # 2) Neighbor benches
        neighbor_benches = [
            (room_id, col - 1, row),
            (room_id, col + 1, row),
            (room_id, col, row - 1),
            (room_id, col, row + 1),
        ]

        for nb in neighbor_benches:
            if nb in bench_exists:
                for a in idxs:
                    for b in bench_to_slot_idxs[nb]:
                        adj[a].add(b)

    return adj


def advanced_allocate(students, slots, adj_map):
    """
    students: list of dicts
      [{"student": StudentDB, "subject_code": "OS301"}, ...]

    returns:
      allocations: list of dict {slot_index, student, subject_code}
      report: violation counts
    """

    # Weights (you can tune these)
    W_SAME_SUBJECT_SAME_BENCH = 1000
    W_SAME_DEPT_SAME_BENCH    = 600
    W_SAME_SUBJECT_ADJ        = 120
    W_SAME_DEPT_ADJ           = 50
    W_SAME_SECTION_ADJ        = 20
    W_SAME_YEAR_ADJ           = 10

    # Remaining students list
    remaining = students[:]

    # placements: slot_index -> placed student info
    placed = {}

    # for quick check: bench_key -> list of placed infos on that bench
    bench_placed = defaultdict(list)

    # report counters
    report = {
        "viol_same_subject_same_bench": 0,
        "viol_same_dept_same_bench": 0,
        "viol_same_subject_adjacent": 0,
        "viol_same_dept_adjacent": 0,
        "viol_same_section_adjacent": 0,
        "viol_same_year_adjacent": 0,
    }

    def score_candidate(slot_idx, cand):
        """
        lower score = better
        cand has keys: student, subject_code
        """
        slot = slots[slot_idx]
        bench_key = slot["bench_key"]

        score = 0

        # --- Bench rule checks (hard)
        for other in bench_placed[bench_key]:
            if other["subject_code"] == cand["subject_code"]:
                score += W_SAME_SUBJECT_SAME_BENCH
            if other["student"].dept == cand["student"].dept:
                score += W_SAME_DEPT_SAME_BENCH

        # --- Adjacency checks (soft)
        for nb_idx in adj_map.get(slot_idx, []):
            if nb_idx not in placed:
                continue
            other = placed[nb_idx]

            if other["subject_code"] == cand["subject_code"]:
                score += W_SAME_SUBJECT_ADJ
            if other["student"].dept == cand["student"].dept:
                score += W_SAME_DEPT_ADJ
            if other["student"].section == cand["student"].section:
                score += W_SAME_SECTION_ADJ
            if other["student"].year == cand["student"].year:
                score += W_SAME_YEAR_ADJ

        return score

    # Greedy seat filling
    for slot_idx in range(min(len(slots), len(remaining))):
        # pick best candidate among remaining students
        best_i = None
        best_score = None

        # To keep it efficient, sample up to N candidates each time
        # (for huge numbers). For small N, it checks all.
        CANDIDATE_LIMIT = 80
        candidate_pool = remaining if len(remaining) <= CANDIDATE_LIMIT else remaining[:CANDIDATE_LIMIT]

        for i, cand in enumerate(candidate_pool):
            s = score_candidate(slot_idx, cand)
            if best_score is None or s < best_score:
                best_score = s
                best_i = i

                # perfect score found
                if best_score == 0:
                    break

        chosen = remaining.pop(best_i)
        placed[slot_idx] = chosen
        bench_placed[slots[slot_idx]["bench_key"]].append(chosen)

    # Build report by checking violations in final placement
    # (This counts actual violations, not just penalty scores)
    for slot_idx, info in placed.items():
        slot = slots[slot_idx]
        bench_key = slot["bench_key"]

        # same bench violations
        for other in bench_placed[bench_key]:
            if other is info:
                continue
            if other["subject_code"] == info["subject_code"]:
                report["viol_same_subject_same_bench"] += 1
            if other["student"].dept == info["student"].dept:
                report["viol_same_dept_same_bench"] += 1

        # adjacency violations
        for nb in adj_map.get(slot_idx, []):
            if nb not in placed:
                continue
            other = placed[nb]
            if other["subject_code"] == info["subject_code"]:
                report["viol_same_subject_adjacent"] += 1
            if other["student"].dept == info["student"].dept:
                report["viol_same_dept_adjacent"] += 1
            if other["student"].section == info["student"].section:
                report["viol_same_section_adjacent"] += 1
            if other["student"].year == info["student"].year:
                report["viol_same_year_adjacent"] += 1

    # adjacency counts are double-counted (A-B and B-A), divide by 2
    for k in ["viol_same_subject_adjacent", "viol_same_dept_adjacent", "viol_same_section_adjacent", "viol_same_year_adjacent"]:
        report[k] = report[k] // 2

    # bench counts double-counted too (seat1-seat2 and seat2-seat1)
    report["viol_same_subject_same_bench"] = report["viol_same_subject_same_bench"] // 2
    report["viol_same_dept_same_bench"] = report["viol_same_dept_same_bench"] // 2

    allocations = []
    for slot_idx, info in placed.items():
        allocations.append({"slot_idx": slot_idx, **info})

    allocations.sort(key=lambda x: x["slot_idx"])
    return allocations, report
