import logging
import PyQt6
from PyQt6.QtCore import QObject, pyqtSignal as Signal


class SignalManager(QObject):

    # error handling
    raise_oms_error = Signal(tuple)
    # Raises error within OMS code ONLY.  If necessary, passes error to gui using self.exception
    # tuple of: (error level: int, exception: Exception, stop_signal: bool)

    exception = Signal(tuple)
    # raises error in the GUI, per above.
    # Tuple of (error level, error_text, stop_oms: bool, trace: traceback)

    unhandled_exception = Signal(tuple)

    # status changes
    config_update = Signal()
    trade_data_updated = Signal()
    trade_history_generated = Signal(str) # file path

    # logging
    log_record = Signal(logging.LogRecord)

    # FROM LEGACY GUI WorkerSignals
    start_timers = Signal()
    finished = Signal()
    raw_order_update = Signal()
    result = Signal(object)
    progress = Signal(int)


SIGNALS = SignalManager()
