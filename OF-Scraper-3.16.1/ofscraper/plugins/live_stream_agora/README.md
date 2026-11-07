# Live Stream Agora — DEPRECATED

Native `agora_python_server_sdk` joins against OnlyFans are a **dead end**:

- AccessToken2 claims (app id / channel / uid) match join args
- SDK 2.4.9 initializes and connects
- OF still returns `CONNECTION_CHANGED_REJECTED_BY_SERVER` (reason **10**)

**Use [Live Stream Monitor](../live_stream_monitor/) instead** (Playwright MediaRecorder). Useful UX from this experiment was merged into Monitor **v1.3.0**:

- Per-row / selected / all **Stop** without disabling the poller  
- Resizable table columns  
- Capture selected  
- Capture cooldown  
- **Fetch live API dump** (OF `/streams/active/url` + token claim inspect)

This folder is kept only as a historical reference. Prefer `plugin_enabled = 0`.
