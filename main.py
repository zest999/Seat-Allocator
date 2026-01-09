from student_import import student_import_excel, review_students
from layouts import generate_layout
from allocator import allocate_students
from models import Classroom


students = student_import_excel("students.xlsx")
students = review_students(students)


layout_template = {
    1: 4,  
    2: 2,   
    3: 3
}

benches = generate_layout(layout_template)
classroom = Classroom("B201", benches)


allocations = allocate_students(students, classroom)


print("\n--- Seat Allocation ---")
for a in allocations:
    s = a["student"]
    b = a["bench"]
    print(
        f"{s.stu_name} -> Room {a['room']} | Column {b.column} | Row {b.row}"
    )


