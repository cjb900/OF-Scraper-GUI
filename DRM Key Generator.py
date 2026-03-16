#!/usr/bin/env python3
"""
Widevine L3 Extraction CLI Tool - Universal OS Edition
Uses Android SDK emulator directly (no Docker required).
Supports Linux, macOS, and Windows.
"""

import platform, subprocess, sys, os, time, requests, lzma, shutil, re, argparse, zipfile, tarfile, threading
import xml.etree.ElementTree as ET

SYSTEM_IMAGE = "system-images;android-29;google_apis;x86_64"
AVD_NAME     = "widevine_avd"


class WidevineMasterAutomator:
    def __init__(self, out_dir, skip_emulator):
        self.os_type       = platform.system()
        self.home_dir      = os.path.expanduser("~")
        self.out_dir       = out_dir
        self.skip_emulator = skip_emulator

        # All SDK + work files live here
        self.sdk_dir  = os.path.join(self.home_dir, "widevine-sdk")
        self.work_dir = os.path.join(self.home_dir, "widevine-work")

        # OS-specific binary extensions
        ext = ".exe" if self.os_type == "Windows" else ""
        bat = ".bat" if self.os_type == "Windows" else ""
        tools_bin = os.path.join(self.sdk_dir, "cmdline-tools", "latest", "bin")

        self.sdkmanager  = os.path.join(tools_bin, f"sdkmanager{bat}")
        self.avdmanager  = os.path.join(tools_bin, f"avdmanager{bat}")
        self.emulator_bin = os.path.join(self.sdk_dir, "emulator", f"emulator{ext}")
        self.adb          = os.path.join(self.sdk_dir, "platform-tools", f"adb{ext}")

        # KeyDive venv
        self.venv_dir = os.path.join(self.work_dir, "venv")
        if self.os_type == "Windows":
            self.venv_python  = os.path.join(self.venv_dir, "Scripts", "python.exe")
            self.venv_keydive = os.path.join(self.venv_dir, "Scripts", "keydive.exe")
        else:
            self.venv_python  = os.path.join(self.venv_dir, "bin", "python")
            self.venv_keydive = os.path.join(self.venv_dir, "bin", "keydive")

        self.avd_name     = AVD_NAME
        self.abi          = "x86_64"          # may be downgraded to "x86" at runtime
        self.system_image = SYSTEM_IMAGE
        self.target       = "localhost:5555"

    # ── Helpers ──────────────────────────────────────────────────────────────

    def run_cmd(self, cmd, check=True, capture=False, env=None):
        print(f"🔄 {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        result = subprocess.run(cmd, capture_output=capture, text=True, env=env)
        if check and result.returncode != 0:
            print(f"❌ Command failed: {cmd}")
            if capture:
                print(result.stderr[:500])
            sys.exit(1)
        return result

    def run_adb(self, args, check=True, capture=False):
        return subprocess.run(
            [self.adb, "-s", self.target] + args,
            capture_output=capture, text=True,
        )

    def _sdk_env(self):
        env = os.environ.copy()
        env["ANDROID_SDK_ROOT"] = self.sdk_dir
        env["ANDROID_HOME"]     = self.sdk_dir
        env["ANDROID_AVD_HOME"] = os.path.join(self.home_dir, ".android", "avd")
        # Inject portable JDK if we downloaded one (needed by sdkmanager on Linux/macOS)
        jdk_dir = os.path.join(self.sdk_dir, "jdk")
        if os.path.isdir(jdk_dir):
            env["JAVA_HOME"] = jdk_dir
            env["PATH"] = os.path.join(jdk_dir, "bin") + os.pathsep + env.get("PATH", "")
        return env

    def get_view_center(self, target_text_or_id):
        try:
            self.run_adb(["shell", "uiautomator", "dump", "/data/local/tmp/ui.xml"])
            xml_data = self.run_adb(["shell", "cat", "/data/local/tmp/ui.xml"], capture=True).stdout
            if not xml_data or "xml" not in xml_data:
                return None
            root = ET.fromstring(xml_data)
            for node in root.iter("node"):
                text   = node.attrib.get("text", "").upper()
                res_id = node.attrib.get("resource-id", "")
                if target_text_or_id.upper() in text or target_text_or_id in res_id:
                    nums = re.findall(r"\d+", node.attrib.get("bounds", ""))
                    if len(nums) == 4:
                        return ((int(nums[0]) + int(nums[2])) // 2,
                                (int(nums[1]) + int(nums[3])) // 2)
        except Exception:
            pass
        return None

    # ── KeyDive setup ─────────────────────────────────────────────────────────

    def setup_keydive(self):
        print("\n🛠️  Verifying KeyDive Virtual Environment...")
        os.makedirs(self.work_dir, exist_ok=True)
        if not os.path.exists(self.venv_dir):
            print("📦 Creating isolated Python virtual environment...")
            self.run_cmd([sys.executable, "-m", "venv", self.venv_dir])
        if not os.path.exists(self.venv_keydive):
            print("📦 Installing pinned KeyDive (3.0.0) into venv...")
            self.run_cmd([self.venv_python, "-m", "pip", "install", "keydive==3.0.0"])
        else:
            print("✅ KeyDive is already installed in the venv.")

    # ── Java (required by sdkmanager on all platforms) ────────────────────────

    def _ensure_java(self):
        """Ensure Java 17 is available. Download a portable JDK if absent."""
        # Already on PATH?
        if shutil.which("java"):
            return

        # Already downloaded into our SDK dir?
        jdk_dir  = os.path.join(self.sdk_dir, "jdk")
        java_bin = os.path.join(jdk_dir, "bin",
                                "java.exe" if self.os_type == "Windows" else "java")
        if os.path.exists(java_bin):
            self._activate_jdk(jdk_dir)
            return

        print("📦 Java not found — downloading portable JDK 17 (Adoptium Temurin)...")
        os.makedirs(self.sdk_dir, exist_ok=True)
        os_key  = {"Darwin": "mac", "Linux": "linux", "Windows": "windows"}.get(
                      self.os_type, "linux")
        arch    = "x64"
        api_url = (
            f"https://api.adoptium.net/v3/assets/latest/17/hotspot"
            f"?os={os_key}&arch={arch}&image_type=jdk"
        )
        info     = requests.get(api_url, timeout=15).json()[0]["binary"]["package"]
        dl_url   = info["link"]
        filename = info["name"]

        archive = os.path.join(self.sdk_dir, filename)
        with requests.get(dl_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            total, done = int(r.headers.get("content-length", 0)), 0
            with open(archive, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r   {min(done * 100 // total, 100)}%", end="", flush=True)
        print()

        tmp = os.path.join(self.sdk_dir, "_jdk_tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        if filename.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(tmp)
        else:
            with tarfile.open(archive) as tf:
                tf.extractall(tmp, filter="data")

        # The archive contains one top-level folder (e.g. jdk-17.0.x+y)
        subdirs = [d for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d))]
        src = os.path.join(tmp, subdirs[0])
        # macOS Adoptium JDK has an extra Contents/Home layer
        if self.os_type == "Darwin":
            mac_home = os.path.join(src, "Contents", "Home")
            if os.path.isdir(mac_home):
                src = mac_home
        shutil.rmtree(jdk_dir, ignore_errors=True)
        shutil.move(src, jdk_dir)
        shutil.rmtree(tmp)
        os.remove(archive)
        print("✅ JDK 17 installed.")
        self._activate_jdk(jdk_dir)

    def _activate_jdk(self, jdk_dir):
        """Point the current process (and child processes) at the portable JDK."""
        os.environ["JAVA_HOME"] = jdk_dir
        os.environ["PATH"] = (
            os.path.join(jdk_dir, "bin") + os.pathsep + os.environ.get("PATH", "")
        )

    # ── Android SDK setup ─────────────────────────────────────────────────────

    def _get_cmdline_tools_url(self):
        os_map = {"Windows": "win", "Darwin": "mac", "Linux": "linux"}
        os_key = os_map.get(self.os_type, "linux")
        try:
            r = requests.get(
                "https://dl.google.com/android/repository/repository2-3.xml", timeout=10
            )
            root = ET.fromstring(r.content)
            os_full = {"win": "windows", "mac": "macosx", "linux": "linux"}[os_key]
            # Collect all cmdline-tools versions and pick the highest revision
            best_rev = -1
            best_url = None
            for pkg in root.iter("remotePackage"):
                if not pkg.get("path", "").startswith("cmdline-tools;"):
                    continue
                rev_el = pkg.find(".//revision/major")
                rev = int(rev_el.text) if rev_el is not None else 0
                if rev <= best_rev:
                    continue
                for archive in pkg.iter("archive"):
                    host_os = archive.find(".//host-os")
                    if host_os is not None and host_os.text == os_full:
                        url_el = archive.find(".//complete/url")
                        if url_el is not None:
                            best_rev = rev
                            best_url = (
                                "https://dl.google.com/android/repository/"
                                + url_el.text
                            )
            if best_url:
                return best_url
        except Exception:
            pass
        # Fallback: cmdline-tools 12.0 (build 11076708) — known-good recent version
        return (
            f"https://dl.google.com/android/repository/"
            f"commandlinetools-{os_key}-11076708_latest.zip"
        )

    def _accept_sdk_licenses(self):
        licenses_dir = os.path.join(self.sdk_dir, "licenses")
        os.makedirs(licenses_dir, exist_ok=True)
        licenses = {
            "android-sdk-license": (
                "\n8933bad161af4178b1185d1a37fbf41ea5269c55"
                "\nd56f5187479451eabf01fb78af6dfcb131a6481e"
                "\n24333f8a63b6825ea9c5514f83c2829b004d1fee"
            ),
            "android-sdk-arm-dbt-license": "\n859f317696f67ef3d7f30a50a5560e7834b43903",
            "android-sdk-preview-license": "\n84831b9409646a918e30573bab4c9c91346d8abd",
            "android-googletv-license":    "\n601085b94cd77f0b54ff86406957099ebe79c4d6",
            "google-gdk-license":          "\n33b6a2b64607f11b759f320ef9dff4ae5c47d97a",
            "intel-android-extra-license": "\nd975f751698a77b662f1254ddbeed3901e976f5a",
        }
        for name, content in licenses.items():
            path = os.path.join(licenses_dir, name)
            if not os.path.exists(path):
                with open(path, "w") as f:
                    f.write(content)

    def setup_android_sdk(self):
        print("\n🛠️  Setting up Android SDK...")
        self._ensure_java()

        # 1. Download cmdline-tools if missing
        if not os.path.exists(self.sdkmanager):
            print("📦 Downloading Android SDK cmdline-tools...")
            url = self._get_cmdline_tools_url()
            print(f"   URL: {url}")
            os.makedirs(self.sdk_dir, exist_ok=True)
            zip_path = os.path.join(self.sdk_dir, "cmdline-tools.zip")

            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                total      = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = min(downloaded * 100 // total, 100)
                            print(f"\r   {pct}%", end="", flush=True)
            print()

            # Extract and locate the folder that contains bin/sdkmanager.
            # Old zips extract to tools/, new zips extract to cmdline-tools/.
            tmp = os.path.join(self.sdk_dir, "_clt_tmp")
            if os.path.exists(tmp):
                shutil.rmtree(tmp)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp)

            # Find the subfolder that has a bin/ directory with sdkmanager inside
            sdkmgr_name = "sdkmanager.bat" if self.os_type == "Windows" else "sdkmanager"
            src_dir = None
            for entry in os.listdir(tmp):
                candidate = os.path.join(tmp, entry)
                if os.path.isdir(candidate) and os.path.exists(
                    os.path.join(candidate, "bin", sdkmgr_name)
                ):
                    src_dir = candidate
                    break
            if src_dir is None:
                print(f"❌ Could not find sdkmanager inside extracted zip. Contents: {os.listdir(tmp)}")
                sys.exit(1)

            dest = os.path.join(self.sdk_dir, "cmdline-tools", "latest")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.move(src_dir, dest)
            shutil.rmtree(tmp)
            os.remove(zip_path)
            if self.os_type != "Windows":
                for f in os.listdir(os.path.join(dest, "bin")):
                    os.chmod(os.path.join(dest, "bin", f), 0o755)
            print("✅ cmdline-tools installed.")
        else:
            print("✅ Android SDK cmdline-tools already present.")

        # 2. Pre-accept licenses
        self._accept_sdk_licenses()

        # 3. Install platform-tools, emulator, system image
        sysimg_dir = os.path.join(
            self.sdk_dir, "system-images", "android-29", "google_apis", self.abi
        )
        missing = []
        if not os.path.exists(self.adb):
            missing.append("platform-tools")
        if not os.path.exists(self.emulator_bin):
            missing.append("emulator")
        if not os.path.exists(sysimg_dir):
            missing.append(self.system_image)

        if missing:
            print(f"📦 Installing SDK components: {', '.join(missing)}")
            print("   (This may take several minutes on first run)")
            result = subprocess.run(
                [self.sdkmanager, f"--sdk_root={self.sdk_dir}"] + missing,
                input="y\n" * 20,
                text=True,
                env=self._sdk_env(),
            )
            if result.returncode != 0:
                print("❌ sdkmanager failed. Check your internet connection.")
                sys.exit(1)
        else:
            print("✅ SDK components already installed.")

        # 4. Create AVD if missing or if it was previously built for a different ABI.
        avd_home = os.path.join(self.home_dir, ".android", "avd")
        avd_ini  = os.path.join(avd_home, f"{self.avd_name}.ini")
        avd_cfg  = os.path.join(avd_home, f"{self.avd_name}.avd", "config.ini")

        def _avd_abi():
            """Read the ABI recorded in the existing AVD's config.ini."""
            try:
                with open(avd_cfg) as f:
                    for line in f:
                        if line.startswith("abi.type="):
                            return line.split("=", 1)[1].strip()
            except Exception:
                pass
            return None

        existing_abi = _avd_abi() if os.path.exists(avd_ini) else None
        need_create  = not os.path.exists(avd_ini) or existing_abi != self.abi

        if need_create:
            if existing_abi and existing_abi != self.abi:
                print(f"📦 AVD ABI mismatch ({existing_abi} → {self.abi}), recreating AVD...")
            else:
                print(f"📦 Creating AVD '{self.avd_name}'...")
            result = subprocess.run(
                [
                    self.avdmanager, "--verbose", "create", "avd",
                    "-n", self.avd_name,
                    "-k", self.system_image,
                    "--device", "pixel",
                    "--force",
                ],
                input="no\n",
                text=True,
                capture_output=True,
                env=self._sdk_env(),
            )
            if result.returncode != 0:
                print(f"❌ Failed to create AVD:\n{result.stderr[:500]}")
                sys.exit(1)
            print(f"✅ AVD '{self.avd_name}' created.")
        else:
            print(f"✅ AVD '{self.avd_name}' already exists.")

    # ── Emulator ──────────────────────────────────────────────────────────────

    def _default_accel(self):
        if self.os_type == "Windows":
            return ["-accel", "auto"]   # emulator picks WHPX/HAXM/TCG automatically
        elif self.os_type == "Linux":
            return ["-accel", "kvm"] if os.path.exists("/dev/kvm") else ["-accel", "auto"]
        else:
            return ["-accel", "hvf"]

    def _userdata_partition_mb(self):
        """Return a userdata partition size (MB) that fits the available disk space."""
        avd_parent = os.path.join(self.home_dir, ".android", "avd")
        os.makedirs(avd_parent, exist_ok=True)
        try:
            free_mb = shutil.disk_usage(avd_parent).free // (1024 * 1024)
        except Exception:
            return 4096
        # Windows emulator enforces a hard 2047 MB ceiling on -partition-size.
        # Linux/macOS support up to 7372 MB.
        max_mb = 2047 if self.os_type == "Windows" else 7372
        # Reserve 512 MB for OS headroom.
        size = min(max(free_mb - 512, 512), max_mb)
        if free_mb < 1024:
            print(f"⚠️  Only {free_mb} MB free — emulator may struggle with {size} MB userdata.")
        else:
            print(f"   Disk: {free_mb} MB free → userdata partition: {size} MB")
        return size

    def _launch_emulator_proc(self, accel):
        os.makedirs(self.work_dir, exist_ok=True)
        self.emulator_log = os.path.join(self.work_dir, "emulator.log")
        log_file = open(self.emulator_log, "w")
        # On Windows, gfxstream/swiftshader_indirect hangs during TCG (software)
        # emulation because it needs hypervisor support to init render workers.
        # Use "-gpu off" only on Windows TCG to avoid the hang.
        # On Linux/macOS, swiftshader_indirect works fine with TCG and is needed
        # for the Android DRM/HAL service to start — "-gpu off" breaks Widevine there.
        is_software = "-accel" in accel and accel[accel.index("-accel") + 1] == "off"
        gpu = ("off" if (is_software and self.os_type == "Windows")
               else "swiftshader_indirect")
        cmd = [
            self.emulator_bin,
            "-avd",   self.avd_name,
            "-port",  "5554",
            "-no-window", "-no-audio", "-no-boot-anim", "-no-snapshot",
            "-gpu",   gpu,
            "-partition-size", str(self._userdata_partition_mb()),
        ] + accel
        accel_label = " ".join(accel) if accel else "none"
        print(f"   Acceleration: {accel_label}  GPU: {gpu}")
        return subprocess.Popen(cmd, env=self._sdk_env(), stdout=log_file, stderr=log_file)

    def _check_windows_acceleration(self):
        """Run `emulator -accel-check` and abort with actionable instructions if no
        hardware virtualization is available.  Only called on Windows."""
        try:
            result = subprocess.run(
                [self.emulator_bin, "-accel-check"],
                capture_output=True, text=True, timeout=20,
                env=self._sdk_env(),
            )
            output = (result.stdout + result.stderr).lower()
        except Exception:
            return   # can't run check — let the normal launch attempt proceed

        # Success: emulator -accel-check returns 0 when any accelerator is available.
        # Different drivers report differently: WHPX says "works", AEHD/HAXM say
        # "installed and usable".  Trust the return code first; fall back to keywords.
        GOOD = ("works", "usable", "installed")
        if result.returncode == 0 or any(k in output for k in GOOD):
            return

        # Failure: no usable accelerator.
        # Use PowerShell to distinguish "CPU doesn't support VT-x" from
        # "CPU supports it but BIOS/firmware has it disabled".
        cpu_has_vt    = False
        bios_enabled  = False
        try:
            ps = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Processor | "
                 "Select-Object -First 1 "
                 "VirtualizationFirmwareEnabled,VMMonitorModeExtensions) | "
                 "ConvertTo-Json"],
                capture_output=True, text=True, timeout=10,
            )
            import json as _json
            info = _json.loads(ps.stdout)
            cpu_has_vt   = bool(info.get("VMMonitorModeExtensions", False))
            bios_enabled = bool(info.get("VirtualizationFirmwareEnabled", False))
        except Exception:
            pass

        print("\n❌ Hardware virtualization is not available on this system.")
        print("   The Android Emulator requires VT-x (Intel) or AMD-V (AMD) to run on Windows.")
        print()
        if cpu_has_vt and not bios_enabled:
            print("   ✅ Your CPU SUPPORTS virtualization, but it is DISABLED in BIOS/UEFI.")
            print()
            print("   How to fix (VT-x is disabled in BIOS):")
            print("   1. Restart your PC and enter BIOS/UEFI  (Del / F2 / F10 at boot)")
            print("   2. Find 'Intel Virtualization Technology', 'VT-x', or 'SVM Mode'")
            print("      and set it to ENABLED")
            print("   3. Save & Exit → Windows will boot normally → run this script again")
            print()
            print("   Then also ensure 'Windows Hypervisor Platform' is enabled:")
            print("   Settings → System → Optional features → More Windows features")
            print("   → check 'Windows Hypervisor Platform' → OK → Reboot")
        elif not cpu_has_vt:
            print("   ❌ Your CPU does not support hardware virtualization (VT-x / AMD-V).")
            print("   The Android Emulator cannot run on this hardware.")
            print()
            print("   Options:")
            print("   - Run this script on a different PC that supports VT-x/AMD-V")
            print("   - Copy the output files from another machine where you ran it successfully")
        else:
            # Can't determine — give generic instructions
            print("   How to fix:")
            print("   1. Restart your PC and enter BIOS/UEFI  (Del / F2 / F10 at boot)")
            print("   2. Find 'Intel Virtualization Technology' (VT-x) or 'SVM Mode' (AMD)")
            print("      and set it to ENABLED")
            print("   3. Save & Exit, boot Windows, then run this script again")
            print()
            print("   Also enable 'Windows Hypervisor Platform':")
            print("   Settings → System → Optional features → More Windows features")
            print("   → check 'Windows Hypervisor Platform' → OK → Reboot")
        print()
        print(f"   emulator -accel-check output:\n   {(result.stdout + result.stderr).strip()}")
        sys.exit(1)

    def start_emulator(self):
        if self.skip_emulator:
            print("\n⏭️  Skipping emulator start. Looking for running emulator...")
            result = subprocess.run(
                [self.adb, "devices"], capture_output=True, text=True
            )
            for line in result.stdout.splitlines():
                if "emulator" in line and "offline" not in line and "List" not in line:
                    self.target = line.split()[0]
                    print(f"🔗 Attached to existing emulator: {self.target}")
                    return
            print("   No running emulator found; defaulting to localhost:5555")
            return

        print(f"\n🚀 Starting Android emulator (headless)...")

        if self.os_type == "Windows":
            self._check_windows_acceleration()

        self._cleanup_stale_emulator()
        subprocess.run([self.adb, "start-server"], capture_output=True, text=True)

        self._emulator_proc = self._launch_emulator_proc(self._default_accel())
        self._accel_fallback_tried = False
        # target will be updated to emulator-5554 once ADB detects it
        self.target = "emulator-5554"

    # ── Boot / Frida / KeyDive ────────────────────────────────────────────────

    def _show_emulator_log(self, tail=60):
        log = getattr(self, "emulator_log", None)
        if log and os.path.exists(log):
            print("\n--- Emulator log (last lines) ---")
            with open(log) as f:
                lines = f.readlines()
            for line in lines[-tail:]:
                print(line, end="")
            print("--- End of log ---\n")

    def _cleanup_stale_emulator(self):
        """Kill any stale emulator processes and remove AVD lock files."""
        # Kill ALL emulator-related processes using PowerShell on Windows
        # (catches emulator.exe, emulator64-x86_64.exe, qemu-system-x86_64.exe, etc.)
        if self.os_type == "Windows":
            subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    "Get-Process | Where-Object {"
                    "  $_.Name -match 'emulator' -or $_.Name -match 'qemu'"
                    "} | Stop-Process -Force -ErrorAction SilentlyContinue",
                ],
                capture_output=True,
            )
        else:
            subprocess.run(["pkill", "-9", "-f", "emulator"], capture_output=True)
        time.sleep(8)   # give OS time to release file handles (Windows needs longer)

        # Kill ADB server (removes stale emulator registrations)
        subprocess.run([self.adb, "kill-server"], capture_output=True)
        time.sleep(1)

        # Remove AVD lock files.
        # On Windows the emulator may use a named mutex (not a file), but it also
        # writes hardware-qemu.ini.lock and multiinstance.lock as file sentinels.
        avd_dir = os.path.join(
            self.home_dir, ".android", "avd", f"{self.avd_name}.avd"
        )
        print(f"   AVD dir: {avd_dir}")
        if os.path.isdir(avd_dir):
            contents = os.listdir(avd_dir)
            locks = [f for f in contents if ".lock" in f or f.endswith(".lock")]
            print(f"   AVD files: {contents}")
            for fname in locks:
                fpath = os.path.join(avd_dir, fname)
                try:
                    os.remove(fpath)
                    print(f"   Removed stale lock: {fname}")
                except OSError as e:
                    print(f"   Could not remove {fname}: {e}")
        else:
            print(f"   AVD dir not found: {avd_dir}")

    def _switch_to_x86(self):
        """Switch from x86_64 to x86 system image (needed when VT-x/AMD-V unavailable)."""
        if self.abi == "x86":
            return  # already on x86
        print("   ⚠️  No hardware virtualization — switching to x86 (32-bit) system image.")
        self.abi          = "x86"
        self.system_image = "system-images;android-29;google_apis;x86"

        # Install the x86 system image if not already present
        sysimg_dir = os.path.join(
            self.sdk_dir, "system-images", "android-29", "google_apis", "x86"
        )
        if not os.path.exists(sysimg_dir):
            print("📦 Installing x86 system image (may take a few minutes)...")
            result = subprocess.run(
                [self.sdkmanager, f"--sdk_root={self.sdk_dir}", self.system_image],
                input="y\n" * 10,
                text=True,
                env=self._sdk_env(),
            )
            if result.returncode != 0:
                print("❌ Failed to install x86 system image.")
                sys.exit(1)
            print("✅ x86 system image installed.")

        # Delete the existing x86_64 AVD and recreate with x86
        avd_home = os.path.join(self.home_dir, ".android", "avd")
        for name in (f"{self.avd_name}.ini", f"{self.avd_name}.avd"):
            path = os.path.join(avd_home, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

        print(f"📦 Recreating AVD '{self.avd_name}' with x86 image...")
        result = subprocess.run(
            [
                self.avdmanager, "--verbose", "create", "avd",
                "-n", self.avd_name,
                "-k", self.system_image,
                "--device", "pixel",
                "--force",
            ],
            input="no\n",
            text=True,
            capture_output=True,
            env=self._sdk_env(),
        )
        if result.returncode != 0:
            print(f"❌ Failed to recreate AVD:\n{result.stderr[:500]}")
            sys.exit(1)
        print(f"✅ AVD '{self.avd_name}' recreated with x86 image.")

        # Remove any cached frida-server binary so install_frida re-downloads x86 build
        for old_fs in (os.path.join(self.work_dir, "fs"),
                       os.path.join(self.work_dir, "fs_x86_64")):
            if os.path.exists(old_fs):
                os.remove(old_fs)

    def _retry_with_software_accel(self):
        """Kill the current emulator and restart with -accel off (TCG/software).
        If the log indicates no hardware virtualization support, switch to the x86
        (32-bit) system image first — x86_64 TCG on Windows does not work without VT-x.
        """
        proc = getattr(self, "_emulator_proc", None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._cleanup_stale_emulator()

        # Detect "no virtualization" and switch to x86 if on x86_64
        log_content = ""
        log_path = getattr(self, "emulator_log", None)
        if log_path and os.path.exists(log_path):
            with open(log_path) as f:
                log_content = f.read()
        virt_absent = (
            "Virtualization extension is not supported" in log_content
            or "virtualization extension" in log_content.lower()
            or "requires hardware acceleration" in log_content
        )
        # On Linux/macOS, x86_64 with -accel off (TCG) works fine — no ABI switch needed.
        # On Windows, emulator 36.x broke x86_64 TCG even with -accel off, so we must
        # fall back to x86 (32-bit) which TCG still supports on Windows.
        if virt_absent and self.abi == "x86_64" and self.os_type == "Windows":
            self._switch_to_x86()

        subprocess.run([self.adb, "start-server"], capture_output=True, text=True)
        print("🔄 Retrying with software acceleration (-accel off)...")
        print("   NOTE: Software emulation is very slow — allow up to 15 minutes.")
        self._emulator_proc = self._launch_emulator_proc(["-accel", "off"])
        self._accel_fallback_tried = True
        self.target = "emulator-5554"

    def _find_emulator_serial(self):
        """Scan adb devices and return the serial of any online/booting emulator."""
        res = subprocess.run([self.adb, "devices"], capture_output=True, text=True)
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 1 and ("emulator-" in parts[0] or "localhost:" in parts[0]):
                # status can be "device", "offline", "unauthorized" — anything means it appeared
                return parts[0]
        return None

    def wait_for_boot(self, timeout=600):
        mins = timeout // 60
        print(f"⏳ Waiting for emulator to boot (up to {mins}m)...")
        start_ts = time.time()
        deadline  = start_ts + timeout
        proc = getattr(self, "_emulator_proc", None)

        def _elapsed():
            return int(time.time() - start_ts)

        def _remaining():
            return max(0, int(deadline - time.time()))

        def _fail(reason):
            print(f"\n❌ {reason}")
            self._show_emulator_log()
            if not self._accel_fallback_tried:
                self._retry_with_software_accel()
                self.wait_for_boot(timeout=900)   # 15 min for slow TCG
            else:
                sys.exit(1)

        # ── Phase 1: wait for emulator to appear in adb devices ─────────────
        print("   [Phase 1] Waiting for ADB to detect emulator...", flush=True)
        log_path        = getattr(self, "emulator_log", None)
        last_log_size   = 0
        last_log_change = time.time()
        STALL_SECS      = 45   # declare hung if log hasn't grown for this long

        while time.time() < deadline:
            serial = self._find_emulator_serial()
            if serial:
                self.target = serial
                print(f"\n   Found emulator: {serial}")
                break
            if proc and proc.poll() is not None:
                _fail(f"Emulator process exited (code {proc.returncode}) before ADB detected it.")
                return

            # Detect a hung emulator: log file exists but stopped growing
            if log_path and os.path.exists(log_path):
                cur_size = os.path.getsize(log_path)
                if cur_size != last_log_size:
                    last_log_size   = cur_size
                    last_log_change = time.time()
                elif time.time() - last_log_change > STALL_SECS and cur_size > 0:
                    _fail(f"Emulator log stopped growing for {STALL_SECS}s — emulator is hung.")
                    return

            print(f"\r   [Phase 1] {_elapsed()}s elapsed, ~{_remaining()}s remaining   ", end="", flush=True)
            time.sleep(5)
        else:
            _fail("ADB did not detect emulator within timeout.")
            return

        # ── Phase 2: wait for sys.boot_completed ────────────────────────────
        print(f"   [Phase 2] Emulator detected. Waiting for boot_completed...", flush=True)
        while time.time() < deadline:
            if proc and proc.poll() is not None:
                _fail(f"Emulator process exited (code {proc.returncode}) during boot.")
                return

            res = subprocess.run(
                [self.adb, "-s", self.target, "shell", "getprop", "sys.boot_completed"],
                capture_output=True, text=True,
            )
            if res.stdout.strip() == "1":
                print(f"\n✅ Boot complete ({_elapsed()}s). Rooting...")
                subprocess.run([self.adb, "-s", self.target, "root"], capture_output=True)
                # `adb root` restarts the ADB daemon on-device, which briefly takes
                # the device offline.  Wait until it's online again before returning.
                print("   Waiting for device to come back online after root...", flush=True)
                for _ in range(30):
                    time.sleep(2)
                    r = subprocess.run(
                        [self.adb, "-s", self.target, "get-state"],
                        capture_output=True, text=True,
                    )
                    if r.stdout.strip() == "device":
                        break
                else:
                    print("   ⚠️  Device did not fully come back online after root — continuing anyway.")
                return

            print(f"\r   [Phase 2] Booting... {_elapsed()}s elapsed, ~{_remaining()}s remaining   ", end="", flush=True)
            time.sleep(10)

        _fail("Boot timed out.")
        return

    def install_frida(self):
        print("\n🛠️  Ensuring frida-server is running...")
        res = self.run_adb(["shell", "pidof", "frida-server"], capture=True, check=False)
        if res.stdout.strip():
            print("✅ Frida is already running.")
            return

        version = requests.get(
            "https://api.github.com/repos/frida/frida/releases/latest"
        ).json()["tag_name"]
        url = (
            f"https://github.com/frida/frida/releases/download/{version}/"
            f"frida-server-{version}-android-{self.abi}.xz"
        )
        fs_path = os.path.join(self.work_dir, f"fs_{self.abi}")
        if not os.path.exists(fs_path):
            xz_path = fs_path + ".xz"
            with open(xz_path, "wb") as f:
                f.write(requests.get(url).content)
            with lzma.open(xz_path, "rb") as xz:
                with open(fs_path, "wb") as f:
                    f.write(xz.read())

        self.run_adb(["push", fs_path, "/data/local/tmp/frida-server"])
        self.run_adb(["shell", "chmod", "755", "/data/local/tmp/frida-server"])
        subprocess.Popen(
            [self.adb, "-s", self.target, "shell", "/data/local/tmp/frida-server"]
        )
        time.sleep(3)

    def _screencap(self, label="screen"):
        """Save a screenshot from the emulator to the work dir for debugging."""
        try:
            remote = "/data/local/tmp/dbg_screen.png"
            local  = os.path.join(self.work_dir, f"{label}.png")
            self.run_adb(["shell", "screencap", "-p", remote], check=False)
            self.run_adb(["pull", remote, local], check=False)
            print(f"   📸 Screenshot saved: {local}")
        except Exception:
            pass

    def _get_screen_size(self):
        """Return (width, height) of the current emulator display."""
        try:
            r = self.run_adb(["shell", "wm", "size"], capture=True)
            # Prefer override size; fall back to physical size
            for line in reversed(r.stdout.splitlines()):
                m = re.search(r"(\d+)x(\d+)", line)
                if m:
                    return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
        return 1080, 1920   # safe default

    def _dismiss_anr_dialogs(self):
        """Tap 'Wait' on any ANR/crash dialog that may be blocking the screen."""
        for _ in range(3):
            # Try UIAutomator path first
            wait_btn = self.get_view_center("Wait")
            if wait_btn:
                print(f"   ⚠️  ANR dialog detected — tapping Wait at {wait_btn}...")
                self.run_adb(["shell", "input", "tap",
                              str(wait_btn[0]), str(wait_btn[1])], check=False)
                time.sleep(3)
                continue
            # Blind-tap the "Wait" button position (lower option in the dialog,
            # ~59% across, ~61% down a 720×1280-equivalent layout, scaled to real size)
            w, h = self._get_screen_size()
            bx, by = int(w * 0.31), int(h * 0.62)
            # Only tap if uiautomator dump hints at an ANR dialog
            r = self.run_adb(["shell", "uiautomator", "dump", "/data/local/tmp/ui.xml"],
                             capture=True)
            xml = self.run_adb(["shell", "cat", "/data/local/tmp/ui.xml"],
                               capture=True).stdout or ""
            if "isn't responding" in xml or "not responding" in xml.lower():
                print(f"   ⚠️  ANR dialog detected (blind) — tapping Wait at ({bx},{by})...")
                self.run_adb(["shell", "input", "tap", str(bx), str(by)], check=False)
                time.sleep(3)
            else:
                break   # no ANR dialog found

    def run_keydive(self):
        print("\n🔑 Starting KeyDive...")
        # NOTE: We intentionally do NOT call `wm size` or `wm density` here.
        # On TCG (software) emulation those commands restart SurfaceFlinger and
        # trigger a System-UI ANR that blocks the entire screen.  We instead
        # query the real screen size and scale all coordinates to match.

        device_dir = os.path.join(self.work_dir, "device")
        if os.path.exists(device_dir):
            shutil.rmtree(device_dir, ignore_errors=True)

        kd_env = os.environ.copy()
        pt = os.path.join(self.sdk_dir, "platform-tools")
        kd_env["PATH"] = pt + os.pathsep + kd_env.get("PATH", "")
        kd_env["ADB"]  = self.adb

        # Capture stdout so we can detect "Successfully attached hook"
        kd_proc = subprocess.Popen(
            [self.venv_keydive, "-s", self.target, "-a", "player"],
            cwd=self.work_dir,
            env=kd_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        hook_attached = threading.Event()

        def _stream():
            for line in kd_proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                if "Successfully attached hook" in line:
                    hook_attached.set()

        threading.Thread(target=_stream, daemon=True).start()

        # Wait for Frida to hook into the Widevine process.
        # On systems with KVM/hardware accel the app starts in seconds.
        # On TCG (software emulation) the APK download + install on a fresh AVD
        # can easily take 15+ minutes, so give it a generous timeout.
        hook_timeout = 900   # 15 minutes — enough for a cold TCG APK install
        print(f"   Waiting for Frida hook to attach (up to {hook_timeout // 60}m on TCG)...")
        deadline_hook = time.time() + hook_timeout
        while not hook_attached.is_set():
            if hook_attached.wait(timeout=60):
                break
            if kd_proc.poll() is not None:
                print("❌ KeyDive exited before attaching hook.")
                return
            elapsed = int(time.time() - (deadline_hook - hook_timeout))
            remaining = max(0, int(deadline_hook - time.time()))
            print(f"   Still waiting for hook... {elapsed}s elapsed, ~{remaining}s remaining")
            if time.time() >= deadline_hook:
                print(f"❌ KeyDive failed to attach hook within {hook_timeout // 60} minutes.")
                kd_proc.terminate()
                return

        print("   Hook attached. Dismissing any ANR dialogs and starting UI automation...")
        time.sleep(5)
        self._dismiss_anr_dialogs()
        time.sleep(3)

        # Resolve real screen dimensions (no wm size override — that crashes System UI on TCG).
        sw, sh = self._get_screen_size()
        print(f"   Screen size: {sw}x{sh}")

        # All coordinates are expressed as fractions of a 720×1280 reference layout
        # and then scaled to the real screen size.
        def sc(rx, ry):
            return int(rx * sw / 720), int(ry * sh / 1280)

        # FAB: bottom-right corner of Kaltura Device Info Speed Dial app
        fab_x,  fab_y  = sc(640, 1185)
        # Player center
        ply_x,  ply_y  = sc(360, 640)
        # Speed-dial TEST DRM mini-FAB candidates: same x as FAB, stacked upward
        # Reference y values spaced ~72 px apart on 720×1280
        drm_candidates = [sc(640, ry) for ry in (1057, 985, 913, 850)]
        # Also try label-tap positions (slightly left of FAB column)
        drm_candidates += [sc(360, ry) for ry in (1057, 985, 913)]

        fab_clicked      = False
        test_clicked     = False
        ui_miss_fab      = 0
        ui_miss_drm      = 0
        player_taps      = 0   # taps since last TEST DRM attempt
        drm_attempt      = 0   # which candidate coordinate we're on
        start            = time.time()

        while time.time() - start < 600:
            # ── Check for extracted key files ────────────────────────────────
            for root_dir, _, files in os.walk(device_dir):
                if "client_id.bin" in files and \
                        os.path.getsize(os.path.join(root_dir, "client_id.bin")) > 500:
                    print(f"\n🎯 Keys exported: {root_dir}")
                    os.makedirs(self.out_dir, exist_ok=True)
                    for f in os.listdir(root_dir):
                        shutil.copy(os.path.join(root_dir, f), self.out_dir)
                    kd_proc.terminate()
                    print(f"📦 Files saved to: {self.out_dir}")
                    return

            if kd_proc.poll() is not None:
                print("❌ KeyDive exited unexpectedly.")
                return

            # Dismiss any ANR that crept up (System UI can restart spontaneously on TCG)
            self._dismiss_anr_dialogs()

            # ── Step 1: click FAB ─────────────────────────────────────────────
            if not fab_clicked:
                fab_btn = self.get_view_center("id/fab")
                if fab_btn:
                    print(f"🔘 Step 1: Clicking FAB (UI at {fab_btn})...")
                    self.run_adb(["shell", "input", "tap",
                                  str(fab_btn[0]), str(fab_btn[1])])
                    fab_clicked = True
                    time.sleep(4)
                else:
                    ui_miss_fab += 1
                    if ui_miss_fab >= 5:
                        print(f"🔘 Step 1: Clicking FAB (blind tap {fab_x},{fab_y})...")
                        self.run_adb(["shell", "input", "tap", str(fab_x), str(fab_y)])
                        fab_clicked = True
                        self._screencap("after_fab")
                        time.sleep(5)
                    else:
                        time.sleep(3)

            # ── Step 2: click TEST DRM ────────────────────────────────────────
            elif not test_clicked:
                test_btn = self.get_view_center("TEST DRM")
                if not test_btn:
                    test_btn = self.get_view_center("Test DRM")
                if test_btn:
                    print(f"🎯 Step 2: Clicking 'TEST DRM' (UI at {test_btn})...")
                    self.run_adb(["shell", "input", "tap",
                                  str(test_btn[0]), str(test_btn[1])])
                    test_clicked = True
                    player_taps  = 0
                    time.sleep(5)
                else:
                    ui_miss_drm += 1
                    if ui_miss_drm >= 5:
                        cx, cy = drm_candidates[drm_attempt % len(drm_candidates)]
                        print(f"🎯 Step 2: 'TEST DRM' blind tap ({cx},{cy}), attempt {drm_attempt + 1}...")
                        self.run_adb(["shell", "input", "tap", str(cx), str(cy)])
                        test_clicked = True
                        player_taps  = 0
                        drm_attempt += 1
                        time.sleep(5)
                    else:
                        time.sleep(3)

            # ── Step 3: tap video player center ──────────────────────────────
            else:
                print(f"🎬 Step 3: Tapping player center ({ply_x},{ply_y}), tap #{player_taps + 1}...")
                self.run_adb(["shell", "input", "tap", str(ply_x), str(ply_y)])
                player_taps += 1
                time.sleep(5)

                # If many player taps with no result, the TEST DRM tap likely missed.
                # Re-open FAB and try the next coordinate candidate.
                if player_taps >= 6:
                    if drm_attempt >= len(drm_candidates):
                        self._screencap("drm_fail")
                        print("❌ All TEST DRM tap candidates exhausted. "
                              f"Check {self.work_dir}/drm_fail.png for screen state.")
                        break
                    print(f"   No keys after {player_taps} player taps — "
                          f"re-opening FAB and trying next TEST DRM coordinate...")
                    self.run_adb(["shell", "input", "keyevent", "4"])  # Back
                    time.sleep(2)
                    self._dismiss_anr_dialogs()
                    self.run_adb(["shell", "input", "tap", str(fab_x), str(fab_y)])
                    time.sleep(4)
                    self._screencap(f"fab_retry_{drm_attempt}")
                    cx, cy = drm_candidates[drm_attempt % len(drm_candidates)]
                    print(f"🎯 Step 2 retry: 'TEST DRM' blind tap ({cx},{cy}), attempt {drm_attempt + 1}...")
                    self.run_adb(["shell", "input", "tap", str(cx), str(cy)])
                    drm_attempt += 1
                    player_taps  = 0
                    time.sleep(5)

        kd_proc.terminate()
        print("❌ KeyDive timed out without extracting keys.")

    def cleanup(self):
        print("\n🧹 Cleaning up...")
        if not self.skip_emulator:
            self.run_adb(["emu", "kill"], check=False)

    def run(self):
        self.setup_keydive()
        self.setup_android_sdk()
        self.start_emulator()
        self.wait_for_boot()
        self.install_frida()
        self.run_keydive()
        self.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Widevine L3 Extractor")
    parser.add_argument(
        "--out-dir", type=str, default="~/.config/ofscraper/device",
        help="Path to save the .bin and .pem files",
    )
    parser.add_argument(
        "--skip-emulator", action="store_true",
        help="Skip emulator creation/boot (assumes one is already running)",
    )
    args = parser.parse_args()
    WidevineMasterAutomator(
        out_dir=os.path.expanduser(args.out_dir),
        skip_emulator=args.skip_emulator,
    ).run()
