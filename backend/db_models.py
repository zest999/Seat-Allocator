from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class StudentDB(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key = True, index = True)
    stu_id = Column(Integer, unique = True, nullable = False)
    stu_name = Column(String, nullable = False)
    year = Column(Integer, nullable = False)
    dept = Column(String, nullable=False)
    section = Column(String, nullable=False)
    phone = Column(String, nullable=True)

class ClassroomDB(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, unique=True, index=True, nullable=False)
    seats_per_bench = Column(Integer, nullable=False, default=2)

    # store layout like: {"1":4,"2":5,"3":3}
    layout_json = Column(String, nullable=False)

    benches = relationship("BenchDB", back_populates="classroom", cascade="all, delete")


class BenchDB(Base):
    __tablename__ = "benches"

    id = Column(Integer, primary_key=True, index=True)
    bench_id = Column(String, index=True, nullable=False)  
    row_no = Column(Integer, nullable=False)
    col_no = Column(Integer, nullable=False)

    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=False)
    classroom = relationship("ClassroomDB", back_populates="benches")

class AllocationDB(Base):
    __tablename__ = "allocations"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=False)
    bench_id = Column(Integer, ForeignKey("benches.id"), nullable=False)
    seat_no = Column(Integer, nullable=False) 
    
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    exam_name = Column(String, nullable=True)

    student = relationship("StudentDB")
    classroom = relationship("ClassroomDB")
    bench = relationship("BenchDB")

class ExamDB(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    exam_name = Column(String, nullable=False)
    exam_date = Column(String, nullable=True)   
    session = Column(String, nullable=True)     


class ExamRegistrationDB(Base):
    __tablename__ = "exam_registrations"

    id = Column(Integer, primary_key=True, index=True)

    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    subject_code = Column(String, nullable=False)

    exam = relationship("ExamDB")
    student = relationship("StudentDB")





