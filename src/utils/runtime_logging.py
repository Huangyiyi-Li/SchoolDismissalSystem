from __future__ import annotations

import atexit
import builtins
import faulthandler
import logging
import os
import sys
import threading
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler

from .path_utils import get_app_root


@dataclass(frozen=True)
class RuntimeLogPaths:
    runtime_log_path: str
    crash_log_path: str


_PRINT_WRAPPED = False
_CRASH_STREAM = None
_QT_HANDLER_INSTALLED = False
_ORIGINAL_PRINT = builtins.print


def get_runtime_log_paths(log_dir: str | None = None) -> RuntimeLogPaths:
    resolved_log_dir = log_dir or os.path.join(get_app_root(), "logs")
    return RuntimeLogPaths(
        runtime_log_path=os.path.join(resolved_log_dir, "runtime.log"),
        crash_log_path=os.path.join(resolved_log_dir, "crash.log"),
    )


def configure_runtime_logging(log_dir: str | None = None) -> RuntimeLogPaths:
    global _CRASH_STREAM

    paths = get_runtime_log_paths(log_dir)
    os.makedirs(os.path.dirname(paths.runtime_log_path), exist_ok=True)

    root_logger = logging.getLogger()
    if not getattr(root_logger, "_schooldismissal_runtime_configured", False):
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s"
        )
        file_handler = TimedRotatingFileHandler(
            paths.runtime_log_path,
            when="midnight",
            backupCount=7,
            encoding="utf-8",
        )
        file_handler._schooldismissal_runtime_handler = True  # type: ignore[attr-defined]
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler(sys.__stderr__)
        stream_handler._schooldismissal_runtime_handler = True  # type: ignore[attr-defined]
        stream_handler.setFormatter(formatter)
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(stream_handler)
        root_logger._schooldismissal_runtime_configured = True

    _install_print_logging()
    _install_exception_hooks()
    _install_qt_message_logging()

    if _CRASH_STREAM is None:
        _CRASH_STREAM = open(paths.crash_log_path, "a", encoding="utf-8", buffering=1)
        atexit.register(_close_crash_stream)
        try:
            faulthandler.enable(_CRASH_STREAM, all_threads=True)
        except Exception:
            logging.getLogger(__name__).exception("Failed to enable faulthandler")

    logging.getLogger("runtime").info(
        "Runtime logging initialized. runtime_log=%s crash_log=%s",
        paths.runtime_log_path,
        paths.crash_log_path,
    )
    return paths


def _install_print_logging() -> None:
    global _PRINT_WRAPPED
    if _PRINT_WRAPPED:
        return

    def logged_print(*args, **kwargs):
        _ORIGINAL_PRINT(*args, **kwargs)
        target = kwargs.get("file")
        if target not in (None, sys.stdout, sys.__stdout__, sys.stderr, sys.__stderr__):
            return
        sep = kwargs.get("sep", " ")
        message = sep.join(str(arg) for arg in args).strip()
        if message:
            logging.getLogger("stdout").info(message)

    logged_print._schooldismissal_wrapped = True  # type: ignore[attr-defined]
    builtins.print = logged_print
    _PRINT_WRAPPED = True


def _install_exception_hooks() -> None:
    def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc_value, exc_traceback)
        logging.getLogger("crash").critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def handle_thread_exception(args):
        logging.getLogger("crash").critical(
            "Unhandled thread exception in %s",
            getattr(args.thread, "name", "unknown"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    def handle_unraisable(unraisable):
        logging.getLogger("crash").critical(
            "Unraisable exception: %s",
            getattr(unraisable, "err_msg", "unknown"),
            exc_info=(
                type(unraisable.exc_value),
                unraisable.exc_value,
                unraisable.exc_traceback,
            ),
        )

    sys.excepthook = handle_uncaught_exception
    if hasattr(threading, "excepthook"):
        threading.excepthook = handle_thread_exception
    if hasattr(sys, "unraisablehook"):
        sys.unraisablehook = handle_unraisable


def _install_qt_message_logging() -> None:
    global _QT_HANDLER_INSTALLED
    if _QT_HANDLER_INSTALLED:
        return

    try:
        from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
    except ModuleNotFoundError:
        return

    def qt_message_handler(mode, context, message):
        logger = logging.getLogger("qt")
        if mode == QtMsgType.QtFatalMsg:
            logger.critical(message)
        elif mode == QtMsgType.QtCriticalMsg:
            logger.error(message)
        elif mode == QtMsgType.QtWarningMsg:
            logger.warning(message)
        else:
            logger.info(message)

    qInstallMessageHandler(qt_message_handler)
    _QT_HANDLER_INSTALLED = True


def _close_crash_stream() -> None:
    global _CRASH_STREAM
    if _CRASH_STREAM is None:
        return
    try:
        _CRASH_STREAM.flush()
        _CRASH_STREAM.close()
    finally:
        _CRASH_STREAM = None


def shutdown_runtime_logging() -> None:
    global _PRINT_WRAPPED

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if getattr(handler, "_schooldismissal_runtime_handler", False):
            root_logger.removeHandler(handler)
            handler.flush()
            handler.close()
    root_logger._schooldismissal_runtime_configured = False
    if _PRINT_WRAPPED:
        builtins.print = _ORIGINAL_PRINT
        _PRINT_WRAPPED = False
    _close_crash_stream()
