"""
llm_engine.py — Local GGUF LLM for intent parsing via llama-cpp-python.

Uses pre-quantized GGUF models downloaded from HuggingFace for fast CPU
inference.  No PyTorch or transformers required.
"""

import json
import logging
import os
import re
import threading

log = logging.getLogger("ofscraper_plugin.llm_assistant.engine")

# ---------------------------------------------------------------------------
# Available GGUF models
# ---------------------------------------------------------------------------

AVAILABLE_MODELS = [
    {
        "id":       "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "filename": "qwen2.5-0.5b-instruct-q8_0.gguf",
        "display":  "Qwen2.5 0.5B  Q8_0  (~530 MB RAM) — fastest",
        "desc":     "Fast on CPU. Good for simple commands. Downloads ~530 MB.",
        "size_mb":  530,
        "ram_gb":   0.7,
    },
    {
        "id":       "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "display":  "Qwen2.5 1.5B  Q4_K_M  (~1.1 GB RAM) — recommended",
        "desc":     "Recommended. Better accuracy, still fast on CPU. Downloads ~1.1 GB.",
        "size_mb":  1100,
        "ram_gb":   1.3,
    },
    {
        "id":       "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "display":  "Qwen2.5 3B  Q4_K_M  (~2.0 GB RAM) — best quality",
        "desc":     "Most accurate. Needs ~2+ GB free RAM. Downloads ~2.0 GB.",
        "size_mb":  2000,
        "ram_gb":   2.3,
    },
]

_DEFAULT_MODEL = AVAILABLE_MODELS[1]  # 1.5B recommended

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a GUI assistant for OF-Scraper. Output ONLY compact JSON — no prose, no whitespace.

STATE: {state}

TOOLS: {tools}

FORMAT: {{"tool_calls":[{{"name":"TOOL","args":{{}}}}],"message":"ok"}}

RULES:
- username: take from "from NAME" / "for NAME" → usernames:["NAME"]
- "all content" / "everything" = areas:["all"], NOT usernames:["ALL"]
- usernames:["ALL"] only when user says "everyone" / "all users"
- Areas: Timeline Messages Pinned Archived Stories Highlights Purchased Profile Streams
- "scrape"/"download"/"start"/"go"/"run" → ALWAYS include start_scraping as last tool call
- Output compact JSON only, no newlines, no spaces between tokens.
"""

_TOOLS_SCHEMA = """\
set_action {"action":"download"|"like"|"unlike"|"download_like"}
set_usernames {"usernames":["name"]} ["ALL"]=everyone
set_areas {"areas":["Timeline",...]} ["all"]=every area
set_media_types {"types":["Images","Videos","Audios"]}
set_price_filter {"filter":"free"|"paid"|"all"}
set_daemon {"enabled":true,"interval_minutes":60}
set_date_filter {"after":"YYYY-MM-DD","before":"YYYY-MM-DD"}
navigate_to {"section":"scraper"|"auth"|"config"|"profiles"|"merge"|"help"}
reset_settings {}
start_scraping {}\
"""

_VALID_TOOLS = {
    "set_action", "set_usernames", "set_areas", "set_media_types",
    "set_price_filter", "set_daemon", "set_date_filter",
    "navigate_to", "reset_settings", "start_scraping",
}


class LLMEngine:
    """
    Wraps a GGUF model loaded via llama-cpp-python.
    All heavy operations run synchronously — call from a QThread.
    """

    def __init__(self, model_id: str | None = None, filename: str | None = None):
        spec = next(
            (m for m in AVAILABLE_MODELS if m["id"] == model_id),
            _DEFAULT_MODEL,
        )
        self.model_id = model_id or spec["id"]
        self.filename = filename or spec["filename"]
        self.llm      = None
        self._loaded  = False
        self._lock    = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    # System helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _available_ram_gb() -> float:
        """Return available system RAM in GB, or -1 if unknown."""
        try:
            import psutil
            return psutil.virtual_memory().available / 1e9
        except ImportError:
            pass
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) / 1_000_000
        except Exception:
            pass
        try:
            import ctypes
            class _MEMSTATUS(ctypes.Structure):
                _fields_ = [
                    ("dwLength",        ctypes.c_ulong),
                    ("dwMemoryLoad",    ctypes.c_ulong),
                    ("ullTotalPhys",    ctypes.c_ulonglong),
                    ("ullAvailPhys",    ctypes.c_ulonglong),
                    ("ullTotalPageFile",ctypes.c_ulonglong),
                    ("ullAvailPageFile",ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtVirtual", ctypes.c_ulonglong),
                ]
            s = _MEMSTATUS()
            s.dwLength = ctypes.sizeof(s)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
            return s.ullAvailPhys / 1e9
        except Exception:
            pass
        return -1.0

    @staticmethod
    def _make_progress_tqdm(progress_callback):
        """Return a tqdm subclass that forwards per-file download progress."""
        if not progress_callback:
            return None
        try:
            from tqdm import tqdm as _Base

            class _HFProgressTqdm(_Base):
                def __init__(self, *args, **kwargs):
                    # huggingface_hub XET storage passes name='huggingface_hub.xet_get'
                    # which tqdm doesn't accept — strip it silently.
                    kwargs.pop("name", None)
                    super().__init__(*args, **kwargs)

                def update(self, n=1):
                    result = super().update(n)
                    try:
                        if self.total and self.n is not None:
                            done_mb  = self.n     / 1_000_000
                            total_mb = self.total / 1_000_000
                            pct      = int(self.n / self.total * 100)
                            fname    = (self.desc or "file").split("/")[-1]
                            progress_callback(
                                f"↓ {fname}  {done_mb:.0f} / {total_mb:.0f} MB  ({pct}%)"
                            )
                    except Exception:
                        pass
                    return result

            return _HFProgressTqdm
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self, progress_callback=None):
        """Download (if needed) + load the GGUF model. Blocking — run from a worker thread."""
        with self._lock:
            if self._loaded:
                return
            try:
                from llama_cpp import Llama
                from huggingface_hub import hf_hub_download, snapshot_download

                # ── RAM check ────────────────────────────────────────────
                spec     = next((m for m in AVAILABLE_MODELS if m["id"] == self.model_id), None)
                need_gb  = spec["ram_gb"] if spec else 1.3
                avail    = self._available_ram_gb()
                if avail > 0 and progress_callback:
                    if avail < need_gb:
                        progress_callback(
                            f"⚠  Low RAM: {avail:.1f} GB available, "
                            f"~{need_gb:.1f} GB needed. "
                            "Consider closing other applications."
                        )
                    else:
                        progress_callback(
                            f"RAM OK: {avail:.1f} GB available (~{need_gb:.1f} GB needed)."
                        )

                # ── Download GGUF file ────────────────────────────────────
                # hf_hub_download fetches the single file and returns its
                # local path.  We pass our custom tqdm so the dialog shows
                # live progress.  Fall back silently if the version of
                # huggingface_hub doesn't support tqdm_class.
                if progress_callback:
                    progress_callback(
                        f"Downloading {self.filename}…\n"
                        "(HuggingFace may throttle unauthenticated downloads — "
                        "set HF_TOKEN env var for full speed)"
                    )

                tqdm_cls = self._make_progress_tqdm(progress_callback)
                try:
                    model_path = hf_hub_download(
                        repo_id=self.model_id,
                        filename=self.filename,
                        tqdm_class=tqdm_cls,
                    )
                except Exception:
                    # Older huggingface_hub doesn't support tqdm_class, or
                    # XET storage raises a non-TypeError — retry without it.
                    model_path = hf_hub_download(
                        repo_id=self.model_id,
                        filename=self.filename,
                    )

                # ── Load into llama.cpp ───────────────────────────────────
                if progress_callback:
                    progress_callback(f"Loading {self.filename} into memory…")

                n_threads = min(os.cpu_count() or 4, 8)
                self.llm  = Llama(
                    model_path=model_path,
                    n_ctx=1024,
                    n_threads=n_threads,
                    n_gpu_layers=0,
                    verbose=False,
                )

                self._loaded = True
                if progress_callback:
                    progress_callback("Model ready.")
                log.info("GGUF model loaded: %s / %s", self.model_id, self.filename)

            except Exception as e:
                log.error("LLM load failed: %s", e)
                self.llm = None
                raise

    def unload(self):
        """Release model from memory."""
        with self._lock:
            try:
                del self.llm
            except Exception:
                pass
            self.llm     = None
            self._loaded = False
        log.info("LLM unloaded")

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def generate(
        self,
        gui_state: dict,
        user_message: str,
        max_new_tokens: int = 300,
        stream_callback=None,
    ) -> str:
        """Run inference and return raw model text."""
        if not self._loaded:
            raise RuntimeError("Model not loaded — call load() first")

        avail = self._available_ram_gb()
        if avail > 0 and avail < 0.5:
            raise RuntimeError(
                f"Not enough RAM for inference ({avail:.1f} GB free). "
                "Close other applications."
            )

        state_lines = [
            f"- Action: {gui_state.get('action', 'download')}",
            f"- Target users: {', '.join(gui_state.get('usernames', ['(none)'])) or '(none)'}",
            f"- Content areas: {', '.join(gui_state.get('areas', ['(none)'])) or '(none)'}",
            f"- Media types: {', '.join(gui_state.get('media_types', ['Images', 'Videos']))}",
            f"- Price filter: {gui_state.get('price_filter', 'all')}",
            (
                f"- Daemon: ON ({gui_state.get('daemon_interval', 30)} min)"
                if gui_state.get("daemon")
                else "- Daemon: OFF"
            ),
        ]

        system_prompt = _SYSTEM_PROMPT.format(
            state="\n".join(state_lines),
            tools=_TOOLS_SCHEMA,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ]

        if stream_callback:
            stream = self.llm.create_chat_completion(
                messages=messages,
                max_tokens=max_new_tokens,
                temperature=0.0,
                stream=True,
            )
            parts: list[str] = []
            for chunk in stream:
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    parts.append(delta)
                    stream_callback("".join(parts))
            return "".join(parts).strip()

        response = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=max_new_tokens,
            temperature=0.0,
        )
        return response["choices"][0]["message"]["content"].strip()

    # ------------------------------------------------------------------
    # Response parsing (static — usable without a loaded model)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_xml_shorthand(raw_text: str) -> tuple[list[dict], str]:
        """
        Strategy 3: smaller models often output compact XML shorthand, e.g.
            <set_action>download</set_action>
            <set_areas>Purchased</set_areas>
        Convert each recognised tag into a proper tool-call dict.
        """
        def _split(v: str) -> list[str]:
            return [x.strip().strip("\"'") for x in re.split(r"[,;|]", v) if x.strip()]

        builders: dict = {
            "set_action":       lambda v: {"action": v.strip().strip("\"'")},
            "set_usernames":    lambda v: {"usernames": _split(v)},
            "set_areas":        lambda v: {"areas": _split(v)},
            "set_media_types":  lambda v: {"types": _split(v)},
            "set_price_filter": lambda v: {"filter": v.strip().strip("\"'")},
            "set_daemon":       lambda v: {
                "enabled": v.strip().lower() in ("true", "1", "on", "yes", "enabled"),
            },
            "navigate_to":      lambda v: {"section": v.strip().strip("\"'")},
            "reset_settings":   lambda v: {},
            "start_scraping":   lambda v: {},
            "set_date_filter":  lambda v: {"after": None, "before": None},
        }

        matches    = re.findall(r"<(\w+)>(.*?)</\1>", raw_text, re.DOTALL)
        tool_calls = []
        for tag, value in matches:
            if tag in _VALID_TOOLS and tag in builders:
                try:
                    tool_calls.append({"name": tag, "args": builders[tag](value)})
                except Exception:
                    pass

        message = re.sub(r"<\w+>.*?</\w+>", "", raw_text, flags=re.DOTALL).strip()
        if not message:
            message = raw_text
        return tool_calls, message

    @staticmethod
    def parse_tool_calls(raw_text: str) -> tuple[list[dict], str]:
        """
        Extract (tool_calls, assistant_message) from raw LLM output.

        Tries four strategies in order:
        0. {"tool_calls":[...], "message":"..."} JSON object
        1. <tools>[JSON array]</tools>
        2. Bare JSON array anywhere in the text
        3. XML shorthand <tool_name>value</tool_name>
        4. Plain-text fallback
        """
        tool_calls: list[dict] = []
        message: str = raw_text

        # ── Strategy 0: JSON object with tool_calls key ───────────────────
        obj_m = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if obj_m:
            try:
                obj = json.loads(obj_m.group(0))
                if isinstance(obj, dict) and "tool_calls" in obj:
                    tcs = obj["tool_calls"] if isinstance(obj["tool_calls"], list) else []
                    msg = obj.get("message", "")
                    if tcs or msg:
                        tcs = [
                            tc for tc in tcs
                            if isinstance(tc, dict) and tc.get("name") in _VALID_TOOLS
                        ]
                        for tc in tcs:
                            if "args" not in tc:
                                tc["args"] = {}
                        log.debug(
                            "parse_tool_calls (S0): %d tool(s) — %s",
                            len(tcs), [tc["name"] for tc in tcs],
                        )
                        return tcs, msg or raw_text
            except Exception:
                pass

        # ── Strategy 1: <tools>[JSON array]</tools> ──────────────────────
        tags_m = re.search(r"<tools>(.*?)</tools>", raw_text, re.DOTALL)
        msg_m  = re.search(r"<message>(.*?)</message>", raw_text, re.DOTALL)

        if tags_m:
            try:
                parsed     = json.loads(tags_m.group(1).strip())
                tool_calls = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                tool_calls = []
            message = (
                msg_m.group(1).strip()
                if msg_m
                else (raw_text[: tags_m.start()] + raw_text[tags_m.end():]).strip() or ""
            )
        else:
            # ── Strategy 2: bare JSON array ──────────────────────────────
            json_m = re.search(r"\[.*?\]", raw_text, re.DOTALL)
            if json_m:
                try:
                    parsed = json.loads(json_m.group(0))
                    if isinstance(parsed, list) and all(isinstance(x, dict) for x in parsed):
                        tool_calls = parsed
                        before  = raw_text[: json_m.start()].strip()
                        after   = raw_text[json_m.end():].strip()
                        message = after or before or raw_text
                except Exception:
                    pass

            # ── Strategy 3: XML shorthand ─────────────────────────────────
            if not tool_calls:
                tool_calls, message = LLMEngine._parse_xml_shorthand(raw_text)

            # ── Strategy 4: partial JSON recovery ─────────────────────
            # If the output was truncated mid-stream, try extracting every
            # complete {"name":"...","args":{...}} object individually.
            if not tool_calls:
                for m in re.finditer(r'\{"name"\s*:\s*"(\w+)"\s*,\s*"args"\s*:\s*(\{[^}]*\}|\{\})', raw_text):
                    name = m.group(1)
                    if name in _VALID_TOOLS:
                        try:
                            args = json.loads(m.group(2))
                        except Exception:
                            args = {}
                        tool_calls.append({"name": name, "args": args})

        # ── Validate and normalise ────────────────────────────────────────
        tool_calls = [
            tc for tc in tool_calls
            if isinstance(tc, dict) and tc.get("name") in _VALID_TOOLS
        ]
        for tc in tool_calls:
            if "args" not in tc:
                tc["args"] = {}

        if not message:
            message = raw_text

        log.debug(
            "parse_tool_calls: %d tool(s) — %s",
            len(tool_calls), [tc["name"] for tc in tool_calls],
        )
        return tool_calls, message
