"""Own only the foreground child; close it on interrupt or termination."""
import signal
import subprocess


def foreground(command):
    previous = {}
    status = 130
    child = None

    def interrupt(signum, frame):
        nonlocal status
        status = 128 + signum
        raise KeyboardInterrupt

    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        number = getattr(signal, name, None)
        if number is not None:
            previous[number] = signal.signal(number, interrupt)
    try:
        child = subprocess.Popen(command)
        return child.wait()
    except KeyboardInterrupt:
        return status
    finally:
        # Repeated interrupts must not interrupt cleanup and orphan the child.
        for number in previous:
            signal.signal(number, signal.SIG_IGN)
        try:
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)
