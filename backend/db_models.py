from sqlalchemy import Column, Integer, String, ForeignKey, Identity 
from sqlalchemy.orm import relationship
from database import Base

class StudentDB(Base): 
    __tablename__ = "students"

    id = Column(Integer, Identity(start=1, always=True), primary_key=True)
    stu_id = Column(Integer, unique = True, nullable = False)
    stu_name = Column(String(100), nullable = False)
    year = Column(Integer, nullable = False)
    dept = Column(String(50), nullable=False)
    section = Column(String(10), nullable=False)
    phone = Column(String(20), nullable=True)

class ClassroomDB(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, Identity(start=1, always=True), primary_key=True)
    room_id = Column(String(100), unique=True, index=True, nullable=False)
    seats_per_bench = Column(Integer, nullable=False, default=2)

    # store layout like: {"1":4,"2":5,"3":3}
    layout_json = Column(String(2000), nullable=False)

    benches = relationship("BenchDB", back_populates="classroom", cascade="all, delete")


class BenchDB(Base):
    __tablename__ = "benches"

    id = Column(Integer, Identity(start=1, always=True), primary_key=True)
    bench_id = Column(String(100), index=True, nullable=False)  
    row_no = Column(Integer, nullable=False)
    col_no = Column(Integer, nullable=False)

    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=False)
    classroom = relationship("ClassroomDB", back_populates="benches")

class AllocationDB(Base):
    __tablename__ = "allocations"

    id = Column(Integer, Identity(start=1, always=True), primary_key=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=False)
    bench_id = Column(Integer, ForeignKey("benches.id"), nullable=False)
    seat_no = Column(Integer, nullable=False) 
    
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    exam_name = Column(String(200), nullable=True)

    student = relationship("StudentDB")
    classroom = relationship("ClassroomDB")
    bench = relationship("BenchDB")

class ExamDB(Base):
    __tablename__ = "exams"

    id = Column(Integer, Identity(start=1, always=True), primary_key=True)
    exam_name = Column(String(200), nullable=False)
    exam_date = Column(String(50), nullable=True)   
    session = Column(String(50), nullable=True)     


class ExamRegistrationDB(Base):
    __tablename__ = "exam_registrations"

    id = Column(Integer, Identity(start=1, always=True), primary_key=True)

    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    subject_code = Column(String(50), nullable=False)

    exam = relationship("ExamDB")
    student = relationship("StudentDB")





