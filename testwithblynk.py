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
MODEL_PATH = "best.pt"  # Path to your YOLOv8 license plate model
CONFIDENCE_THRESHOLD = 0.3
NMS_IOU_THRESHOLD = 0.5
CAM_INDEX = 0  # Default webcam index
CSV_LOG_FILE = "plate_log.csv"
REGISTERED_PLATES = {"BAA4777BAGMATI", "BAG1234", "BBA5678"}  # Registered plates
COOLDOWN_SECONDS = 20  # Prevent duplicate log within this time

# === BLYNK CONFIGURATION ===
BLYNK_AUTH_TOKEN = "L6iTBLuvZ5MLkhmwG0HQb8Uu7KaiiwDY"  # Replace with your token
BLYNK_BASE_URL = "https://blynk.cloud/external/api/update?token={BLYNK_TOKEN}"

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

# === Helper: Update Blynk Virtual Pin ===
def update_blynk_virtual_pin(pin, value):
    try:
        url = f"{BLYNK_BASE_URL}/update?token={BLYNK_AUTH_TOKEN}&{pin}={value}"
        requests.get(url)
        print(f"[BLYNK] Updated {pin} to {value}")
    except Exception as e:
        print(f"[BLYNK ERROR] Failed to update {pin}: {e}")

# === VIDEO STREAM ===
cap = cv2.VideoCapture(CAM_INDEX)
if not cap.isOpened():
    raise RuntimeError("[ERROR] Cannot open webcam.")

print("[INFO] Starting License Plate Recognition. Press 'q' to quit.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("[ERROR] Failed to grab frame.")
        break

    results = model(frame)[0]

    # === DETECTION PARSING ===
    boxes = []
    confidences = []
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf = float(box.conf[0])
        if conf >= CONFIDENCE_THRESHOLD:
            boxes.append([x1, y1, x2 - x1, y2 - y1])
            confidences.append(conf)

    # === NMS FILTERING ===
    indices = cv2.dnn.NMSBoxes(boxes, confidences, CONFIDENCE_THRESHOLD, NMS_IOU_THRESHOLD)

    if len(indices) > 0:
        for i in indices.flatten():
            x, y, w, h = boxes[i]
            x2, y2 = x + w, y + h
            roi = frame[y:y2, x:x2]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

            # === OCR ===
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
                        status = "GRANTED" if clean_text in REGISTERED_PLATES else "DENIED"
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        # === DRAW OUTPUT ===
                        color = (0, 255, 0) if status == "GRANTED" else (0, 0, 255)
                        cv2.rectangle(frame, (x, y), (x2, y2), color, 2)
                        cv2.putText(frame, f"{clean_text} [{status}]", (x, max(y - 10, 20)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                        print(f"[YOLO + OCR] Plate: {clean_text} => {status}")

                        # === GATE TRIGGER & LOG ONLY IF GRANTED ===
                        if status == "GRANTED":
                            print(f"[GATE] Opening gate for: {clean_text}")
                            # requests.get("http://192.168.x.x/open")

                        # === LOG TO CSV ===
                        with open(CSV_LOG_FILE, mode='a', newline='') as f:
                            writer = csv.writer(f)
                            writer.writerow([clean_text, timestamp, status])

                        # === BLYNK NOTIFICATION & UPDATE ===
                        try:
                            message = f"Access {status}: {clean_text} at {timestamp}"
                            notify_url = f"{BLYNK_BASE_URL}/notify?token={BLYNK_AUTH_TOKEN}&message={requests.utils.quote(message)}"
                            requests.get(notify_url)

                            update_blynk_virtual_pin("V1", clean_text)
                            update_blynk_virtual_pin("V2", timestamp)
                            update_blynk_virtual_pin("V3", status)
                        except Exception as e:
                            print(f"[BLYNK ERROR] Notification or update failed: {e}")


                        # === BLYNK NOTIFICATION & UPDATE ===
                        try:
                            message = f"Access {status}: {clean_text} at {timestamp}"
                            notify_url = f"{BLYNK_BASE_URL}/notify?token={BLYNK_AUTH_TOKEN}&message={requests.utils.quote(message)}"
                            requests.get(notify_url)

                            # Virtual Pins: V1=Plate, V2=Time, V3=Status
                            update_blynk_virtual_pin("V1", clean_text)
                            update_blynk_virtual_pin("V2", timestamp)
                            update_blynk_virtual_pin("V3", status)
                        except Exception as e:
                            print(f"[BLYNK ERROR] Notification or update failed: {e}")

                    else:
                        print(f"[INFO] Skipped duplicate (cooldown): {clean_text}")
                else:
                    print("[INFO] Skipped short OCR result:", clean_text)
            else:
                print("[INFO] No OCR result found.")

    # === SHOW RESULT ===
    cv2.imshow("Live License Plate Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# === CLEAN UP ===
cap.release()
cv2.destroyAllWindows()
print("[INFO] Program ended.")


def log_to_server(plate):
    try:
        response = requests.post("http://127.0.0.1:5000/log_access", json={"plate": plate})
        print("Log response:", response.json())
    except Exception as e:
        print("Logging failed:", e)