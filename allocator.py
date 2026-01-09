def allocate_students(students, classroom):
    allocation = []
    index = 0

    for bench in classroom.benches:
        if index >= len(students):
            break

        allocation.append({
            "student": students[index],
            "room": classroom.room_id,
            "bench": bench
        })

        index += 1
    return allocation
