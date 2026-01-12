from fastapi import FastAPI, Depends, Body, HTTPException
from sqlalchemy.orm import Session
from database import Base, engine, SessionLocal
from db_models import StudentDB, ClassroomDB, BenchDB, AllocationDB
import pandas as pd
import json
from math import ceil
from layouts import generate_layout
from pydantic import BaseModel
from fastapi.responses import FileResponse
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas



app = FastAPI(title = "Seat Allocator API")

Base.metadata.create_all(bind = engine)

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
        "message": "Student import completed ✅",
        "inserted": inserted,
        "skipped_duplicates": skipped
    }


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
        "message": "Classroom created ✅",
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
    room_id: str

@app.post("/allocate")
def allocate_students_to_room(req: AllocateRequest, db: Session = Depends(get_db)):
    room_id = req.room_id

    classroom = db.query(ClassroomDB).filter(ClassroomDB.room_id == room_id).first()
    if not classroom:
        return {"error": "Classroom not found"}

    students = db.query(StudentDB).order_by(StudentDB.stu_id).all()
    benches = (
        db.query(BenchDB)
        .filter(BenchDB.classroom_id == classroom.id)
        .order_by(BenchDB.column, BenchDB.row)
        .all()
    )

    # clear old allocations for this room
    db.query(AllocationDB).filter(AllocationDB.classroom_id == classroom.id).delete()
    db.commit()

    allocated = 0
    waiting = 0

    for i, student in enumerate(students):
        if i >= len(benches):
            waiting += 1
            continue

        alloc = AllocationDB(
            student_id=student.id,
            classroom_id=classroom.id,
            bench_id=benches[i].id,
            exam_name="Demo Exam"
        )
        db.add(alloc)
        allocated += 1

    db.commit()

    return {
        "message": "Allocation completed ✅",
        "room_id": room_id,
        "allocated": allocated,
        "waiting": waiting
    }


@app.get("/public/seat-lookup")
def seat_lookup(stu_id: int, room_id: str, db: Session = Depends(get_db)):
    classroom = db.query(ClassroomDB).filter(ClassroomDB.room_id == room_id).first()
    if not classroom:
        return {"error": "Classroom not found"}

    student = db.query(StudentDB).filter(StudentDB.stu_id == stu_id).first()
    if not student:
        return {"error": "Student not found"}

    allocation = (
        db.query(AllocationDB)
        .filter(AllocationDB.student_id == student.id)
        .filter(AllocationDB.classroom_id == classroom.id)
        .first()
    )

    if not allocation:
        return {"error": "Seat not allocated yet"}

    bench = db.query(BenchDB).filter(BenchDB.id == allocation.bench_id).first()

    return {
        "stu_id": student.stu_id,
        "stu_name": student.stu_name,
        "room_id": classroom.room_id,
        "bench_id": bench.bench_id,
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
            "row": bench.row
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
    c.drawString(350, y, "Column")
    c.drawString(410, y, "Row")
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
        c.drawString(350, y, str(bench.column))
        c.drawString(410, y, str(bench.row))
        y -= 15

    c.save()

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/pdf"
    )
