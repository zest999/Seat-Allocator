from database import Base, engine
from db_models import (
    AllocationDB, ExamRegistrationDB, BenchDB, 
    ExamDB, ClassroomDB, StudentDB
)

print("Dropping all tables in correct order...")
Base.metadata.drop_all(bind=engine, tables=[
    AllocationDB.__table__,
    ExamRegistrationDB.__table__,
    BenchDB.__table__,
    ExamDB.__table__,
    ClassroomDB.__table__,
    StudentDB.__table__
])

print("Creating all tables with IDENTITY columns...")
Base.metadata.create_all(bind=engine)

print(" Database reset complete!")