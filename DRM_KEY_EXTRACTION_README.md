# DRM Key Extraction Script (`test.py`)

Automates Widevine L3 key extraction using an Android emulator, Frida, and KeyDive. Produces a `client_id.bin` and `private_key.pem` that can be loaded directly into OF-Scraper's CDM configuration.

> **Tested on:** Windows 10/11 and Debian-based Linux (KDE Neon, PikaOS, Ubuntu). macOS is **not** supported.

---

## How It Works

1. **Download & configure the Android SDK** — Downloads `cmdline-tools` for the current platform, accepts licenses, and installs the Android 29 (`google_apis;x86_64`) system image.
2. **Ensure Java is available** — Checks `PATH` for a `java` binary. If missing, automatically downloads Adoptium Temurin JDK 17 and activates it for the session.
3. **Create an AVD** — Creates a virtual device named `WV_Extractor` (or validates the existing one matches the required ABI). Allocates a user-data partition sized to available free disk space (capped at 2 047 MB on Windows, 7 372 MB on Linux).
4. **Pre-flight acceleration check** *(Windows only)* — Runs `emulator -accel-check`. If hardware virtualization (VT-x / AEHD / WHPX / HAXM) is not available:
   - Prints actionable BIOS instructions if the CPU supports VT-x but it is disabled.
   - Falls back to x86 (32-bit) TCG software emulation automatically if the CPU has no virtualization extensions.
5. **Launch the emulator** — Starts the AVD with the correct acceleration and GPU flags for the platform. On Windows TCG (no hypervisor), `-gpu off` is used to avoid gfxstream hangs.
6. **Wait for full boot** — Polls `sys.boot_completed` and monitors the emulator log for stalls (exits with an error if the log stops growing for 45 s).
7. **Install Frida server** — Downloads and pushes the matching `frida-server` binary (ABI-aware: x86_64 or x86), then starts it as root.
8. **Install & launch KeyDive + Kaltura** — Installs KeyDive and the Kaltura APK, launches KeyDive's hook against the Widevine HAL, then automates the Kaltura app UI (FAB tap → video player → TEST DRM button) using UIAutomator with a blind-tap coordinate fallback scaled to the actual screen resolution.
9. **Extract and save keys** — Reads the keys written by KeyDive and saves them to the output directory as `client_id.bin` and `private_key.pem`.

---

## System Requirements

| Component | Minimum |
|-----------|---------|
| OS | Windows 10/11 or Debian-based Linux (Ubuntu 20.04+, KDE Neon, PikaOS) |
| CPU | x86-64 processor |
| RAM | 8 GB (16 GB recommended) |
| Free disk | 8 GB (SDK + AVD + Kaltura APK) |
| Hardware virtualization | Strongly recommended (VT-x enabled in BIOS). Script falls back to x86 TCG on Windows if absent — extraction still works but is significantly slower (30–60 min vs 10–15 min). |
| Internet | Required for SDK, JDK, Frida, KeyDive, and Kaltura APK downloads |

> **Linux KVM note:** On Linux without KVM (`/dev/kvm` absent or permission denied), the emulator runs in TCG software mode using `-accel off -gpu swiftshader_indirect`. Extraction works but is slow.

> **macOS:** Not supported. The Android emulator for macOS uses HVF and a different ABI stack that has not been tested.

---

## Software Prerequisites

### Required
| Software | Notes |
|----------|-------|
| Python 3.9+ | Must be on `PATH` |
| `pip` | For installing Python packages |
| `adb` (Android Debug Bridge) | Installed automatically via Android SDK `platform-tools` |
| Internet access | Downloads ~3 GB of tools and images on first run |

### Auto-installed by the script
- Android SDK `cmdline-tools` (latest)
- Android SDK `platform-tools`
- Android system image `system-images;android-29;google_apis;x86_64` (or `x86` fallback on Windows TCG)
- Adoptium Temurin JDK 17 (if `java` is not on PATH)
- Frida server (matching version of the installed `frida` Python package)
- KeyDive 3.0.0 (`keydive.apk` + Python wheel)
- Kaltura Android app APK

### Python packages (install before first run)
```
pip install frida frida-tools requests
```

---

## Usage

```
python test.py [OPTIONS]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir PATH` | `./keys` | Directory where `client_id.bin` and `private_key.pem` are saved |
| `--sdk-dir PATH` | `~/.android_sdk_auto` | Root directory for the Android SDK installation |
| `--work-dir PATH` | `~/.wv_extractor_work` | Working directory for downloaded files and temp data |
| `--avd-name NAME` | `WV_Extractor` | Name of the Android Virtual Device to create/reuse |
| `--keep-avd` | *(flag)* | Do not delete the AVD after extraction (speeds up subsequent runs) |
| `--no-accel-check` | *(flag)* | Skip the pre-flight `emulator -accel-check` (Windows only) |

### Example

```bash
# Basic run — saves keys to ./keys/
python test.py

# Save to a specific folder and keep the AVD for next time
python test.py --output-dir ~/drm_keys --keep-avd
```

---

## Output Files

After a successful run the output directory will contain:

| File | Description |
|------|-------------|
| `client_id.bin` | Widevine client identification blob |
| `private_key.pem` | Widevine device private key |

These paths can be entered directly into OF-Scraper's Configuration → CDM tab (`Client ID` and `Private Key` fields) with **Key Mode** set to **manual**.

---

## Platform-Specific Notes

### Windows
- The script caps the AVD user-data partition at **2 047 MB** (emulator hard limit on Windows).
- If VT-x is not enabled in BIOS, the script prints instructions and falls back to x86 TCG emulation. Expect a 30–60 minute first-run time.
- Java is downloaded automatically if not found on PATH.
- AEHD (Android Emulator Hypervisor Driver) is supported and preferred over HAXM/WHPX on Windows 10/11.

### Linux (KDE Neon / PikaOS / Ubuntu)
- KVM acceleration is used automatically if `/dev/kvm` is accessible. Add your user to the `kvm` group if needed: `sudo usermod -aG kvm $USER` (re-login required).
- If KVM is unavailable, TCG software emulation is used with `-gpu swiftshader_indirect`.
- Root or `sudo` is **not** required (KVM group membership is sufficient).

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `partition-size must be between 10MB and 2047MB` | Only on older versions — fixed in current script | Update to the latest `test.py` |
| `JAVA_HOME is not set` | Only on older versions — fixed in current script | Update to the latest `test.py` |
| `emulator -accel-check` passes but emulator hangs | GPU backend issue on TCG | Script sets `-gpu off` on Windows TCG automatically |
| `KeyDive failed to attach hook within 15 minutes` | APK install took too long or Widevine HAL not found | Wait for a full cold-start then re-run with `--keep-avd` |
| `device offline` after `adb root` | Normal transient state — script auto-waits up to 60 s | No action needed; update script if not retrying |
| `Virtualization extension is not supported` on Linux | Script incorrectly triggered x86 fallback | Only occurs on older versions; update to latest `test.py` |
| Emulator log stalls for 45 s | Emulator hung (common on underpowered TCG) | Free RAM, close other applications, re-run |
| `frida.ServerNotStartingError` | ADB root failed or frida-server ABI mismatch | Re-run; script re-downloads matching binary automatically |
| ANR "System UI isn't responding" dialog | Occurs on slow TCG emulators | Script auto-dismisses ANR dialogs — no action needed |

---

## First-Run Time Estimates

| Platform | Condition | Estimated Time |
|----------|-----------|---------------|
| Windows | AEHD / VT-x enabled | 10–20 min |
| Windows | TCG (no VT-x) | 45–90 min |
| Linux | KVM available | 8–15 min |
| Linux | TCG (no KVM) | 30–60 min |

Subsequent runs with `--keep-avd` are significantly faster (skip AVD creation and APK install).
