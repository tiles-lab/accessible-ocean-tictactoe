"""
Shared camera selection for hsv_calibration_tool.py and the tic-tac-toe prototypes.

At launch:
    python tictactoe_prototype8.py                   -> lists the cameras (by name) and asks which one to use
    python tictactoe_prototype8.py --camera orbbec   -> uses the Orbbec Gemini's COLOR camera
    python tictactoe_prototype8.py --camera FaceTime -> uses the camera whose name contains "FaceTime"
    python tictactoe_prototype8.py --camera 1        -> uses camera number 1
    (Passing --camera skips the question - use this for the exhibit so it starts unattended.
     On a Mac, prefer a name over a number: camera numbers change when an iPhone / Desk View
     camera appears or disappears, names don't.)
While running:
    press 'v' to switch to the next working camera.

Camera names:
    macOS   -> install  pyobjc-framework-AVFoundation  (in requirements.txt) for exact names;
               without it, names come from `system_profiler` when they can be matched safely.
    Linux   -> read from the system automatically.
    Windows -> shown as "camera N".

How "orbbec" reaches the Gemini 2's COLOR camera:
    macOS         -> macOS itself only exposes the Gemini's IR camera (greyscale). The color sensor
                     is only reachable through the Orbbec SDK, which on a Mac must run as administrator:
                         pip install --no-deps pyorbbecsdk2          (once; --no-deps keeps your OpenCV)
                         sudo -E .venv/bin/python tictactoe_prototype8.py --camera orbbec
    Windows/Linux -> OpenCV's built-in Orbbec support, or the Orbbec SDK if installed.
                     (Opening the Gemini by number there usually gives the depth/IR view.)
"""

MAC_SUDO_HINT = (
    "  The Gemini's color camera needs the Orbbec SDK, run as administrator on a Mac:\n"
    "      python -m pip install --no-deps pyorbbecsdk2      (once)\n"
    "      sudo -E .venv/bin/python <script>.py --camera orbbec"
)

import os
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")   # hide OpenCV noise while probing camera indices

import argparse
import json
import subprocess
import sys
import time
import cv2
import numpy as np

CAMERA_MAX_INDEX = 6      # how many camera numbers to try when the real count isn't known
CAMERA_WIDTH     = 1280
CAMERA_HEIGHT    = 720

# Picture settings (exposure, gain, brightness) for the Orbbec color camera. Adjusted with keys in
# hsv_calibration_tool.py, saved here, and applied automatically every time the camera opens -
# so the game sees exactly the same picture the colors were calibrated on.
CAMERA_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_settings.json")

ORBBEC_CONTROLS = {
    "auto_exposure": "OB_PROP_COLOR_AUTO_EXPOSURE_BOOL",
    "exposure":      "OB_PROP_COLOR_EXPOSURE_INT",
    "gain":          "OB_PROP_COLOR_GAIN_INT",
    "brightness":    "OB_PROP_COLOR_BRIGHTNESS_INT",
}

# Keys used by hsv_calibration_tool.py to adjust the picture: key -> (control, direction)
CAMERA_KEYS = {
    ord('['): ("exposure", -1),   ord(']'): ("exposure", +1),
    ord(';'): ("gain", -1),       ord("'"): ("gain", +1),
    ord(','): ("brightness", -1), ord('.'): ("brightness", +1),
    ord('e'): ("auto_exposure", 0),
}
CAMERA_KEYS_HELP = "[ ] exposure   ; ' gain   , . brightness   e auto-exposure on/off"

ORBBEC = "orbbec"         # camera id for the Orbbec color stream (via the Orbbec SDK)
ORBBEC_COLOR_WIDTH = 1280 # preferred color width (the Gemini 2 color sensor is 1280x800)
ORBBEC_COLOR_FPS   = 30


# -------------------------------------------------------------------
# Camera names
# -------------------------------------------------------------------
def _mac_names_avfoundation():
    """Same device list and order as OpenCV's macOS backend: video + muxed devices,
    sorted by uniqueID. Needs pyobjc-framework-AVFoundation."""
    import AVFoundation as AVF
    devs = list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo)) + \
           list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeMuxed))
    devs.sort(key=lambda d: str(d.uniqueID()))
    return [str(d.localizedName()) for d in devs]


def _mac_names_system_profiler():
    """Fallback without pyobjc. May miss some devices (e.g. iPhone Continuity Camera), so the
    caller only trusts it when the count matches what OpenCV sees."""
    out  = subprocess.run(["system_profiler", "SPCameraDataType", "-json"],
                          capture_output=True, text=True, timeout=15).stdout
    cams = [c for c in json.loads(out).get("SPCameraDataType", []) if c.get("spcamera_unique-id")]
    cams.sort(key=lambda c: c["spcamera_unique-id"])
    return [c.get("_name", "?") for c in cams]


def _linux_names():
    names = []
    for idx in range(CAMERA_MAX_INDEX):
        try:
            with open(f"/sys/class/video4linux/video{idx}/name") as f:
                names.append(f.read().strip())
        except OSError:
            names.append(None)
    return names


def _get_camera_names():
    """Returns (names, exact): names[i] is the name of OpenCV camera i (or None).
    exact=True when the list is known to match OpenCV's numbering exactly."""
    try:
        if sys.platform == "darwin":
            try:
                return _mac_names_avfoundation(), True
            except ImportError:
                return _mac_names_system_profiler(), False
            except Exception:
                return _mac_names_system_profiler(), False
        if sys.platform.startswith("linux"):
            return _linux_names(), True
    except Exception:
        pass
    return [], False


_NAMES = {}   # camera number -> name, filled in by list_cameras()


def give_back_to_user(path):
    """When a script runs with sudo, files it writes belong to root - which then blocks the
    normal (non-sudo) run from updating them. Hand them back to the user who ran sudo."""
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if uid and gid and os.path.exists(path):
        try:
            os.chown(path, int(uid), int(gid))
        except OSError:
            pass


def handle_camera_key(cap, key):
    """If key is one of CAMERA_KEYS, adjusts the camera picture and returns a status message;
    otherwise returns None."""
    if key not in CAMERA_KEYS:
        return None
    if not hasattr(cap, "adjust"):
        return "Picture controls only work with the Orbbec color camera (--camera orbbec)"
    control, direction = CAMERA_KEYS[key]
    msg = cap.adjust(control, direction)
    print(f"[CAMERA] {msg}")
    return msg


def camera_settings_text(cap):
    return cap.describe() if hasattr(cap, "describe") else ""


def camera_label(cam_id):
    if cam_id == ORBBEC:
        return "Orbbec SDK (color)"
    name = _NAMES.get(cam_id)
    return f"{name} (#{cam_id})" if name else f"camera {cam_id}"


def _numbered_ids():
    """Camera numbers worth trying. On a Mac with exact names, exactly that many (avoids
    OpenCV's 'out device of bound' messages)."""
    names, exact = _get_camera_names()
    if exact and sys.platform == "darwin":
        return list(range(len(names)))
    return list(range(CAMERA_MAX_INDEX))


# -------------------------------------------------------------------
# Orbbec color camera via the Orbbec SDK (behaves like a cv2.VideoCapture for our purposes)
# -------------------------------------------------------------------
def _orbbec_frame_to_bgr(frame):
    """Converts an Orbbec SDK color frame to a BGR numpy image (or None)."""
    from pyorbbecsdk import OBFormat
    w, h = frame.get_width(), frame.get_height()
    fmt  = frame.get_format()
    data = np.asanyarray(frame.get_data())
    if fmt == OBFormat.RGB:
        return cv2.cvtColor(data.reshape((h, w, 3)), cv2.COLOR_RGB2BGR)
    if fmt == OBFormat.BGR:
        return data.reshape((h, w, 3)).copy()
    if fmt == OBFormat.MJPG:
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    if fmt == OBFormat.YUYV:
        return cv2.cvtColor(data.reshape((h, w, 2)), cv2.COLOR_YUV2BGR_YUYV)
    if fmt == OBFormat.UYVY:
        return cv2.cvtColor(data.reshape((h, w, 2)), cv2.COLOR_YUV2BGR_UYVY)
    if fmt == OBFormat.NV12:
        return cv2.cvtColor(data.reshape((h * 3 // 2, w)), cv2.COLOR_YUV2BGR_NV12)
    if fmt == OBFormat.NV21:
        return cv2.cvtColor(data.reshape((h * 3 // 2, w)), cv2.COLOR_YUV2BGR_NV21)
    if fmt == OBFormat.I420:
        return cv2.cvtColor(data.reshape((h * 3 // 2, w)), cv2.COLOR_YUV2BGR_I420)
    print(f"[ORBBEC] unsupported color format: {fmt}")
    return None


class OrbbecColorCamera:
    """Opens only the COLOR stream of an Orbbec depth camera. Has the same read() /
    isOpened() / release() / set() methods the programs use on a cv2.VideoCapture."""

    def __init__(self, quiet=False):
        self.backend  = None
        self.pipeline = None
        self.device   = None
        self._desc    = None    # cached describe() text, refreshed when a setting changes
        self.cap      = None
        self.error    = None
        if not self._open_with_sdk(quiet):
            self._open_with_opencv()

    def _open_with_sdk(self, quiet):
        try:
            from pyorbbecsdk import Pipeline, Config, OBSensorType, OBFormat
        except ImportError:
            self.error = "Orbbec SDK not installed (pip install pyorbbecsdk2)"
            return False
        try:
            pipeline = Pipeline()
            profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
            try:
                profile = profiles.get_video_stream_profile(ORBBEC_COLOR_WIDTH, 0, OBFormat.RGB, ORBBEC_COLOR_FPS)
            except Exception:
                profile = profiles.get_default_video_stream_profile()
            config = Config()
            config.enable_stream(profile)   # color only - depth stays off
            pipeline.start(config)
            self.pipeline, self.backend = pipeline, "Orbbec SDK"
            try:
                self.device = pipeline.get_device()
                self.apply_saved_settings()
            except Exception as e:
                print(f"[ORBBEC] picture settings unavailable: {e}")
            return True
        except Exception as e:
            msg = str(e)
            if sys.platform == "darwin" and ("uvc_open" in msg or "ACCESS" in msg.upper()):
                self.error = ("the Orbbec SDK needs administrator rights on macOS - launch with "
                              "sudo -E .venv/bin/python ... (and close OrbbecViewer)")
            else:
                self.error = f"Orbbec SDK could not open the camera: {msg}"
            return False

    def _open_with_opencv(self):
        # OpenCV's built-in Orbbec support (Windows/Linux builds of opencv-python; not on macOS).
        if sys.platform == "darwin" or not hasattr(cv2, "CAP_OBSENSOR"):
            return False
        cap = cv2.VideoCapture(0, cv2.CAP_OBSENSOR)
        if cap.isOpened():
            self.cap, self.backend, self.error = cap, "OpenCV Orbbec backend", None
            return True
        cap.release()
        return False

    def isOpened(self):
        return self.backend is not None

    def read(self):
        """Returns (ok, bgr_frame). Waits up to ~1 s for a color frame."""
        if self.pipeline is not None:
            for _ in range(10):
                frames = self.pipeline.wait_for_frames(100)
                color  = frames.get_color_frame() if frames is not None else None
                if color is not None:
                    img = _orbbec_frame_to_bgr(color)
                    if img is not None:
                        return True, img
            return False, None
        if self.cap is not None:
            for _ in range(10):
                if self.cap.grab():
                    ok, img = self.cap.retrieve(None, cv2.CAP_OBSENSOR_BGR_IMAGE)
                    if ok and img is not None:
                        return True, img
                time.sleep(0.03)
        return False, None

    def set(self, *args):
        return False   # resolution is chosen when the stream starts

    # ---- Picture controls (Orbbec SDK only) ----
    def _pid(self, key):
        from pyorbbecsdk import OBPropertyID
        return getattr(OBPropertyID, ORBBEC_CONTROLS[key])

    def get_control(self, key):
        if self.device is None:
            return None
        try:
            if key == "auto_exposure":
                return bool(self.device.get_bool_property(self._pid(key)))
            return int(self.device.get_int_property(self._pid(key)))
        except Exception:
            return None

    def _range(self, key):
        try:
            r = self.device.get_int_property_range(self._pid(key))
            return int(r.min), int(r.max), max(1, int(r.step))
        except Exception:
            return None

    def set_control(self, key, value):
        if self.device is None:
            return False
        self._desc = None
        try:
            if key == "auto_exposure":
                self.device.set_bool_property(self._pid(key), bool(value))
            else:
                rng = self._range(key)
                if rng:
                    lo, hi, step = rng
                    value = lo + round((min(max(value, lo), hi) - lo) / step) * step
                self.device.set_int_property(self._pid(key), int(value))
            return True
        except Exception as e:
            print(f"[ORBBEC] can't set {key}: {e}")
            return False

    def adjust(self, key, direction):
        """Nudges a control up (+1) or down (-1); direction 0 toggles auto-exposure.
        Changing exposure or gain switches auto-exposure off (otherwise the camera would
        immediately undo the change). Saves the result. Returns a short status message."""
        if self.device is None:
            return "Picture controls need the Orbbec SDK color camera"
        if key == "auto_exposure":
            on = not bool(self.get_control("auto_exposure"))
            self.set_control("auto_exposure", on)
        else:
            if key in ("exposure", "gain") and self.get_control("auto_exposure"):
                self.set_control("auto_exposure", False)   # keeps the current auto value as the start
            cur, rng = self.get_control(key), self._range(key)
            if cur is None or rng is None:
                return f"This camera doesn't support {key}"
            lo, hi, step = rng
            if key == "exposure":                       # exposure feels natural in ~20% steps
                new = cur * 1.25 if direction > 0 else cur / 1.25
                if round(new) == cur:
                    new = cur + direction * step
            else:
                new = cur + direction * max(step, (hi - lo) // 20)
            self.set_control(key, int(round(new)))
        self.save_settings()
        return f"Camera: {self.describe()}"

    def describe(self):
        if self.device is None:
            return ""
        if self._desc is not None:
            return self._desc
        parts = ["auto-exposure ON" if self.get_control("auto_exposure") else "auto-exposure OFF"]
        for key in ("exposure", "gain", "brightness"):
            val = self.get_control(key)
            if val is not None:
                parts.append(f"{key} {val}")
        self._desc = "  ".join(parts)
        return self._desc

    def save_settings(self):
        settings = {k: self.get_control(k) for k in ORBBEC_CONTROLS}
        settings = {k: v for k, v in settings.items() if v is not None}
        try:
            with open(CAMERA_SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=2)
            give_back_to_user(CAMERA_SETTINGS_FILE)
        except OSError as e:
            print(f"[ORBBEC] couldn't save {CAMERA_SETTINGS_FILE}: {e}")

    def apply_saved_settings(self):
        if not os.path.exists(CAMERA_SETTINGS_FILE):
            return
        try:
            with open(CAMERA_SETTINGS_FILE) as f:
                settings = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[ORBBEC] couldn't read {CAMERA_SETTINGS_FILE}: {e}")
            return
        # Auto-exposure first: manual exposure/gain only stick once it's off.
        if "auto_exposure" in settings:
            self.set_control("auto_exposure", settings["auto_exposure"])
        for key in ("exposure", "gain"):
            if key in settings and not settings.get("auto_exposure", True):
                self.set_control(key, settings[key])
        if "brightness" in settings:
            self.set_control("brightness", settings["brightness"])
        print(f"[ORBBEC] applied saved picture settings: {self.describe()}")

    def release(self):
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception:
                pass
            self.pipeline = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.backend = None


def _orbbec_sdk_worth_trying():
    """Only probe the Orbbec choice if something could actually open it."""
    try:
        import pyorbbecsdk  # noqa: F401
        return True
    except ImportError:
        return sys.platform != "darwin" and hasattr(cv2, "CAP_OBSENSOR")


# -------------------------------------------------------------------
# Opening / listing / choosing
# -------------------------------------------------------------------
def open_camera(cam_id, quiet=False):
    """Opens a camera by id (a number, or ORBBEC). Returns a capture that delivers frames,
    or None."""
    if cam_id == ORBBEC:
        cap = OrbbecColorCamera()
        if not cap.isOpened():
            if not quiet:
                print(f"[ORBBEC] {cap.error or 'no Orbbec camera found'}")
            return None
        ok, _ = cap.read()
        if not ok:
            cap.release()
            return None
        print(f"[CAMERA] Orbbec color stream opened via {cap.backend}")
        return cap

    cap = cv2.VideoCapture(cam_id)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    ret, frame = cap.read()
    if not ret or frame is None:
        cap.release()
        return None
    return cap


def all_camera_ids():
    return _numbered_ids() + [ORBBEC]


def list_cameras():
    """Returns [(cam_id, width, height), ...] for every camera that delivers a frame, and fills
    in the camera names used by camera_label()."""
    names, exact = _get_camera_names()

    found = []
    for cam_id in (list(range(len(names))) if (exact and sys.platform == "darwin") else range(CAMERA_MAX_INDEX)):
        cap = open_camera(cam_id)
        if cap is not None:
            ok, frame = cap.read()
            if ok and frame is not None:
                found.append((cam_id, frame.shape[1], frame.shape[0]))
            cap.release()

    # Only use names we can trust to line up with OpenCV's numbering.
    _NAMES.clear()
    if exact or (names and len(names) == len(found) and [c[0] for c in found] == list(range(len(names)))):
        for i, name in enumerate(names):
            if name:
                _NAMES[i] = name

    if _orbbec_sdk_worth_trying():
        orb = OrbbecColorCamera()
        if orb.isOpened():
            ok, frame = orb.read()
            if ok and frame is not None:
                found.append((ORBBEC, frame.shape[1], frame.shape[0]))
        elif orb.error:
            print(f"  (Orbbec SDK option unavailable: {orb.error})")
        orb.release()
    return found


ORBBEC_NAME_HINTS = ("orbbec", "gemini")
COLOR_NAME_HINTS  = ("rgb", "color", "colour")      # names that suggest the color sensor
DEPTH_NAME_HINTS  = ("depth", "infrared", " ir", "ir ", "left", "right")   # names to avoid


def _color_preference(name):
    """Lower is better: color-sounding names first, depth/IR-sounding names last."""
    n = f" {name.lower()} "
    if any(h in n for h in COLOR_NAME_HINTS):
        return 0
    if any(h in n for h in DEPTH_NAME_HINTS):
        return 2
    return 1


def parse_camera_id(value):
    """'1' -> 1, 'orbbec' / 'o' -> ORBBEC, any other text -> that text (a camera name to
    search for), None / '' -> None."""
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    if value.isdigit():
        return int(value)
    if value.lower() in (ORBBEC, "o"):
        return ORBBEC
    return value


def _colorfulness(frame):
    """~0 for greyscale images (depth / infrared views), clearly higher for real color images."""
    b, g, r = (frame[..., k].astype(np.int16) for k in range(3))
    return float(np.mean(np.abs(b - g) + np.abs(g - r)))


COLOR_SCORE_MIN   = 6.0   # below this a frame is treated as greyscale (IR / depth)
_last_color_scores = {}


def _pick_most_colorful(cam_ids):
    """Opens each camera, grabs a frame, and returns the one with the most color."""
    best, best_score = None, -1.0
    for cam_id in cam_ids:
        cap = open_camera(cam_id, quiet=True)
        if cap is None:
            continue
        ok, frame = cap.read()
        cap.release()
        if ok and frame is not None:
            score = _colorfulness(frame)
            _last_color_scores[cam_id] = score
            print(f"[CAMERA]   {camera_label(cam_id)}: color score {score:.1f}")
            if score > best_score:
                best, best_score = cam_id, score
    return best


def find_orbbec_color_camera():
    """macOS: the Gemini may show up as several cameras (color, depth, infrared). Returns the
    number of its color camera: by name if one sounds like the color sensor, otherwise by
    checking which one actually delivers a color image."""
    names, exact = _get_camera_names()
    if not exact:
        return None
    _NAMES.update({j: n for j, n in enumerate(names) if n})
    # Orbbec entries that aren't obviously IR/depth (on a Mac there is normally none: macOS only
    # exposes the Gemini's IR camera).
    matches = [i for i, n in enumerate(names)
               if n and any(h in n.lower() for h in ORBBEC_NAME_HINTS) and _color_preference(n) < 2]
    if not matches:
        return None
    named_color = [i for i in matches if _color_preference(names[i]) == 0]
    if len(named_color) == 1:
        return named_color[0]
    print("[CAMERA] Checking which Orbbec camera is in color...")
    best = _pick_most_colorful(matches)
    return best if best is not None and _last_color_scores.get(best, 0) > COLOR_SCORE_MIN else None


def find_camera_by_name(*texts):
    """Camera number whose name contains any of texts (case-insensitive), or None.
    Only uses names that are known to match OpenCV's numbering."""
    names, exact = _get_camera_names()
    if not exact:
        return None
    matches = [i for i, name in enumerate(names)
               if name and any(t.lower() in name.lower() for t in texts)]
    if not matches:
        return None
    _NAMES.update({j: n for j, n in enumerate(names) if n})
    # Several matches (e.g. a depth camera listed as both a color and a depth device):
    # prefer the one whose name sounds like the color sensor.
    return min(matches, key=lambda i: (_color_preference(names[i]), i))


def resolve_camera_id(requested):
    """Turns what the user asked for into something open_camera() understands: a camera
    number, or ORBBEC (= Orbbec SDK / OpenCV Orbbec backend on Windows/Linux)."""
    if requested is None or isinstance(requested, int):
        return requested

    if requested == ORBBEC:
        if sys.platform == "darwin":
            idx = find_orbbec_color_camera()
            if idx is not None:
                return idx
            # Normal case on a Mac: only the SDK can deliver the color stream.
            try:
                import pyorbbecsdk  # noqa: F401
            except ImportError:
                print("[CAMERA] macOS only shows the Gemini's IR camera, not its color camera.")
                print(MAC_SUDO_HINT)
                return None
            if os.geteuid() != 0:
                print("[CAMERA] The Orbbec SDK can only open the Gemini when run as administrator on a Mac.")
                print(MAC_SUDO_HINT)
                return None
            return ORBBEC
        return ORBBEC

    idx = find_camera_by_name(requested)
    if idx is None:
        names, exact = _get_camera_names()
        if not exact:
            print("[CAMERA] Can't read camera names on this computer - use a camera number instead.")
        else:
            print(f"[CAMERA] No camera name contains '{requested}'. Cameras: {', '.join(n for n in names if n)}")
    return idx


def valid_ids(cams):
    return [c[0] for c in cams]


def _looks_like_orbbec(cam_id):
    name = (_NAMES.get(cam_id) or "").lower()
    return any(h in name for h in ORBBEC_NAME_HINTS)


def _best_orbbec(cam_ids):
    """Among cameras that look like the Orbbec, the one most likely to be its color sensor
    (IR/depth-named entries are never picked)."""
    orb = [c for c in cam_ids if isinstance(c, int) and _looks_like_orbbec(c)
           and _color_preference(_NAMES[c]) < 2]
    return min(orb, key=lambda c: (_color_preference(_NAMES[c]), c)) if orb else None


def choose_camera_id(requested=None):
    """The requested camera if given; otherwise lists the cameras found and asks in the
    terminal. Returns a camera id, or None if no camera works."""
    if requested is not None:
        cam_id = resolve_camera_id(requested)
        if isinstance(cam_id, int) and not _NAMES:
            names, exact = _get_camera_names()
            if exact:
                _NAMES.update({i: n for i, n in enumerate(names) if n})
        return cam_id

    print("\nLooking for cameras...")
    cams = list_cameras()
    if not cams:
        return None
    if len(cams) == 1:
        print(f"  Only one camera found: {camera_label(cams[0][0])} ({cams[0][1]}x{cams[0][2]})")
        return cams[0][0]

    print("Cameras found:")
    for cam_id, cw, ch in cams:
        key = "o" if cam_id == ORBBEC else str(cam_id)
        print(f"  [{key}]  {camera_label(cam_id):<40} {cw}x{ch}")
    if not _NAMES:
        print("  (Camera names unavailable - on a Mac: pip install pyobjc-framework-AVFoundation)")
    if ORBBEC in valid_ids(cams):
        print("  Tip: launch with  --camera orbbec  to always pick the Gemini's color camera.")
    elif any(_looks_like_orbbec(c[0]) for c in cams):
        print("  Note: the Gemini entry above is its IR (greyscale) camera, not its color camera.")
        if sys.platform == "darwin":
            print(MAC_SUDO_HINT)
    print("  (Not sure which is which? Pick one, then press 'v' in the program to cycle.)")

    valid = [c[0] for c in cams]
    best_orb = _best_orbbec(valid)
    orb_all  = [c for c in valid if isinstance(c, int) and _looks_like_orbbec(c)
                and _color_preference(_NAMES[c]) < 2]
    if len(orb_all) > 1 and not any(_color_preference(_NAMES[c]) == 0 for c in orb_all):
        best_orb = _pick_most_colorful(orb_all)
    not_ir  = [c for c in valid if not (isinstance(c, int) and _looks_like_orbbec(c)
                                        and _color_preference(_NAMES[c]) == 2)] or valid
    default = ORBBEC if ORBBEC in valid else (best_orb if best_orb is not None else not_ir[0])
    default_key = "o" if default == ORBBEC else str(default)
    while True:
        choice = input(f"Which camera do you want to use? (Enter = {default_key}): ").strip()
        if choice == "":
            return default
        cam_id = parse_camera_id(choice)
        if cam_id == ORBBEC and ORBBEC not in valid:
            cam_id = best_orb
            if cam_id is None:
                print("  The Gemini's color camera isn't available right now.")
                if sys.platform == "darwin":
                    print(MAC_SUDO_HINT)
                continue
        if cam_id in valid:
            return cam_id
        print("  Please type one of: " + ", ".join("o" if c == ORBBEC else str(c) for c in valid))


def start_camera(default_camera=None):
    """Reads --camera from the command line (a number or 'orbbec'), asks if needed, and
    opens the camera. Returns (cap, camera_id). Exits with a message if nothing opens."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default=None,
                        help="camera to use: 'orbbec' for the Orbbec Gemini's color camera, part of a "
                             "camera's name (e.g. FaceTime), or a number. Skips the question at launch.")
    args, _ = parser.parse_known_args()

    requested = parse_camera_id(args.camera if args.camera is not None else default_camera)
    cam_id = choose_camera_id(requested)
    if cam_id is None and requested == ORBBEC:
        raise SystemExit(1)          # the reason was already printed above
    cap = open_camera(cam_id) if cam_id is not None else None
    if cap is None:
        what = camera_label(cam_id) if cam_id is not None else (f"camera '{requested}'" if requested else "any camera")
        print(f"Error: could not open {what}.")
        print("  Check that it's plugged in and that no other program (e.g. OrbbecViewer, Zoom) is using it.")
        if sys.platform == "darwin":
            print("  On a Mac, also check System Settings > Privacy & Security > Camera allows your Terminal / VS Code.")
        raise SystemExit(1)
    print(f"Using {camera_label(cam_id)}")
    return cap, cam_id


def switch_to_next_camera(cap, current_id):
    """Releases cap and opens the next working camera after current_id (wrapping around,
    with the Orbbec SDK choice after the numbered cameras). Falls back to reopening
    current_id if nothing else works.
    Returns (cap, camera_id); cap is None only if even the current camera can't be reopened."""
    cap.release()
    ids   = all_camera_ids()
    start = ids.index(current_id) if current_id in ids else -1
    for step in range(1, len(ids) + 1):
        cam_id  = ids[(start + step) % len(ids)]
        new_cap = open_camera(cam_id, quiet=True)
        if new_cap is not None:
            if cam_id == current_id:
                print(f"[CAMERA] no other camera found - staying on {camera_label(cam_id)}")
            else:
                print(f"[CAMERA] switched to {camera_label(cam_id)}")
            return new_cap, cam_id
    print(f"[CAMERA] lost {camera_label(current_id)} and found no other camera")
    return None, current_id


# -------------------------------------------------------------------
# Diagnostic:  python camera_select.py
# -------------------------------------------------------------------
def _fourcc(code):
    try:
        return int(code).to_bytes(4, "big").decode("ascii", "replace")
    except Exception:
        return str(code)


def print_camera_report():
    """Prints every camera the computer reports, with the image formats each one offers,
    plus what OpenCV actually receives from it. Helps tell a depth camera's color sensor
    apart from its depth/infrared sensors."""
    print(f"Platform: {sys.platform}   OpenCV {cv2.__version__}\n")
    if sys.platform == "darwin":
        try:
            import AVFoundation as AVF
            devs = list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo)) + \
                   list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeMuxed))
            devs.sort(key=lambda d: str(d.uniqueID()))
        except Exception as e:
            print(f"Can't read macOS camera list ({e}). Run: pip install pyobjc-framework-AVFoundation")
            devs = []
        try:
            import CoreMedia as CM
        except Exception:
            CM = None
        for i, d in enumerate(devs):
            print(f"[{i}] {d.localizedName()}")
            for label, attr in (("model", "modelID"), ("maker", "manufacturer"), ("id", "uniqueID")):
                try:
                    print(f"     {label}: {getattr(d, attr)()}")
                except Exception:
                    pass
            if CM is not None:
                seen = []
                for f in d.formats():
                    try:
                        desc = f.formatDescription()
                        sub_ = _fourcc(CM.CMFormatDescriptionGetMediaSubType(desc))
                        dims = CM.CMVideoFormatDescriptionGetDimensions(desc)
                        item = f"{sub_} {dims.width}x{dims.height}"
                    except Exception:
                        item = str(f)[:60]
                    if item not in seen:
                        seen.append(item)
                print(f"     formats: {', '.join(seen) if seen else '(none reported)'}")
            _report_opencv_frame(i)
            print()
        try:
            import pyorbbecsdk  # noqa: F401
            print("[o] Orbbec SDK (color)")
            _report_opencv_frame(ORBBEC)
        except ImportError:
            print("Orbbec SDK not installed - the Gemini's COLOR camera isn't reachable on a Mac without it.")
            print(MAC_SUDO_HINT)
    else:
        names, _ = _get_camera_names()
        for i in range(CAMERA_MAX_INDEX):
            name = names[i] if i < len(names) and names[i] else "?"
            print(f"[{i}] {name}")
            _report_opencv_frame(i)
            print()


def _report_opencv_frame(idx):
    cap = open_camera(idx, quiet=(idx != ORBBEC))
    if cap is None:
        print("     can't open / no frame")
        return
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        print("     OpenCV: no frame")
        return
    colorfulness = _colorfulness(frame)
    kind = "COLOR image" if colorfulness > 6 else "GREYSCALE image (depth/infrared?)"
    print(f"     OpenCV: {frame.shape[1]}x{frame.shape[0]}, {kind} (color score {colorfulness:.1f})")
    snap = f"camera_{'orbbec' if idx == ORBBEC else idx}_snapshot.png"
    cv2.imwrite(snap, frame)
    give_back_to_user(snap)
    print(f"     saved {snap}")


if __name__ == "__main__":
    print_camera_report()

# """
# Shared camera selection for hsv_calibration_tool.py and the tic-tac-toe prototypes.

# At launch:
#     python tictactoe_prototype8.py                   -> lists the cameras (by name) and asks which one to use
#     python tictactoe_prototype8.py --camera orbbec   -> uses the Orbbec Gemini's COLOR camera
#     python tictactoe_prototype8.py --camera FaceTime -> uses the camera whose name contains "FaceTime"
#     python tictactoe_prototype8.py --camera 1        -> uses camera number 1
#     (Passing --camera skips the question - use this for the exhibit so it starts unattended.
#      On a Mac, prefer a name over a number: camera numbers change when an iPhone / Desk View
#      camera appears or disappears, names don't.)
# While running:
#     press 'v' to switch to the next working camera.

# Camera names:
#     macOS   -> install  pyobjc-framework-AVFoundation  (in requirements.txt) for exact names;
#                without it, names come from `system_profiler` when they can be matched safely.
#     Linux   -> read from the system automatically.
#     Windows -> shown as "camera N".

# How "orbbec" reaches the Gemini 2's COLOR camera:
#     macOS         -> macOS itself only exposes the Gemini's IR camera (greyscale). The color sensor
#                      is only reachable through the Orbbec SDK, which on a Mac must run as administrator:
#                          pip install --no-deps pyorbbecsdk2          (once; --no-deps keeps your OpenCV)
#                          sudo -E .venv/bin/python tictactoe_prototype8.py --camera orbbec
#     Windows/Linux -> OpenCV's built-in Orbbec support, or the Orbbec SDK if installed.
#                      (Opening the Gemini by number there usually gives the depth/IR view.)
# """

# MAC_SUDO_HINT = (
#     "  The Gemini's color camera needs the Orbbec SDK, run as administrator on a Mac:\n"
#     "      python -m pip install --no-deps pyorbbecsdk2      (once)\n"
#     "      sudo -E .venv/bin/python <script>.py --camera orbbec"
# )

# import os
# os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")   # hide OpenCV noise while probing camera indices

# import argparse
# import json
# import subprocess
# import sys
# import time
# import cv2
# import numpy as np

# CAMERA_MAX_INDEX = 6      # how many camera numbers to try when the real count isn't known
# CAMERA_WIDTH     = 1280
# CAMERA_HEIGHT    = 720

# ORBBEC = "orbbec"         # camera id for the Orbbec color stream (via the Orbbec SDK)
# ORBBEC_COLOR_WIDTH = 1280 # preferred color width (the Gemini 2 color sensor is 1280x800)
# ORBBEC_COLOR_FPS   = 30


# # -------------------------------------------------------------------
# # Camera names
# # -------------------------------------------------------------------
# def _mac_names_avfoundation():
#     """Same device list and order as OpenCV's macOS backend: video + muxed devices,
#     sorted by uniqueID. Needs pyobjc-framework-AVFoundation."""
#     import AVFoundation as AVF
#     devs = list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo)) + \
#            list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeMuxed))
#     devs.sort(key=lambda d: str(d.uniqueID()))
#     return [str(d.localizedName()) for d in devs]


# def _mac_names_system_profiler():
#     """Fallback without pyobjc. May miss some devices (e.g. iPhone Continuity Camera), so the
#     caller only trusts it when the count matches what OpenCV sees."""
#     out  = subprocess.run(["system_profiler", "SPCameraDataType", "-json"],
#                           capture_output=True, text=True, timeout=15).stdout
#     cams = [c for c in json.loads(out).get("SPCameraDataType", []) if c.get("spcamera_unique-id")]
#     cams.sort(key=lambda c: c["spcamera_unique-id"])
#     return [c.get("_name", "?") for c in cams]


# def _linux_names():
#     names = []
#     for idx in range(CAMERA_MAX_INDEX):
#         try:
#             with open(f"/sys/class/video4linux/video{idx}/name") as f:
#                 names.append(f.read().strip())
#         except OSError:
#             names.append(None)
#     return names


# def _get_camera_names():
#     """Returns (names, exact): names[i] is the name of OpenCV camera i (or None).
#     exact=True when the list is known to match OpenCV's numbering exactly."""
#     try:
#         if sys.platform == "darwin":
#             try:
#                 return _mac_names_avfoundation(), True
#             except ImportError:
#                 return _mac_names_system_profiler(), False
#             except Exception:
#                 return _mac_names_system_profiler(), False
#         if sys.platform.startswith("linux"):
#             return _linux_names(), True
#     except Exception:
#         pass
#     return [], False


# _NAMES = {}   # camera number -> name, filled in by list_cameras()


# def give_back_to_user(path):
#     """When a script runs with sudo, files it writes belong to root - which then blocks the
#     normal (non-sudo) run from updating them. Hand them back to the user who ran sudo."""
#     uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
#     if uid and gid and os.path.exists(path):
#         try:
#             os.chown(path, int(uid), int(gid))
#         except OSError:
#             pass


# def camera_label(cam_id):
#     if cam_id == ORBBEC:
#         return "Orbbec SDK (color)"
#     name = _NAMES.get(cam_id)
#     return f"{name} (#{cam_id})" if name else f"camera {cam_id}"


# def _numbered_ids():
#     """Camera numbers worth trying. On a Mac with exact names, exactly that many (avoids
#     OpenCV's 'out device of bound' messages)."""
#     names, exact = _get_camera_names()
#     if exact and sys.platform == "darwin":
#         return list(range(len(names)))
#     return list(range(CAMERA_MAX_INDEX))


# # -------------------------------------------------------------------
# # Orbbec color camera via the Orbbec SDK (behaves like a cv2.VideoCapture for our purposes)
# # -------------------------------------------------------------------
# def _orbbec_frame_to_bgr(frame):
#     """Converts an Orbbec SDK color frame to a BGR numpy image (or None)."""
#     from pyorbbecsdk import OBFormat
#     w, h = frame.get_width(), frame.get_height()
#     fmt  = frame.get_format()
#     data = np.asanyarray(frame.get_data())
#     if fmt == OBFormat.RGB:
#         return cv2.cvtColor(data.reshape((h, w, 3)), cv2.COLOR_RGB2BGR)
#     if fmt == OBFormat.BGR:
#         return data.reshape((h, w, 3)).copy()
#     if fmt == OBFormat.MJPG:
#         return cv2.imdecode(data, cv2.IMREAD_COLOR)
#     if fmt == OBFormat.YUYV:
#         return cv2.cvtColor(data.reshape((h, w, 2)), cv2.COLOR_YUV2BGR_YUYV)
#     if fmt == OBFormat.UYVY:
#         return cv2.cvtColor(data.reshape((h, w, 2)), cv2.COLOR_YUV2BGR_UYVY)
#     if fmt == OBFormat.NV12:
#         return cv2.cvtColor(data.reshape((h * 3 // 2, w)), cv2.COLOR_YUV2BGR_NV12)
#     if fmt == OBFormat.NV21:
#         return cv2.cvtColor(data.reshape((h * 3 // 2, w)), cv2.COLOR_YUV2BGR_NV21)
#     if fmt == OBFormat.I420:
#         return cv2.cvtColor(data.reshape((h * 3 // 2, w)), cv2.COLOR_YUV2BGR_I420)
#     print(f"[ORBBEC] unsupported color format: {fmt}")
#     return None


# class OrbbecColorCamera:
#     """Opens only the COLOR stream of an Orbbec depth camera. Has the same read() /
#     isOpened() / release() / set() methods the programs use on a cv2.VideoCapture."""

#     def __init__(self, quiet=False):
#         self.backend  = None
#         self.pipeline = None
#         self.cap      = None
#         self.error    = None
#         if not self._open_with_sdk(quiet):
#             self._open_with_opencv()

#     def _open_with_sdk(self, quiet):
#         try:
#             from pyorbbecsdk import Pipeline, Config, OBSensorType, OBFormat
#         except ImportError:
#             self.error = "Orbbec SDK not installed (pip install pyorbbecsdk2)"
#             return False
#         try:
#             pipeline = Pipeline()
#             profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
#             try:
#                 profile = profiles.get_video_stream_profile(ORBBEC_COLOR_WIDTH, 0, OBFormat.RGB, ORBBEC_COLOR_FPS)
#             except Exception:
#                 profile = profiles.get_default_video_stream_profile()
#             config = Config()
#             config.enable_stream(profile)   # color only - depth stays off
#             pipeline.start(config)
#             self.pipeline, self.backend = pipeline, "Orbbec SDK"
#             return True
#         except Exception as e:
#             msg = str(e)
#             if sys.platform == "darwin" and ("uvc_open" in msg or "ACCESS" in msg.upper()):
#                 self.error = ("the Orbbec SDK needs administrator rights on macOS - launch with "
#                               "sudo -E .venv/bin/python ... (and close OrbbecViewer)")
#             else:
#                 self.error = f"Orbbec SDK could not open the camera: {msg}"
#             return False

#     def _open_with_opencv(self):
#         # OpenCV's built-in Orbbec support (Windows/Linux builds of opencv-python; not on macOS).
#         if sys.platform == "darwin" or not hasattr(cv2, "CAP_OBSENSOR"):
#             return False
#         cap = cv2.VideoCapture(0, cv2.CAP_OBSENSOR)
#         if cap.isOpened():
#             self.cap, self.backend, self.error = cap, "OpenCV Orbbec backend", None
#             return True
#         cap.release()
#         return False

#     def isOpened(self):
#         return self.backend is not None

#     def read(self):
#         """Returns (ok, bgr_frame). Waits up to ~1 s for a color frame."""
#         if self.pipeline is not None:
#             for _ in range(10):
#                 frames = self.pipeline.wait_for_frames(100)
#                 color  = frames.get_color_frame() if frames is not None else None
#                 if color is not None:
#                     img = _orbbec_frame_to_bgr(color)
#                     if img is not None:
#                         return True, img
#             return False, None
#         if self.cap is not None:
#             for _ in range(10):
#                 if self.cap.grab():
#                     ok, img = self.cap.retrieve(None, cv2.CAP_OBSENSOR_BGR_IMAGE)
#                     if ok and img is not None:
#                         return True, img
#                 time.sleep(0.03)
#         return False, None

#     def set(self, *args):
#         return False   # resolution is chosen when the stream starts

#     def release(self):
#         if self.pipeline is not None:
#             try:
#                 self.pipeline.stop()
#             except Exception:
#                 pass
#             self.pipeline = None
#         if self.cap is not None:
#             self.cap.release()
#             self.cap = None
#         self.backend = None


# def _orbbec_sdk_worth_trying():
#     """Only probe the Orbbec choice if something could actually open it."""
#     try:
#         import pyorbbecsdk  # noqa: F401
#         return True
#     except ImportError:
#         return sys.platform != "darwin" and hasattr(cv2, "CAP_OBSENSOR")


# # -------------------------------------------------------------------
# # Opening / listing / choosing
# # -------------------------------------------------------------------
# def open_camera(cam_id, quiet=False):
#     """Opens a camera by id (a number, or ORBBEC). Returns a capture that delivers frames,
#     or None."""
#     if cam_id == ORBBEC:
#         cap = OrbbecColorCamera()
#         if not cap.isOpened():
#             if not quiet:
#                 print(f"[ORBBEC] {cap.error or 'no Orbbec camera found'}")
#             return None
#         ok, _ = cap.read()
#         if not ok:
#             cap.release()
#             return None
#         print(f"[CAMERA] Orbbec color stream opened via {cap.backend}")
#         return cap

#     cap = cv2.VideoCapture(cam_id)
#     if not cap.isOpened():
#         cap.release()
#         return None
#     cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
#     cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
#     ret, frame = cap.read()
#     if not ret or frame is None:
#         cap.release()
#         return None
#     return cap


# def all_camera_ids():
#     return _numbered_ids() + [ORBBEC]


# def list_cameras():
#     """Returns [(cam_id, width, height), ...] for every camera that delivers a frame, and fills
#     in the camera names used by camera_label()."""
#     names, exact = _get_camera_names()

#     found = []
#     for cam_id in (list(range(len(names))) if (exact and sys.platform == "darwin") else range(CAMERA_MAX_INDEX)):
#         cap = open_camera(cam_id)
#         if cap is not None:
#             ok, frame = cap.read()
#             if ok and frame is not None:
#                 found.append((cam_id, frame.shape[1], frame.shape[0]))
#             cap.release()

#     # Only use names we can trust to line up with OpenCV's numbering.
#     _NAMES.clear()
#     if exact or (names and len(names) == len(found) and [c[0] for c in found] == list(range(len(names)))):
#         for i, name in enumerate(names):
#             if name:
#                 _NAMES[i] = name

#     if _orbbec_sdk_worth_trying():
#         orb = OrbbecColorCamera()
#         if orb.isOpened():
#             ok, frame = orb.read()
#             if ok and frame is not None:
#                 found.append((ORBBEC, frame.shape[1], frame.shape[0]))
#         elif orb.error:
#             print(f"  (Orbbec SDK option unavailable: {orb.error})")
#         orb.release()
#     return found


# ORBBEC_NAME_HINTS = ("orbbec", "gemini")
# COLOR_NAME_HINTS  = ("rgb", "color", "colour")      # names that suggest the color sensor
# DEPTH_NAME_HINTS  = ("depth", "infrared", " ir", "ir ", "left", "right")   # names to avoid


# def _color_preference(name):
#     """Lower is better: color-sounding names first, depth/IR-sounding names last."""
#     n = f" {name.lower()} "
#     if any(h in n for h in COLOR_NAME_HINTS):
#         return 0
#     if any(h in n for h in DEPTH_NAME_HINTS):
#         return 2
#     return 1


# def parse_camera_id(value):
#     """'1' -> 1, 'orbbec' / 'o' -> ORBBEC, any other text -> that text (a camera name to
#     search for), None / '' -> None."""
#     if value is None:
#         return None
#     value = str(value).strip()
#     if value == "":
#         return None
#     if value.isdigit():
#         return int(value)
#     if value.lower() in (ORBBEC, "o"):
#         return ORBBEC
#     return value


# def _colorfulness(frame):
#     """~0 for greyscale images (depth / infrared views), clearly higher for real color images."""
#     b, g, r = (frame[..., k].astype(np.int16) for k in range(3))
#     return float(np.mean(np.abs(b - g) + np.abs(g - r)))


# COLOR_SCORE_MIN   = 6.0   # below this a frame is treated as greyscale (IR / depth)
# _last_color_scores = {}


# def _pick_most_colorful(cam_ids):
#     """Opens each camera, grabs a frame, and returns the one with the most color."""
#     best, best_score = None, -1.0
#     for cam_id in cam_ids:
#         cap = open_camera(cam_id, quiet=True)
#         if cap is None:
#             continue
#         ok, frame = cap.read()
#         cap.release()
#         if ok and frame is not None:
#             score = _colorfulness(frame)
#             _last_color_scores[cam_id] = score
#             print(f"[CAMERA]   {camera_label(cam_id)}: color score {score:.1f}")
#             if score > best_score:
#                 best, best_score = cam_id, score
#     return best


# def find_orbbec_color_camera():
#     """macOS: the Gemini may show up as several cameras (color, depth, infrared). Returns the
#     number of its color camera: by name if one sounds like the color sensor, otherwise by
#     checking which one actually delivers a color image."""
#     names, exact = _get_camera_names()
#     if not exact:
#         return None
#     _NAMES.update({j: n for j, n in enumerate(names) if n})
#     # Orbbec entries that aren't obviously IR/depth (on a Mac there is normally none: macOS only
#     # exposes the Gemini's IR camera).
#     matches = [i for i, n in enumerate(names)
#                if n and any(h in n.lower() for h in ORBBEC_NAME_HINTS) and _color_preference(n) < 2]
#     if not matches:
#         return None
#     named_color = [i for i in matches if _color_preference(names[i]) == 0]
#     if len(named_color) == 1:
#         return named_color[0]
#     print("[CAMERA] Checking which Orbbec camera is in color...")
#     best = _pick_most_colorful(matches)
#     return best if best is not None and _last_color_scores.get(best, 0) > COLOR_SCORE_MIN else None


# def find_camera_by_name(*texts):
#     """Camera number whose name contains any of texts (case-insensitive), or None.
#     Only uses names that are known to match OpenCV's numbering."""
#     names, exact = _get_camera_names()
#     if not exact:
#         return None
#     matches = [i for i, name in enumerate(names)
#                if name and any(t.lower() in name.lower() for t in texts)]
#     if not matches:
#         return None
#     _NAMES.update({j: n for j, n in enumerate(names) if n})
#     # Several matches (e.g. a depth camera listed as both a color and a depth device):
#     # prefer the one whose name sounds like the color sensor.
#     return min(matches, key=lambda i: (_color_preference(names[i]), i))


# def resolve_camera_id(requested):
#     """Turns what the user asked for into something open_camera() understands: a camera
#     number, or ORBBEC (= Orbbec SDK / OpenCV Orbbec backend on Windows/Linux)."""
#     if requested is None or isinstance(requested, int):
#         return requested

#     if requested == ORBBEC:
#         if sys.platform == "darwin":
#             idx = find_orbbec_color_camera()
#             if idx is not None:
#                 return idx
#             # Normal case on a Mac: only the SDK can deliver the color stream.
#             try:
#                 import pyorbbecsdk  # noqa: F401
#             except ImportError:
#                 print("[CAMERA] macOS only shows the Gemini's IR camera, not its color camera.")
#                 print(MAC_SUDO_HINT)
#                 return None
#             if os.geteuid() != 0:
#                 print("[CAMERA] The Orbbec SDK can only open the Gemini when run as administrator on a Mac.")
#                 print(MAC_SUDO_HINT)
#                 return None
#             return ORBBEC
#         return ORBBEC

#     idx = find_camera_by_name(requested)
#     if idx is None:
#         names, exact = _get_camera_names()
#         if not exact:
#             print("[CAMERA] Can't read camera names on this computer - use a camera number instead.")
#         else:
#             print(f"[CAMERA] No camera name contains '{requested}'. Cameras: {', '.join(n for n in names if n)}")
#     return idx


# def valid_ids(cams):
#     return [c[0] for c in cams]


# def _looks_like_orbbec(cam_id):
#     name = (_NAMES.get(cam_id) or "").lower()
#     return any(h in name for h in ORBBEC_NAME_HINTS)


# def _best_orbbec(cam_ids):
#     """Among cameras that look like the Orbbec, the one most likely to be its color sensor
#     (IR/depth-named entries are never picked)."""
#     orb = [c for c in cam_ids if isinstance(c, int) and _looks_like_orbbec(c)
#            and _color_preference(_NAMES[c]) < 2]
#     return min(orb, key=lambda c: (_color_preference(_NAMES[c]), c)) if orb else None


# def choose_camera_id(requested=None):
#     """The requested camera if given; otherwise lists the cameras found and asks in the
#     terminal. Returns a camera id, or None if no camera works."""
#     if requested is not None:
#         cam_id = resolve_camera_id(requested)
#         if isinstance(cam_id, int) and not _NAMES:
#             names, exact = _get_camera_names()
#             if exact:
#                 _NAMES.update({i: n for i, n in enumerate(names) if n})
#         return cam_id

#     print("\nLooking for cameras...")
#     cams = list_cameras()
#     if not cams:
#         return None
#     if len(cams) == 1:
#         print(f"  Only one camera found: {camera_label(cams[0][0])} ({cams[0][1]}x{cams[0][2]})")
#         return cams[0][0]

#     print("Cameras found:")
#     for cam_id, cw, ch in cams:
#         key = "o" if cam_id == ORBBEC else str(cam_id)
#         print(f"  [{key}]  {camera_label(cam_id):<40} {cw}x{ch}")
#     if not _NAMES:
#         print("  (Camera names unavailable - on a Mac: pip install pyobjc-framework-AVFoundation)")
#     if ORBBEC in valid_ids(cams):
#         print("  Tip: launch with  --camera orbbec  to always pick the Gemini's color camera.")
#     elif any(_looks_like_orbbec(c[0]) for c in cams):
#         print("  Note: the Gemini entry above is its IR (greyscale) camera, not its color camera.")
#         if sys.platform == "darwin":
#             print(MAC_SUDO_HINT)
#     print("  (Not sure which is which? Pick one, then press 'v' in the program to cycle.)")

#     valid = [c[0] for c in cams]
#     best_orb = _best_orbbec(valid)
#     orb_all  = [c for c in valid if isinstance(c, int) and _looks_like_orbbec(c)
#                 and _color_preference(_NAMES[c]) < 2]
#     if len(orb_all) > 1 and not any(_color_preference(_NAMES[c]) == 0 for c in orb_all):
#         best_orb = _pick_most_colorful(orb_all)
#     not_ir  = [c for c in valid if not (isinstance(c, int) and _looks_like_orbbec(c)
#                                         and _color_preference(_NAMES[c]) == 2)] or valid
#     default = ORBBEC if ORBBEC in valid else (best_orb if best_orb is not None else not_ir[0])
#     default_key = "o" if default == ORBBEC else str(default)
#     while True:
#         choice = input(f"Which camera do you want to use? (Enter = {default_key}): ").strip()
#         if choice == "":
#             return default
#         cam_id = parse_camera_id(choice)
#         if cam_id == ORBBEC and ORBBEC not in valid:
#             cam_id = best_orb
#             if cam_id is None:
#                 print("  The Gemini's color camera isn't available right now.")
#                 if sys.platform == "darwin":
#                     print(MAC_SUDO_HINT)
#                 continue
#         if cam_id in valid:
#             return cam_id
#         print("  Please type one of: " + ", ".join("o" if c == ORBBEC else str(c) for c in valid))


# def start_camera(default_camera=None):
#     """Reads --camera from the command line (a number or 'orbbec'), asks if needed, and
#     opens the camera. Returns (cap, camera_id). Exits with a message if nothing opens."""
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--camera", default=None,
#                         help="camera to use: 'orbbec' for the Orbbec Gemini's color camera, part of a "
#                              "camera's name (e.g. FaceTime), or a number. Skips the question at launch.")
#     args, _ = parser.parse_known_args()

#     requested = parse_camera_id(args.camera if args.camera is not None else default_camera)
#     cam_id = choose_camera_id(requested)
#     if cam_id is None and requested == ORBBEC:
#         raise SystemExit(1)          # the reason was already printed above
#     cap = open_camera(cam_id) if cam_id is not None else None
#     if cap is None:
#         what = camera_label(cam_id) if cam_id is not None else (f"camera '{requested}'" if requested else "any camera")
#         print(f"Error: could not open {what}.")
#         print("  Check that it's plugged in and that no other program (e.g. OrbbecViewer, Zoom) is using it.")
#         if sys.platform == "darwin":
#             print("  On a Mac, also check System Settings > Privacy & Security > Camera allows your Terminal / VS Code.")
#         raise SystemExit(1)
#     print(f"Using {camera_label(cam_id)}")
#     return cap, cam_id


# def switch_to_next_camera(cap, current_id):
#     """Releases cap and opens the next working camera after current_id (wrapping around,
#     with the Orbbec SDK choice after the numbered cameras). Falls back to reopening
#     current_id if nothing else works.
#     Returns (cap, camera_id); cap is None only if even the current camera can't be reopened."""
#     cap.release()
#     ids   = all_camera_ids()
#     start = ids.index(current_id) if current_id in ids else -1
#     for step in range(1, len(ids) + 1):
#         cam_id  = ids[(start + step) % len(ids)]
#         new_cap = open_camera(cam_id, quiet=True)
#         if new_cap is not None:
#             if cam_id == current_id:
#                 print(f"[CAMERA] no other camera found - staying on {camera_label(cam_id)}")
#             else:
#                 print(f"[CAMERA] switched to {camera_label(cam_id)}")
#             return new_cap, cam_id
#     print(f"[CAMERA] lost {camera_label(current_id)} and found no other camera")
#     return None, current_id


# # -------------------------------------------------------------------
# # Diagnostic:  python camera_select.py
# # -------------------------------------------------------------------
# def _fourcc(code):
#     try:
#         return int(code).to_bytes(4, "big").decode("ascii", "replace")
#     except Exception:
#         return str(code)


# def print_camera_report():
#     """Prints every camera the computer reports, with the image formats each one offers,
#     plus what OpenCV actually receives from it. Helps tell a depth camera's color sensor
#     apart from its depth/infrared sensors."""
#     print(f"Platform: {sys.platform}   OpenCV {cv2.__version__}\n")
#     if sys.platform == "darwin":
#         try:
#             import AVFoundation as AVF
#             devs = list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo)) + \
#                    list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeMuxed))
#             devs.sort(key=lambda d: str(d.uniqueID()))
#         except Exception as e:
#             print(f"Can't read macOS camera list ({e}). Run: pip install pyobjc-framework-AVFoundation")
#             devs = []
#         try:
#             import CoreMedia as CM
#         except Exception:
#             CM = None
#         for i, d in enumerate(devs):
#             print(f"[{i}] {d.localizedName()}")
#             for label, attr in (("model", "modelID"), ("maker", "manufacturer"), ("id", "uniqueID")):
#                 try:
#                     print(f"     {label}: {getattr(d, attr)()}")
#                 except Exception:
#                     pass
#             if CM is not None:
#                 seen = []
#                 for f in d.formats():
#                     try:
#                         desc = f.formatDescription()
#                         sub_ = _fourcc(CM.CMFormatDescriptionGetMediaSubType(desc))
#                         dims = CM.CMVideoFormatDescriptionGetDimensions(desc)
#                         item = f"{sub_} {dims.width}x{dims.height}"
#                     except Exception:
#                         item = str(f)[:60]
#                     if item not in seen:
#                         seen.append(item)
#                 print(f"     formats: {', '.join(seen) if seen else '(none reported)'}")
#             _report_opencv_frame(i)
#             print()
#         try:
#             import pyorbbecsdk  # noqa: F401
#             print("[o] Orbbec SDK (color)")
#             _report_opencv_frame(ORBBEC)
#         except ImportError:
#             print("Orbbec SDK not installed - the Gemini's COLOR camera isn't reachable on a Mac without it.")
#             print(MAC_SUDO_HINT)
#     else:
#         names, _ = _get_camera_names()
#         for i in range(CAMERA_MAX_INDEX):
#             name = names[i] if i < len(names) and names[i] else "?"
#             print(f"[{i}] {name}")
#             _report_opencv_frame(i)
#             print()


# def _report_opencv_frame(idx):
#     cap = open_camera(idx, quiet=(idx != ORBBEC))
#     if cap is None:
#         print("     can't open / no frame")
#         return
#     ok, frame = cap.read()
#     cap.release()
#     if not ok or frame is None:
#         print("     OpenCV: no frame")
#         return
#     colorfulness = _colorfulness(frame)
#     kind = "COLOR image" if colorfulness > 6 else "GREYSCALE image (depth/infrared?)"
#     print(f"     OpenCV: {frame.shape[1]}x{frame.shape[0]}, {kind} (color score {colorfulness:.1f})")
#     snap = f"camera_{'orbbec' if idx == ORBBEC else idx}_snapshot.png"
#     cv2.imwrite(snap, frame)
#     give_back_to_user(snap)
#     print(f"     saved {snap}")


# if __name__ == "__main__":
#     print_camera_report()