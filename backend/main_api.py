from fastapi import FastAPI, Depends, Body, HTTPException, Query
from sqlalchemy.orm import Session
from database import Base, engine, SessionLocal
from db_models import StudentDB, ClassroomDB, BenchDB, AllocationDB, ExamDB, ExamRegistrationDB
import pandas as pd
import json
from math import ceil
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
    students = db.query(StudentDB).all()
    return [
        {
            "stu_id": s.stu_id,
            "stu_name": s.stu_name,
            "year": s.year,
            "subject": s.subject
        }
        for s in students
    ]


@app.post("/students/import")
def import_students_from_excel(db: Session = Depends(get_db)):
    file_path = "../students.xlsx"  

    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel read failed: {str(e)}")

    required_cols = {"stu_id", "stu_name", "year", "subject"}
    if not required_cols.issubset(df.columns):
        missing = required_cols - set(df.columns)
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")

    inserted = 0
    skipped = 0

    for _, row in df.iterrows():
        stu_id = int(row["stu_id"])

        existing = db.query(StudentDB).filter(StudentDB.stu_id == stu_id).first()
        if existing:
            skipped += 1
            continue

        student = StudentDB(
            stu_id=stu_id,
            stu_name=str(row["stu_name"]),
            year=int(row["year"]),
            subject=str(row["subject"])
        )

        db.add(student)
        inserted += 1

    db.commit()

    return {
        "message": "Student import completed !",
        "inserted": inserted,
        "skipped_duplicates": skipped
    }

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
def export_allocation_excel(room_id: str, db: Session = Depends(get_db)):
    classroom = db.query(ClassroomDB).filter(ClassroomDB.room_id == room_id).first()
    if not classroom:
        return {"error": "Classroom not found"}

    allocations = (
        db.query(AllocationDB, StudentDB, BenchDB)
        .join(StudentDB, AllocationDB.student_id == StudentDB.id)
        .join(BenchDB, AllocationDB.bench_id == BenchDB.id)
        .filter(AllocationDB.classroom_id == classroom.id)
        .order_by(BenchDB.column, BenchDB.row)
        .all()
    )

    if not allocations:
        return {"error": "No allocation found. Run /allocate first."}

    data = []
    for alloc, student, bench in allocations:
        data.append({
            "stu_id": student.stu_id,
            "stu_name": student.stu_name,
            "year": student.year,
            "subject": student.subject,
            "room_id": classroom.room_id,
            "bench_id": bench.bench_id,
            "column": bench.column,
            "row": bench.row,
            "seat_no": alloc.seat_no
        })

    df = pd.DataFrame(data)

    # save excel in backend/exports/
    export_dir = Path(__file__).resolve().parent / "exports"
    export_dir.mkdir(exist_ok=True)

    file_path = export_dir / f"allocation_{room_id}.xlsx"
    df.to_excel(file_path, index=False)

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.get("/export/allocation/pdf")
def export_allocation_pdf(room_id: str, db: Session = Depends(get_db)):
    classroom = db.query(ClassroomDB).filter(ClassroomDB.room_id == room_id).first()
    if not classroom:
        return {"error": "Classroom not found"}

    allocations = (
        db.query(AllocationDB, StudentDB, BenchDB)
        .join(StudentDB, AllocationDB.student_id == StudentDB.id)
        .join(BenchDB, AllocationDB.bench_id == BenchDB.id)
        .filter(AllocationDB.classroom_id == classroom.id)
        .order_by(BenchDB.column, BenchDB.row)
        .all()
    )

    if not allocations:
        return {"error": "No allocation found. Run /allocate first."}

    export_dir = Path(__file__).resolve().parent / "exports"
    export_dir.mkdir(exist_ok=True)

    file_path = export_dir / f"allocation_{room_id}.pdf"

    c = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, f"Seating Arrangement - Room {room_id}")
    y -= 30

    c.setFont("Helvetica", 10)
    c.drawString(50, y, "Stu ID")
    c.drawString(110, y, "Name")
    c.drawString(280, y, "Bench")
    c.drawString(350, y, "Seat No")
    c.drawString(420, y, "Column")
    c.drawString(480, y, "Row")
    y -= 15

    c.line(50, y, 550, y)
    y -= 15

    for alloc, student, bench in allocations:
        if y < 60:
            c.showPage()
            y = height - 50

        c.drawString(50, y, str(student.stu_id))
        c.drawString(110, y, student.stu_name[:22])
        c.drawString(280, y, bench.bench_id)
        c.drawString(350, y, str(alloc.seat_no)) 
        c.drawString(350, y, str(bench.column))
        c.drawString(410, y, str(bench.row))
        y -= 15

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
            "subject": s.subject
        }
        for r, s in regs
    ]

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
def allocate_multi(req: RoomsRequest, db: Session = Depends(get_db)):
    # 1) Get classrooms in the same order user selected
    classrooms = db.query(ClassroomDB).filter(ClassroomDB.room_id.in_(req.rooms)).all()
    if not classrooms:
        return {"error": "No valid classrooms found"}

    # map room_id -> ClassroomDB
    room_map = {c.room_id: c for c in classrooms}
    ordered_classrooms = [room_map[r] for r in req.rooms if r in room_map]

    # 2) Get registered students
    students = (
        db.query(StudentDB)
        .join(ExamRegistrationDB, ExamRegistrationDB.student_id == StudentDB.id)
        .filter(ExamRegistrationDB.exam_id == req.exam_id)
        .order_by(StudentDB.stu_id)
        .all()
    )

    if not students:
        return {"error": "No registered students for this exam"}

    # 3) Clear old allocations for this exam (important)
    db.query(AllocationDB).filter(AllocationDB.exam_id == req.exam_id).delete()
    db.commit()

    # 4) Collect all benches room-by-room in order
    seat_slots = []  # each item: (classroom_id, bench_id, seat_no)
    for c in ordered_classrooms:
        benches = (
            db.query(BenchDB)
            .filter(BenchDB.classroom_id == c.id)
            .order_by(BenchDB.column, BenchDB.row)
            .all()
        )

        for bench in benches:
            for seat_no in range(1, c.seats_per_bench + 1):
                seat_slots.append((c.id, bench.id, seat_no))

    total_seats = len(seat_slots)

    allocated = 0
    waiting = 0

    # 5) Allocate students to slots
    for i, student in enumerate(students):
        if i >= total_seats:
            waiting += 1
            continue

        classroom_id, bench_id, seat_no = seat_slots[i]

        db.add(AllocationDB(
            exam_id=req.exam_id,
            student_id=student.id,
            classroom_id=classroom_id,
            bench_id=bench_id,
            seat_no=seat_no,
            exam_name="Demo Exam"
        ))
        allocated += 1

    db.commit()

    # 6) Summary room-wise allocated count
    room_summary = {}
    for c in ordered_classrooms:
        count = db.query(AllocationDB).filter(
            AllocationDB.exam_id == req.exam_id,
            AllocationDB.classroom_id == c.id
        ).count()
        room_summary[c.room_id] = count

    return {
        "message": "Multi-room allocation completed !",
        "exam_id": req.exam_id,
        "selected_rooms": req.rooms,
        "registered_students": len(students),
        "total_seats": total_seats,
        "allocated": allocated,
        "waiting": waiting,
        "room_summary": room_summary
    }

