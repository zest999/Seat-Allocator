class Student:
    def __init__(self, stu_id, stu_name, year, subject):
        self.stu_id = stu_id
        self.name = stu_name
        self.year = year
        self.subject = subject

class Classroom:
    def __init__(self, room_id, benches):
        self.room_id = room_id
        self.benches = benches

class Bench:
    def __init__(self, row, column, bench_id):
        self.row = row
        self.column = column
        self.bench_id = bench_id
