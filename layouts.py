from models import Bench

def generate_layout(column_bench_map):
    benches = []

    for column, count in column_bench_map.items():
        for row in range(1, count + 1):
            benches.append(
                Bench(
                    row=row,
                    column=column,
                    bench_id=f"C{column}-R{row}"
                )
            )

    return benches

