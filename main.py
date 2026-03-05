import importlib.util  # for checking if a Python package is installed
import subprocess      # for launching each service as a separate OS process
import sys             # for passing the current Python interpreter path
import time            # for sleep between process health checks
from pathlib import Path

# Resolve the directory where this script lives so all paths are absolute
ROOT_DIR = Path(__file__).resolve().parent


def check_dependencies():
    """Check that required third-party packages are installed before launching."""
    missing = []
    if importlib.util.find_spec("paho") is None:
        missing.append("paho-mqtt")
    if importlib.util.find_spec("pygame") is None:
        missing.append("pygame")

    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Install them with:")
        print(f"  {sys.executable} -m pip install -r {ROOT_DIR / 'requirements.txt'}")
        return False
    return True


def start_process(script_name, *args):
    """
    Launch a Python script as a subprocess using the current interpreter.
    Extra positional args (e.g. plant type) are forwarded to the script.
    """
    script_path = ROOT_DIR / script_name
    return subprocess.Popen(
        [sys.executable, str(script_path), *args],
        cwd=str(ROOT_DIR),  # run from the project root so relative paths work
    )


def stop_process(process):
    """Gracefully terminate a subprocess, killing it if it does not stop in time."""
    if process.poll() is not None:
        return  # process already exited — nothing to do

    process.terminate()  # send SIGTERM
    try:
        process.wait(timeout=5)  # wait up to 5 seconds for clean exit
    except subprocess.TimeoutExpired:
        process.kill()  # force kill if it didn't respond to SIGTERM


def main():
    if not check_dependencies():
        return 1  # exit early if a required package is missing

    print("Starting Smart Plant Monitoring System…")
    print("Launching: controller | ficus publisher | cactus publisher | dashboard")

    # Start the controller first so it's ready before publishers connect
    controller = start_process("controller.py")
    time.sleep(1)  # give the controller time to connect to the broker

    # Start both plant publishers with their type as a CLI argument
    publisher_ficus  = start_process("publisher.py", "ficus")
    time.sleep(0.5)  # stagger startup to avoid simultaneous broker connections
    publisher_cactus = start_process("publisher.py", "cactus")
    time.sleep(0.5)

    # Start the Pygame dashboard last (depends on data already flowing)
    dashboard = start_process("dashboard.py")

    # Map process names to their Popen handles for monitoring and cleanup
    processes = {
        "controller.py":        controller,
        "publisher.py(ficus)":  publisher_ficus,
        "publisher.py(cactus)": publisher_cactus,
        "dashboard.py":         dashboard,
    }

    print("\nAll services running. Press Ctrl+C to stop.\n")

    try:
        while True:
            # Poll each process and report if any stopped unexpectedly
            for name, proc in processes.items():
                if proc.poll() is not None:
                    print(f"{name} stopped unexpectedly.")
            time.sleep(0.5)  # check every 500 ms
    except KeyboardInterrupt:
        print("\nStopping all services…")
    finally:
        # Always stop all subprocesses on exit, even if an error occurred
        for proc in processes.values():
            stop_process(proc)
        print("All stopped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
