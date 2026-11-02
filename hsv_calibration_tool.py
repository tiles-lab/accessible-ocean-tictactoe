"""
HSV calibration tool.
- Point your camera at a cube face.
- Click any pixel on it to sample its HSV value.
- Hold 'r', 'd', 'f', 's' to set which habitat you're calibrating:
    r = Rippled sand
    d = Dense live bottom
    f = Flat sand
    s = Sparse live bottom
- Press SPACE to add the current sample to that habitat's list.
- Press 'v' to switch to the next camera.
- Orbbec Gemini color camera only - adjust the picture if it looks too bright/dark:
    [ / ]  exposure down / up      ; / '  gain down / up
    , / .  brightness down / up    e      auto-exposure on/off
  Settings are saved to camera_settings.json and used by the game too.
  Adjust the picture FIRST, then take your color samples.
- Press 'p' to print the final recommended ranges to the terminal.
- Press ESC to quit.
"""

import cv2
import numpy as np
import json
import os
from camera_select import (start_camera, switch_to_next_camera, camera_label, give_back_to_user,
                           handle_camera_key, camera_settings_text, CAMERA_KEYS_HELP)

# None = ask at launch which camera to use. Or always use one camera:
#   "orbbec"   -> the Orbbec Gemini's color camera (on a Mac it's found by name - no sudo needed)
#   "FaceTime" -> any camera whose name contains that text
#   1          -> camera number 1 (on a Mac numbers can change, names are safer)
# The command line wins over this:  python hsv_calibration_tool.py --camera orbbec
CAMERA_INDEX = None

HABITATS = {
    'r': "Rippled sand",
    'd': "Dense live bottom",
    'f': "Flat sand",
    's': "Sparse live bottom",
}

samples = {name: [] for name in HABITATS.values()}
current_habitat = None
last_hsv        = None
last_pos        = (0, 0)

def on_click(event, x, y, flags, param):
    global last_hsv, last_pos
    if event == cv2.EVENT_LBUTTONDOWN:
        hsv_frame = cv2.cvtColor(param[0], cv2.COLOR_BGR2HSV)
        # average a small patch around the click for stability
        patch = hsv_frame[max(0,y-5):y+5, max(0,x-5):x+5]
        if patch.size > 0:
            last_hsv = patch.reshape(-1, 3).mean(axis=0).astype(int)
            last_pos = (x, y)
            print(f"  Sampled HSV: {last_hsv}  (habitat: {current_habitat or 'none selected'})")

cap, camera_idx = start_camera(CAMERA_INDEX)

cv2.namedWindow("HSV Picker")

frame_holder = [None]
cv2.setMouseCallback("HSV Picker", on_click, frame_holder)

print("\nControls:")
print("  r = select Rippled sand")
print("  d = select Dense live bottom")
print("  f = select Flat sand")
print("  s = select Sparse live bottom")
print("  SPACE = save current sample to selected habitat")
print("  p     = print recommended HSV ranges")
print("  v     = switch to the next camera")
print(f"  Picture (Orbbec): {CAMERA_KEYS_HELP}")
print("  ESC   = quit\n")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_holder[0] = frame.copy()

    # Draw crosshair at last click
    if last_hsv is not None:
        x, y = last_pos
        cv2.drawMarker(frame, (x, y), (0, 255, 255), cv2.MARKER_CROSS, 20, 2)
        h, s, v = last_hsv
        cv2.putText(frame, f"HSV: ({h}, {s}, {v})", (x + 12, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    # Status bar
    hab_label = current_habitat if current_habitat else "-- none --"
    cv2.putText(frame, f"Selected: {hab_label}   |   {camera_label(camera_idx)}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    cam_text = camera_settings_text(cap)
    if cam_text:
        cv2.putText(frame, f"{cam_text}   ({CAMERA_KEYS_HELP})", (20, 105),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    # Highlight blown-out (pure white) pixels in red, so over-exposure is easy to spot.
    blown = (frame_holder[0] >= 250).all(axis=2)
    if blown.any():
        frame[blown] = (0, 0, 255)
        cv2.putText(frame, f"Red = over-exposed ({blown.mean():.0%} of image)", (20, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    counts = "  |  ".join(f"{k}: {len(v)}" for k, v in samples.items())
    cv2.putText(frame, f"Samples  {counts}", (20, 75),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)

    cv2.putText(frame, "Click cube, SPACE to save, p to print ranges, v next camera, ESC quit",
                (20, frame.shape[0] - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

    cv2.imshow("HSV Picker", frame)
    key = cv2.waitKey(1) & 0xFF

    if key == 27:   # ESC
        break
    elif handle_camera_key(cap, key) is not None:
        pass   # picture setting changed (message printed in the terminal)
    elif key in (ord('v'), ord('V')):
        cap, camera_idx = switch_to_next_camera(cap, camera_idx)
        if cap is None:
            break
        last_hsv = None   # the old click position means nothing on the new view
    elif key in [ord(k) for k in HABITATS]:
        current_habitat = HABITATS[chr(key)]
        print(f">> Now calibrating: {current_habitat}")
    elif key == ord(' '):
        if current_habitat and last_hsv is not None:
            samples[current_habitat].append(last_hsv.tolist())
            print(f"  Saved sample {len(samples[current_habitat])} for {current_habitat}: {last_hsv}")
        else:
            print("  (select a habitat key first, then click a pixel)")
    elif key == ord('p'):
        print("\n========== RECOMMENDED HSV RANGES ==========")
        print("Copy these into your COLOR_HSV_RANGES dict:\n")
        for name, pts in samples.items():
            if len(pts) < 2:
                print(f"  {name!r}: not enough samples (need >= 2)")
                continue
            arr     = np.array(pts)
            padding = np.array([8, 40, 40])   # generous padding
            lower   = np.clip(arr.min(axis=0) - padding, 0, 255)
            upper   = np.clip(arr.max(axis=0) + padding, 0, 255)
            print(f'    "{name}": (np.array({lower.tolist()}), np.array({upper.tolist()})),')
        print("=============================================\n")
        ranges = {}
        for name, pts in samples.items():
            if len(pts) < 2:
                continue
            arr     = np.array(pts)
            padding = np.array([8, 40, 40])
            lower   = np.clip(arr.min(axis=0) - padding, 0, 255)
            upper   = np.clip(arr.max(axis=0) + padding, 0, 255)
            ranges[name] = [lower.tolist(), upper.tolist()]

        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hsv_ranges.json")
        with open(out_path, "w") as f:
            json.dump(ranges, f, indent=2)
        give_back_to_user(out_path)   # keep it editable after a sudo run
        print(f"Saved {len(ranges)} habitat ranges to {out_path}")

if cap is not None:
    cap.release()
cv2.destroyAllWindows()


# # try1:

#     "Rippled sand": (np.array([5, 125, 167]), np.array([22, 216, 252])),
#     "Dense live bottom": (np.array([69, 4, 108]), np.array([89, 96, 198])),
#     "Flat sand": (np.array([10, 90, 204]), np.array([27, 176, 255])),
#     "Sparse live bottom": (np.array([81, 18, 182]), np.array([100, 107, 255]))

# salle de reunion TILES lab:

# "Rippled sand": (np.array([7, 1, 55]), np.array([28, 136, 173])),
#     "Dense live bottom": (np.array([85, 102, 50]), np.array([104, 249, 167])),
#     "Flat sand": (np.array([37, 0, 104]), np.array([76, 84, 241])),
#     "Sparse live bottom": (np.array([87, 135, 90]), np.array([105, 255, 255])),

# "Rippled sand": (np.array([8, 99, 91]), np.array([26, 218, 194])),
#     "Dense live bottom": (np.array([34, 0, 41]), np.array([98, 179, 232])),
#     "Flat sand": (np.array([14, 53, 146]), np.array([33, 179, 255])),
#     "Sparse live bottom": (np.array([78, 66, 54]), np.array([103, 207, 255])),

# """
# HSV calibration tool.
# - Point your camera at a cube face.
# - Click any pixel on it to sample its HSV value.
# - Hold 'r', 'd', 'f', 's' to set which habitat you're calibrating:
#     r = Rippled sand
#     d = Dense live bottom
#     f = Flat sand
#     s = Sparse live bottom
# - Press SPACE to add the current sample to that habitat's list.
# - Press 'v' to switch to the next camera.
# - Press 'p' to print the final recommended ranges to the terminal.
# - Press ESC to quit.
# """

# import cv2
# import numpy as np
# import json
# import os
# from camera_select import start_camera, switch_to_next_camera, camera_label, give_back_to_user

# # None = ask at launch which camera to use. Or always use one camera:
# #   "orbbec"   -> the Orbbec Gemini's color camera (on a Mac it's found by name - no sudo needed)
# #   "FaceTime" -> any camera whose name contains that text
# #   1          -> camera number 1 (on a Mac numbers can change, names are safer)
# # The command line wins over this:  python hsv_calibration_tool.py --camera orbbec
# CAMERA_INDEX = None

# HABITATS = {
#     'r': "Rippled sand",
#     'd': "Dense live bottom",
#     'f': "Flat sand",
#     's': "Sparse live bottom",
# }

# samples = {name: [] for name in HABITATS.values()}
# current_habitat = None
# last_hsv        = None
# last_pos        = (0, 0)

# def on_click(event, x, y, flags, param):
#     global last_hsv, last_pos
#     if event == cv2.EVENT_LBUTTONDOWN:
#         hsv_frame = cv2.cvtColor(param[0], cv2.COLOR_BGR2HSV)
#         # average a small patch around the click for stability
#         patch = hsv_frame[max(0,y-5):y+5, max(0,x-5):x+5]
#         if patch.size > 0:
#             last_hsv = patch.reshape(-1, 3).mean(axis=0).astype(int)
#             last_pos = (x, y)
#             print(f"  Sampled HSV: {last_hsv}  (habitat: {current_habitat or 'none selected'})")

# cap, camera_idx = start_camera(CAMERA_INDEX)

# cv2.namedWindow("HSV Picker")

# frame_holder = [None]
# cv2.setMouseCallback("HSV Picker", on_click, frame_holder)

# print("\nControls:")
# print("  r = select Rippled sand")
# print("  d = select Dense live bottom")
# print("  f = select Flat sand")
# print("  s = select Sparse live bottom")
# print("  SPACE = save current sample to selected habitat")
# print("  p     = print recommended HSV ranges")
# print("  v     = switch to the next camera")
# print("  ESC   = quit\n")

# while True:
#     ret, frame = cap.read()
#     if not ret:
#         break

#     frame_holder[0] = frame.copy()

#     # Draw crosshair at last click
#     if last_hsv is not None:
#         x, y = last_pos
#         cv2.drawMarker(frame, (x, y), (0, 255, 255), cv2.MARKER_CROSS, 20, 2)
#         h, s, v = last_hsv
#         cv2.putText(frame, f"HSV: ({h}, {s}, {v})", (x + 12, y - 8),
#                     cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

#     # Status bar
#     hab_label = current_habitat if current_habitat else "-- none --"
#     cv2.putText(frame, f"Selected: {hab_label}   |   {camera_label(camera_idx)}", (20, 40),
#                 cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

#     counts = "  |  ".join(f"{k}: {len(v)}" for k, v in samples.items())
#     cv2.putText(frame, f"Samples  {counts}", (20, 75),
#                 cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)

#     cv2.putText(frame, "Click cube, SPACE to save, p to print ranges, v next camera, ESC quit",
#                 (20, frame.shape[0] - 15),
#                 cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

#     cv2.imshow("HSV Picker", frame)
#     key = cv2.waitKey(1) & 0xFF

#     if key == 27:   # ESC
#         break
#     elif key in (ord('v'), ord('V')):
#         cap, camera_idx = switch_to_next_camera(cap, camera_idx)
#         if cap is None:
#             break
#         last_hsv = None   # the old click position means nothing on the new view
#     elif key in [ord(k) for k in HABITATS]:
#         current_habitat = HABITATS[chr(key)]
#         print(f">> Now calibrating: {current_habitat}")
#     elif key == ord(' '):
#         if current_habitat and last_hsv is not None:
#             samples[current_habitat].append(last_hsv.tolist())
#             print(f"  Saved sample {len(samples[current_habitat])} for {current_habitat}: {last_hsv}")
#         else:
#             print("  (select a habitat key first, then click a pixel)")
#     elif key == ord('p'):
#         print("\n========== RECOMMENDED HSV RANGES ==========")
#         print("Copy these into your COLOR_HSV_RANGES dict:\n")
#         for name, pts in samples.items():
#             if len(pts) < 2:
#                 print(f"  {name!r}: not enough samples (need >= 2)")
#                 continue
#             arr     = np.array(pts)
#             padding = np.array([8, 40, 40])   # generous padding
#             lower   = np.clip(arr.min(axis=0) - padding, 0, 255)
#             upper   = np.clip(arr.max(axis=0) + padding, 0, 255)
#             print(f'    "{name}": (np.array({lower.tolist()}), np.array({upper.tolist()})),')
#         print("=============================================\n")
#         ranges = {}
#         for name, pts in samples.items():
#             if len(pts) < 2:
#                 continue
#             arr     = np.array(pts)
#             padding = np.array([8, 40, 40])
#             lower   = np.clip(arr.min(axis=0) - padding, 0, 255)
#             upper   = np.clip(arr.max(axis=0) + padding, 0, 255)
#             ranges[name] = [lower.tolist(), upper.tolist()]

#         out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hsv_ranges.json")
#         with open(out_path, "w") as f:
#             json.dump(ranges, f, indent=2)
#         give_back_to_user(out_path)   # keep it editable after a sudo run
#         print(f"Saved {len(ranges)} habitat ranges to {out_path}")

# if cap is not None:
#     cap.release()
# cv2.destroyAllWindows()


# # # try1:

# #     "Rippled sand": (np.array([5, 125, 167]), np.array([22, 216, 252])),
# #     "Dense live bottom": (np.array([69, 4, 108]), np.array([89, 96, 198])),
# #     "Flat sand": (np.array([10, 90, 204]), np.array([27, 176, 255])),
# #     "Sparse live bottom": (np.array([81, 18, 182]), np.array([100, 107, 255]))

# # salle de reunion TILES lab:

# # "Rippled sand": (np.array([7, 1, 55]), np.array([28, 136, 173])),
# #     "Dense live bottom": (np.array([85, 102, 50]), np.array([104, 249, 167])),
# #     "Flat sand": (np.array([37, 0, 104]), np.array([76, 84, 241])),
# #     "Sparse live bottom": (np.array([87, 135, 90]), np.array([105, 255, 255])),

# # "Rippled sand": (np.array([8, 99, 91]), np.array([26, 218, 194])),
# #     "Dense live bottom": (np.array([34, 0, 41]), np.array([98, 179, 232])),
# #     "Flat sand": (np.array([14, 53, 146]), np.array([33, 179, 255])),
# #     "Sparse live bottom": (np.array([78, 66, 54]), np.array([103, 207, 255])),