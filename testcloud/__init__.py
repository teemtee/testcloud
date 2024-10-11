# NOTE: if you update version, *make sure* to also update `docs/source/conf.py`
__version__ = "0.11.1"

import signal
import sys
import threading


def sigterm_handler(_signo, _stack_frame):
    # A call to sys.exit() is translated into an exception so that clean-up handlers
    #  (finally clauses of try statements) can be executed, and so that a debugger can
    #  execute a script without running the risk of losing control.
    sys.exit(0)


if threading.current_thread() is threading.main_thread():
    signal.signal(signal.SIGTERM, sigterm_handler)
