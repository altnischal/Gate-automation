import cv2
import easyocr
from ultralytics import YOLO
import re
import csv
from datetime import datetime
import os
import time
from collections import defaultdict
import requests

# === CONFIGURATION ===
MODEL_PATH = "best.pt"
CONFIDENCE_THRESHOLD = 0.3
NMS_IOU_THRESHOLD = 0.5
CAM_INDEX = 0
CSV_LOG_FILE = "plate_log.csv"
COOLDOWN_SECONDS = 20

# === INIT MODELS ===
model = YOLO(MODEL_PATH)
reader = easyocr.Reader(['en'], gpu=False)

# === CSV SETUP ===
if not os.path.exists(CSV_LOG_FILE):
    with open(CSV_LOG_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Plate", "Datetime", "Status"])

# === TRACK LAST DETECTION TIME ===
last_logged_time = defaultdict(lambda: 0)

# === Send log to backend ===
def log_to_server(plate):
    try:
        response = requests.post("http://127.0.0.1:5000/log_access", json={"plate": plate})
        print("Flask response:", response.json())
        return response.json().get("status", "Unknown")
    except Exception as e:
        print("[ERROR] Failed to log to server:", e)
        return "Unknown"

# === VIDEO STREAM ===
cap = cv2.VideoCapture(CAM_INDEX)
if not cap.isOpened():
    raise RuntimeError("[ERROR] Cannot open webcam.")

print("[INFO] Running headless license plate recognition... Press Ctrl+C to stop.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Failed to grab frame.")
            break

        results = model(frame)[0]
        boxes = []
        confidences = []

        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            if conf >= CONFIDENCE_THRESHOLD:
                boxes.append([x1, y1, x2 - x1, y2 - y1])
                confidences.append(conf)

        indices = cv2.dnn.NMSBoxes(boxes, confidences, CONFIDENCE_THRESHOLD, NMS_IOU_THRESHOLD)

        if len(indices) > 0:
            for i in indices.flatten():
                x, y, w, h = boxes[i]
                x2, y2 = x + w, y + h
                roi = frame[y:y2, x:x2]
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

                ocr_results = reader.readtext(gray)
                if ocr_results:
                    sorted_ocr = sorted(ocr_results, key=lambda x: x[0][0][0])
                    combined_text = ' '.join([text for (_, text, _) in sorted_ocr])
                    clean_text = re.sub(r'[^A-Z0-9]', '', combined_text.upper())

                    if len(clean_text) >= 5:
                        current_time = time.time()
                        last_time = last_logged_time.get(clean_text, 0)

                        if current_time - last_time >= COOLDOWN_SECONDS:
                            last_logged_time[clean_text] = current_time
                            status = log_to_server(clean_text)
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                            with open(CSV_LOG_FILE, mode='a', newline='') as f:
                                writer = csv.writer(f)
                                writer.writerow([clean_text, timestamp, status])

                            if status == "Authorized":
                                print(f"[GATE] Opening gate for: {clean_text}")
                                # requests.get("http://192.168.x.x/open")

                            print(f"[LOG] Plate: {clean_text} => {status}")
                        else:
                            print(f"[INFO] Skipped (cooldown): {clean_text}")
                    else:
                        print("[INFO] Skipped short OCR result:", clean_text)
                else:
                    print("[INFO] No OCR result found.")

        time.sleep(0.1)  # Slight delay to reduce CPU usage

except KeyboardInterrupt:
    print("\n[INFO] Stopped by user.")

finally:
    cap.release()
    print("[INFO] Camera released and program ended.")
