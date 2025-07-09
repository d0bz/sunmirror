from concurrent.futures import ThreadPoolExecutor
import time

def do_io_task(i):
    print(f"Task {i} started")
    time.sleep(1)  # simulate I/O
    print(f"Task {i} done")

with ThreadPoolExecutor(max_workers=54) as executor:
    for i in range(54):
        executor.submit(do_io_task, i)

