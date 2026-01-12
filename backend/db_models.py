from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class StudentDB(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key = True, index = True)
    stu_id = Column(Integer, unique = True, nullable = False)
    stu_name = Column(String, nullable = False)
    year = Column(Integer, nullable = False)
    subject = Column(String, nullable = False)

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
    bench_id = Column(String, index=True, nullable=False)  # "C1-R1"
    row = Column(Integer, nullable=False)
    column = Column(Integer, nullable=False)

    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=False)
    classroom = relationship("ClassroomDB", back_populates="benches")

class AllocationDB(Base):
    __tablename__ = "allocations"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=False)
    bench_id = Column(Integer, ForeignKey("benches.id"), nullable=False)

    exam_name = Column(String, nullable=True)

    student = relationship("StudentDB")
    classroom = relationship("ClassroomDB")
    bench = relationship("BenchDB")


