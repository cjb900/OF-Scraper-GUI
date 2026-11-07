"""Background-safe subscription model fetch for the GUI.

The worker returns a list of **plain dicts** only. ``Model`` objects are built
on the Qt main thread after cleanup. Crossing the thread boundary with live
``Model`` instances (64+) was associated with Windows access violations after
``worker_done`` and before ``ui_poll_done``.

Hardening:
- Serialized fetches + asyncio timeout
- NullLive / quiet console prepared on the main thread only
- Safe Model ctor during API parse (worker); results converted to dicts before return
- Thread-safe handoff box so the Worker object need not retain the payload
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Iterable, Optional

log = logging.getLogger("shared")

_FETCH_LOCK = threading.RLock()
_DEFAULT_TIMEOUT_SEC = 180.0
_SKIPPED_NAME = "__gui_model_skip__"

_env_lock = threading.Lock()
_env_depth = 0
_RealModel = None
_activity_restores: list = []
_suppress_worker_gui_logs = False

# Thread-safe payload handoff (worker → main). Cleared by take_handoff().
_handoff_lock = threading.Lock()
_handoff: dict[str, Any] = {
    "gen": 0,
    "payload": None,
    "error": None,
    "ready": False,
}

# Worker waits on this after publishing so QThreadPool does not tear the thread
# down while the main thread is still uninstalling NullLive / Model patches.
_ui_ack = threading.Event()
_ui_ack.set()  # idle default: not blocking


def prepare_model_fetch_environment() -> None:
    """Install NullLive / quiet console / safe Model — call on Qt main thread."""
    global _env_depth, _RealModel, _activity_restores, _suppress_worker_gui_logs
    from ofscraper.gui.utils.crash_diagnostics import breadcrumb, set_model_fetch_active
    from ofscraper.gui.utils.workflow import _install_gui_live_stubs
    import ofscraper.classes.of.models as models_cls
    from ofscraper.utils.live import updater as live_updater

    with _env_lock:
        if _env_depth == 0:
            _suppress_worker_gui_logs = True
            RealModel = models_cls.Model
            _RealModel = RealModel
            _activity_restores = []

            class _SkippedModel:
                name = _SKIPPED_NAME
                id = None

                def __init__(self, *_a, **_k):
                    pass

            def _safe_model(data):
                try:
                    return RealModel(data)
                except Exception:
                    return _SkippedModel()

            try:
                for attr in ("update_task", "update_activity", "update_activity_task"):
                    obj = getattr(live_updater, "activity", None)
                    if obj is None or not hasattr(obj, attr):
                        continue
                    old = getattr(obj, attr)
                    setattr(obj, attr, lambda *a, **k: None)
                    _activity_restores.append((obj, attr, old))
            except Exception as e:
                log.debug(f"[GUI model fetch] Could not mute live updater: {e}")

            _install_gui_live_stubs()
            models_cls.Model = _safe_model
            clear_ui_ack()
            set_model_fetch_active(True)
        _env_depth += 1
    breadcrumb("env_prepared", f"depth={_env_depth}")


def cleanup_model_fetch_environment() -> None:
    """Undo prepare — call on Qt main thread after the worker finishes."""
    global _env_depth, _RealModel, _activity_restores, _suppress_worker_gui_logs
    from ofscraper.gui.utils.crash_diagnostics import breadcrumb, set_model_fetch_active
    from ofscraper.gui.utils.workflow import _uninstall_gui_live_stubs
    import ofscraper.classes.of.models as models_cls

    with _env_lock:
        if _env_depth <= 0:
            signal_ui_ack()
            return
        _env_depth -= 1
        if _env_depth == 0:
            if _RealModel is not None:
                models_cls.Model = _RealModel
                _RealModel = None
            for obj, attr, old in _activity_restores:
                try:
                    setattr(obj, attr, old)
                except Exception:
                    pass
            _activity_restores = []
            try:
                _uninstall_gui_live_stubs()
            except Exception as e:
                log.debug(f"[GUI model fetch] Live stub uninstall failed: {e}")
            _suppress_worker_gui_logs = False
            set_model_fetch_active(False)
    breadcrumb("env_cleaned", f"depth={_env_depth}")
    # Release the pool worker only after patches are gone.
    signal_ui_ack()


def publish_handoff(*, gen: int, payload=None, error: str | None = None) -> None:
    """Worker publishes result; main thread takes it via ``take_handoff``."""
    with _handoff_lock:
        _handoff["gen"] = int(gen)
        _handoff["payload"] = payload
        _handoff["error"] = error
        _handoff["ready"] = True


def handoff_ready(expected_gen: int) -> bool:
    """True when the worker has published a handoff for *expected_gen*."""
    with _handoff_lock:
        return bool(_handoff["ready"]) and int(_handoff["gen"]) == int(expected_gen)


def take_handoff(expected_gen: int) -> dict | None:
    """Return ``{payload, error}`` once, or None if not ready / wrong gen."""
    with _handoff_lock:
        if not _handoff["ready"]:
            return None
        if int(_handoff["gen"]) != int(expected_gen):
            return None
        out = {"payload": _handoff["payload"], "error": _handoff["error"]}
        _handoff["payload"] = None
        _handoff["error"] = None
        _handoff["ready"] = False
        return out


def clear_handoff() -> None:
    with _handoff_lock:
        _handoff["payload"] = None
        _handoff["error"] = None
        _handoff["ready"] = False
        _handoff["gen"] = 0


def clear_ui_ack() -> None:
    """Reset ack so the next worker will block until the UI signals."""
    _ui_ack.clear()


def wait_for_ui_ack(timeout: float = 60.0) -> bool:
    """Block the worker thread until main-thread cleanup calls ``signal_ui_ack``."""
    from ofscraper.gui.utils.crash_diagnostics import breadcrumb

    breadcrumb("worker_wait_ack_start")
    ok = _ui_ack.wait(timeout=max(1.0, float(timeout)))
    breadcrumb("worker_wait_ack_done", f"acked={int(bool(ok))}")
    return bool(ok)


def signal_ui_ack() -> None:
    """Allow a waiting model-fetch worker to exit its QRunnable."""
    from ofscraper.gui.utils.crash_diagnostics import breadcrumb

    _ui_ack.set()
    try:
        breadcrumb("ui_ack_signaled")
    except Exception:
        pass


def _to_plain_dicts(raw: Any) -> list[dict]:
    """Convert Model/dict API results to plain dicts (safe to cross threads)."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        items = list(raw.values())
    else:
        try:
            items = list(raw)
        except TypeError:
            items = [raw]

    out: list[dict] = []
    for item in items:
        if item is None:
            continue
        try:
            if isinstance(item, dict):
                d = dict(item)
            else:
                try:
                    if getattr(item, "name", None) == _SKIPPED_NAME:
                        continue
                except Exception:
                    continue
                inner = getattr(item, "model", None)
                if not isinstance(inner, dict):
                    continue
                d = dict(inner)
            if not d.get("username") and d.get("name"):
                d["username"] = d["name"]
            if not d.get("username"):
                continue
            out.append(d)
        except Exception:
            continue
    return out


def dicts_to_models(dicts: Any) -> list:
    """Build Model objects on the Qt main thread only."""
    import ofscraper.classes.of.models as models_cls

    Model = models_cls.Model
    if not isinstance(Model, type):
        # Environment still patched — use saved class if available.
        Model = _RealModel if isinstance(_RealModel, type) else None
    if Model is None:
        return []

    out = []
    for d in dicts or []:
        if not isinstance(d, dict):
            continue
        try:
            out.append(Model(d))
        except Exception as e:
            log.debug(f"[GUI model fetch] UI Model build failed: {e}")
    return out


def _run_coro(coro, timeout: float):
    """Run *coro* on a fresh event loop with a hard timeout.

    On Windows, prefer ``SelectorEventLoop`` over the default Proactor/IOCP
    loop — Proactor teardown from a QThreadPool worker has hard-crashed Qt's
    event loop (access violation after worker_done, before ui_poll_done).
    """
    import sys
    from ofscraper.gui.utils.crash_diagnostics import breadcrumb

    breadcrumb("loop_create_start", f"platform={sys.platform}")
    if sys.platform == "win32":
        # Avoid asyncio.windows_events.ProactorEventLoop (IOCP) under Qt.
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        breadcrumb("loop_run_start")
        return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
    finally:
        breadcrumb("loop_cleanup_start")
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        try:
            # Python 3.9+
            shutdown_exec = getattr(loop, "shutdown_default_executor", None)
            if callable(shutdown_exec):
                loop.run_until_complete(shutdown_exec())
        except Exception:
            pass
        try:
            loop.close()
        except Exception as e:
            breadcrumb("loop_close_err", str(e))
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass
        breadcrumb("loop_cleanup_done")


def fetch_subscription_models(
    *,
    userlist: Optional[Iterable[str]] = None,
    timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
) -> list[dict]:
    """Fetch subscriptions; return plain dicts (not Model instances)."""
    from ofscraper.gui.utils.crash_diagnostics import breadcrumb

    ul_preview = [str(u).lower() for u in (userlist or []) if u][:5]
    breadcrumb(
        "fetch_enter",
        f"userlist={ul_preview!r} timeout={timeout_sec} thread={threading.current_thread().name}",
    )
    acquired = _FETCH_LOCK.acquire(timeout=max(5.0, float(timeout_sec) + 5.0))
    if not acquired:
        breadcrumb("fetch_lock_timeout")
        raise Exception(
            "Timed out waiting for another model-list fetch to finish. "
            "Please retry in a moment."
        )
    breadcrumb("fetch_lock_acquired")
    try:
        result = _fetch_subscription_models_locked(
            userlist=userlist, timeout_sec=timeout_sec
        )
        breadcrumb("fetch_ok", f"dicts={len(result or [])}")
        return result
    except Exception as e:
        breadcrumb("fetch_error", f"{type(e).__name__}: {e}")
        raise
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        breadcrumb("fetch_baseexception", f"{type(e).__name__}: {e}")
        raise Exception(f"Model list fetch failed unexpectedly: {e}") from e
    finally:
        try:
            _FETCH_LOCK.release()
        except Exception:
            pass
        breadcrumb("fetch_exit")


def _fetch_subscription_models_locked(
    *,
    userlist: Optional[Iterable[str]],
    timeout_sec: float,
) -> list[dict]:
    from ofscraper.gui.utils.crash_diagnostics import breadcrumb
    import ofscraper.utils.auth.utils.dict as auth_dict_mod
    import ofscraper.utils.paths.common as common_paths

    try:
        auth_path = common_paths.get_auth_file()
        auth_data = auth_dict_mod.get_auth_dict()
        filled = {k: ("set" if v else "EMPTY") for k, v in (auth_data or {}).items()}
        breadcrumb("auth_ok", f"path={auth_path} fields={filled}")
        required = ["sess", "auth_id", "user_agent", "x-bc"]
        missing = [k for k in required if not (auth_data or {}).get(k)]
        if missing:
            raise Exception(
                f"Auth fields not configured: {', '.join(missing)}. "
                "Please fill in your auth credentials first."
            )
    except Exception as e:
        breadcrumb("auth_fail", str(e))
        raise

    ul = [str(u).lower() for u in (userlist or []) if u]
    timeout = float(timeout_sec) if timeout_sec and timeout_sec > 0 else _DEFAULT_TIMEOUT_SEC

    breadcrumb("api_phase_enter", f"mode={'userlist' if ul else 'all_subs'}")
    try:
        if ul:
            import ofscraper.data.api.subscriptions.lists as _lists_mod

            async def _do_fetch_list():
                breadcrumb("api_userlist_start")
                raw = _lists_mod.get_otherlist()
                if asyncio.iscoroutine(raw):
                    raw = await raw
                breadcrumb("api_userlist_done", f"raw={len(raw or [])}")
                return list(raw or [])

            breadcrumb("coro_run_start", f"timeout={timeout}")
            data = _run_coro(_do_fetch_list(), timeout)
            breadcrumb("coro_run_done", f"raw={len(data or [])}")
        else:
            import ofscraper.data.models.utils.retriver as retriver

            async def _do_fetch_all():
                breadcrumb("api_get_models_start")
                out = await retriver.get_models()
                breadcrumb("api_get_models_done", f"raw={len(out or [])}")
                return out

            breadcrumb("coro_run_start", f"timeout={timeout}")
            data = _run_coro(_do_fetch_all(), timeout)
            breadcrumb("coro_run_done", f"raw={len(data or [])}")
    except asyncio.TimeoutError as e:
        breadcrumb("api_timeout", f"after={int(timeout)}s")
        raise Exception(
            f"Model list fetch timed out after {int(timeout)}s. "
            "Check your network / Dynamic Mode and retry."
        ) from e
    except Exception as e:
        msg = str(e).strip() or e.__class__.__name__
        breadcrumb("api_error", f"{type(e).__name__}: {msg}")
        raise Exception(f"Model list fetch failed: {msg}") from e

    breadcrumb("to_dicts_start")
    out = _to_plain_dicts(data)
    # Drop references to Model instances as soon as possible on the worker.
    try:
        del data
    except Exception:
        pass
    breadcrumb("to_dicts_done", f"count={len(out)}")
    return out
