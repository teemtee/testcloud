import importlib.metadata
import signal
import sys
import threading

__version__ = importlib.metadata.version(__name__)


def sigterm_handler(_signo, _stack_frame):
    # A call to sys.exit() is translated into an exception so that clean-up handlers
    #  (finally clauses of try statements) can be executed, and so that a debugger can
    #  execute a script without running the risk of losing control.
    sys.exit(0)


if threading.current_thread() is threading.main_thread():
    signal.signal(signal.SIGTERM, sigterm_handler)
