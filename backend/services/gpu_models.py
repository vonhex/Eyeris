import os
import torch
import json
import numpy as np
from PIL import Image
from io import BytesIO

def _get_device():
    if torch.cuda.is_available():
        return "cuda"
    # Future-proofing: Check for ROCm (AMD) or other backends if torch is compiled for them
    # ROCm usually presents as 'cuda' in torch if the environment is correct,
    # but we can explicitly check for others here.
    return "cpu"

DEVICE = _get_device()

_yolo_face_model = None
_facenet_model = None


def _load_yolo_face():
    global _yolo_face_model
    if _yolo_face_model is not None:
        return _yolo_face_model
    try:
        from ultralytics import YOLO
        # Try local path first, then fall back to name for auto-download
        model_name = "yolov8n-face.pt"
        local_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), model_name)
        
        if os.path.exists(local_path):
            _yolo_face_model = YOLO(local_path)
        else:
            print(f"[GPU Models] Local {model_name} not found, attempting auto-download...")
            _yolo_face_model = YOLO(model_name)
            
        _yolo_face_model.to(DEVICE)
        return _yolo_face_model
    except Exception as e:
        print(f"[GPU Models] Failed to load YOLOv8-face: {e}")
        return None


def _load_facenet():
    global _facenet_model
    if _facenet_model is not None:
        return _facenet_model
    try:
        from facenet_pytorch import InceptionResnetV1
        _facenet_model = InceptionResnetV1(pretrained="vggface2").eval().to(DEVICE)
        return _facenet_model
    except Exception as e:
        print(f"[GPU Models] FaceNet load error: {e}")
        return None


def detect_faces(image_bytes: bytes) -> list[dict]:
    model = _load_yolo_face()
    if model is None:
        return []
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        results = model.predict(img, conf=0.4, verbose=False, device=DEVICE)
        faces = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                center_x = (x1 + x2) / 2 / img.width
                position = "left" if center_x < 0.33 else "right" if center_x > 0.66 else "center"
                faces.append({
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "confidence": float(box.conf[0]),
                    "position": position,
                })
        return faces
    except Exception:
        return []


def extract_face_embeddings(image_bytes: bytes, faces: list[dict]) -> list[dict]:
    if not faces:
        return faces
    model = _load_facenet()
    if model is None:
        return faces
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        for face in faces:
            bbox = face.get("bbox")
            if not bbox:
                continue
            x1, y1, x2, y2 = bbox
            px, py = int((x2 - x1) * 0.2), int((y2 - y1) * 0.2)
            crop = img.crop((
                max(0, x1 - px), max(0, y1 - py),
                min(img.width, x2 + px), min(img.height, y2 + py)
            )).resize((160, 160))
            arr = np.array(crop, dtype=np.float32) / 127.5 - 1.0
            tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(DEVICE)
            with torch.no_grad():
                emb = model(tensor).cpu().numpy()[0]
            face["embedding"] = emb.tolist()
    except Exception:
        pass
    return faces


def analyze_image_local(image_bytes: bytes) -> dict:
    faces = detect_faces(image_bytes)
    faces = extract_face_embeddings(image_bytes, faces)
    return {"faces": faces}
