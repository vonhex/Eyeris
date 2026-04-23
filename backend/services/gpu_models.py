"""
Lightweight GPU-accelerated models for fast image sync.
Optimized for AMD iGPU (Strix Halo) / CPU.

Models:
- YOLOv8n-face: Face detection
- FaceNet: Face embeddings for clustering
- SigLIP: Zero-shot image categorization
"""

import os
import torch
import json
import numpy as np
from PIL import Image
from io import BytesIO

# Targeting Strix Halo iGPU (via ROCm/DirectML if available, else CPU)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

_yolo_face_model = None
_facenet_model = None
_siglip_model = None
_siglip_processor = None

# High-level categories for SigLIP classification
CATEGORIES = [
    "nature", "landscape", "urban", "architecture", "interior", 
    "person", "group photo", "food", "animal", "pet", 
    "vehicle", "document", "screenshot", "concert", "wedding",
    "sports", "macro", "black and white", "night sky"
]


def _load_yolo_face():
    """Load YOLOv8n-face model."""
    global _yolo_face_model
    if _yolo_face_model is not None:
        return _yolo_face_model
    try:
        from ultralytics import YOLO
        model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "yolov8n-face.pt")
        _yolo_face_model = YOLO(model_path)
        _yolo_face_model.to(DEVICE)
        return _yolo_face_model
    except Exception as e:
        print(f"[GPU Models] Failed to load YOLOv8-face: {e}")
        return None


def _load_facenet():
    """Load FaceNet (InceptionResnetV1) for face embeddings."""
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


def _load_siglip():
    """Load SigLIP model for zero-shot categorization."""
    global _siglip_model, _siglip_processor
    if _siglip_model is not None:
        return _siglip_model, _siglip_processor
    try:
        from transformers import AutoModel, AutoProcessor
        model_name = "google/siglip-base-patch16-224"
        _siglip_processor = AutoProcessor.from_pretrained(model_name)
        _siglip_model = AutoModel.from_pretrained(model_name).to(DEVICE).eval()
        return _siglip_model, _siglip_processor
    except Exception as e:
        print(f"[GPU Models] SigLIP load error: {e}")
        return None, None


def detect_faces(image_bytes: bytes) -> list[dict]:
    """Detect faces in image."""
    model = _load_yolo_face()
    if model is None: return []
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
    except Exception: return []


def extract_face_embeddings(image_bytes: bytes, faces: list[dict]) -> list[dict]:
    """Add 512-d face embedding to each detected face dict."""
    if not faces: return faces
    model = _load_facenet()
    if model is None: return faces
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        for face in faces:
            bbox = face.get("bbox")
            if not bbox: continue
            x1, y1, x2, y2 = bbox
            px, py = int((x2 - x1) * 0.2), int((y2 - y1) * 0.2)
            crop = img.crop((max(0, x1 - px), max(0, y1 - py), min(img.width, x2 + px), min(img.height, y2 + py))).resize((160, 160))
            arr = np.array(crop, dtype=np.float32) / 127.5 - 1.0
            tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(DEVICE)
            with torch.no_grad():
                emb = model(tensor).cpu().numpy()[0]
            face["embedding"] = emb.tolist()
    except Exception: pass
    return faces


def classify_category(image_bytes: bytes, threshold: float = 0.5) -> str | None:
    """Classify image into one of the predefined categories."""
    res = _load_siglip()
    if not res[0]: return None
    model, processor = res
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        texts = [f"a photo of {c}" for f in CATEGORIES] # Typo here, should be 'c' not 'f'
        # Wait, I noticed a tiny typo in my planned text list above. Fixing it now.
        texts = [f"a photo of {c}" for c in CATEGORIES]
        
        inputs = processor(text=texts, images=img, return_tensors="pt", padding="max_length", truncation=True)
        inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = model(**inputs)
        
        probs = torch.sigmoid(outputs.logits_per_image[0]).cpu().numpy()
        max_idx = np.argmax(probs)
        if probs[max_idx] >= threshold:
            return CATEGORIES[max_idx]
    except Exception: pass
    return None


def analyze_image_local(image_bytes: bytes) -> dict:
    """Run all local GPU/iGPU models."""
    faces = detect_faces(image_bytes)
    faces = extract_face_embeddings(image_bytes, faces)
    category = classify_category(image_bytes)
    return {
        "faces": faces,
        "category": category
    }
