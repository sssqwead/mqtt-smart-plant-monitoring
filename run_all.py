import subprocess
import time
import signal
import sys

PLANT_TYPES = ["ficus", "cactus"]

controllers = [
    "controller_moisture.py",
    "controller_temp.py",
    "controller_humidity.py",
    "controller_nitrogen.py",
    "controller_phosphorus.py",
    "controller_potassium.py",
    "controller_ph.py",
    "controller_salinity.py",
    "controller_root_temp.py",
]

publishers = [
    "publisher_moisture.py",
    "publisher_temp.py",
    "publisher_humidity.py",
    "publisher_nitrogen.py",
    "publisher_phosphorus.py",
    "publisher_potassium.py",
    "publisher_ph.py",
    "publisher_salinity.py",
    "publisher_root_temp.py",
]

processes = []


def start_process(cmd):
    print(f"[run_all] starting: {' '.join(cmd)}")
    return subprocess.Popen(cmd)


def start_all():
    for c in controllers:
        processes.append(start_process(["python", c]))

    time.sleep(2)

    for plant_type in PLANT_TYPES:
        for p in publishers:
            processes.append(start_process(["python", p, plant_type]))

    processes.append(start_process(["python", "dashboard.py"]))


def shutdown(signum=None, frame=None):
    print("\n[run_all] shutting down...")

    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass

    time.sleep(1)

    for p in processes:
        try:
            p.kill()
        except Exception:
            pass

    print("[run_all] all processes stopped")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    start_all()
    print("\n[run_all] system started. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()
