import pandas as pd
from models import Student


def student_import_excel(file_path):

    students = []
    df = pd.read_excel(file_path)

    for _, row in df.iterrows():
        students.append( 
            Student(
                stu_id = int(row["stu_id"]),
                stu_name = str(row["stu_name"]),
                year = int(row["year"]),
                subject = str(row["subject"])
            )
        )

    return students

def review_students (students):
    print("\n Student List")
    for s in students:
        print(f"{s.stu_id}:{s.stu_name}, Year:{s.year}, Subject:{s.subject}")

    choice = input("\nDo you want to edit any student? (y/n): ")

    if choice.lower() == "y":
        sid = int(input("Enter student ID to edit: "))
        for s in students:
            if s.stu_id == sid:
                s.name = input(f"Name ({s.stu_name}): ") or s.name
                s.year = int(input(f"Year ({s.year}): ") or s.year)
                s.subject = input(f"Subject ({s.subject}): ") or s.subject

    return students



        

