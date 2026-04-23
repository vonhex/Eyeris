import hashlib
import json
import os
import uuid
import xml.etree.ElementTree as ET
from io import BytesIO
from datetime import datetime

from PIL import Image, ExifTags

from config import settings

# EXIF orientation tag ID
ORIENTATION_TAG = None
for tag, name in ExifTags.TAGS.items():
    if name == "Orientation":
        ORIENTATION_TAG = tag
        break


def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def correct_orientation(img: Image.Image) -> tuple[Image.Image, bool]:
    """Auto-rotate image based on EXIF orientation. Returns (image, was_corrected)."""
    try:
        exif = img.getexif()
        if not exif or ORIENTATION_TAG not in exif:
            return img, False

        orientation = exif[ORIENTATION_TAG]
        rotations = {
            3: Image.Transpose.ROTATE_180,
            6: Image.Transpose.ROTATE_270,
            8: Image.Transpose.ROTATE_90,
        }
        # Mirrored orientations
        mirror_rotations = {
            2: (Image.Transpose.FLIP_LEFT_RIGHT, None),
            4: (Image.Transpose.FLIP_TOP_BOTTOM, None),
            5: (Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.ROTATE_270),
            7: (Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.ROTATE_90),
        }

        if orientation in rotations:
            return img.transpose(rotations[orientation]), True
        elif orientation in mirror_rotations:
            first, second = mirror_rotations[orientation]
            img = img.transpose(first)
            if second:
                img = img.transpose(second)
            return img, True

        return img, False
    except Exception:
        return img, False


def extract_date_taken(img: Image.Image) -> datetime | None:
    """Extract date taken from EXIF data."""
    try:
        exif = img.getexif()
        if not exif:
            return None
        # DateTimeOriginal (36867), DateTimeDigitized (36868), DateTime (306)
        for tag_id in (36867, 36868, 306):
            if tag_id in exif:
                val = exif[tag_id]
                # Reject sentinel/invalid values
                if not val or val.startswith("0000") or ":00:" in val[:8]:
                    continue
                try:
                    return datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    continue
    except Exception:
        pass
    return None


def _rational_to_float(rational) -> float:
    """Convert an EXIF rational (numerator, denominator) to float."""
    try:
        if hasattr(rational, "numerator"):
            return rational.numerator / rational.denominator
        return float(rational[0]) / float(rational[1])
    except Exception:
        return 0.0


def extract_gps(img: Image.Image) -> tuple[float | None, float | None]:
    """Extract GPS latitude and longitude from EXIF. Returns (lat, lon) or (None, None)."""
    try:
        gps_info = img.getexif().get_ifd(34853)  # GPSInfo IFD
        if not gps_info:
            return None, None

        def dms_to_decimal(dms, ref: str) -> float | None:
            try:
                d = _rational_to_float(dms[0])
                m = _rational_to_float(dms[1])
                s = _rational_to_float(dms[2])
                val = d + (m / 60.0) + (s / 3600.0)
                if ref in ("S", "W"):
                    val = -val
                return val
            except Exception:
                return None

        lat = dms_to_decimal(gps_info.get(2), gps_info.get(1, "N"))
        lon = dms_to_decimal(gps_info.get(4), gps_info.get(3, "E"))
        return lat, lon
    except Exception:
        return None, None


def extract_camera_model(img: Image.Image) -> str | None:
    """Extract camera make + model from EXIF."""
    try:
        exif = img.getexif()
        if not exif:
            return None
        make = (exif.get(271) or "").strip()
        model = (exif.get(272) or "").strip()
        if not make and not model:
            return None
        # Avoid duplicating make in model string (e.g. "Apple iPhone 15" not "Apple Apple iPhone 15")
        if make and model.startswith(make):
            return model
        return f"{make} {model}".strip() if make else model
    except Exception:
        return None


def generate_thumbnail(img: Image.Image) -> str:
    """Create a thumbnail and save to disk. Returns the thumbnail filename."""
    thumb = img.copy()
    thumb.thumbnail(settings.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

    filename = f"{uuid.uuid4().hex}.jpg"
    path = os.path.join(settings.THUMBNAIL_DIR, filename)

    # Convert to RGB if necessary (e.g., RGBA PNGs)
    if thumb.mode in ("RGBA", "P", "LA"):
        thumb = thumb.convert("RGB")

    thumb.save(path, "JPEG", quality=85)
    return filename


def parse_xmp_metadata(xmp_data: bytes) -> dict:
    """
    Parse an XMP sidecar file to extract tags, description, and date taken.
    Returns a dict with:
      - tags: list[str]
      - description: str
      - album: str
      - date_taken: datetime | None
    """
    tags = []
    description = ""
    album = ""
    date_taken = None

    try:
        # XMP uses namespaces; we need to handle them for ElementTree
        ns = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "dc": "http://purl.org/dc/elements/1.1/",
            "xmp": "http://ns.adobe.com/xap/1.0/",
            "tiff": "http://ns.adobe.com/tiff/1.0/",
            "digiKam": "http://www.digikam.org/ns/1.0/",
        }

        root = ET.fromstring(xmp_data)

        # 1. Extract Tags (dc:subject)
        for bag in root.findall(".//dc:subject/rdf:Bag", ns):
            for li in bag.findall("rdf:li", ns):
                if li.text:
                    tags.append(li.text.strip())

        # 2. Extract Description (dc:description fallback to tiff:ImageDescription)
        # Check dc:description first
        for alt in root.findall(".//dc:description/rdf:Alt", ns):
            for li in alt.findall("rdf:li", ns):
                if li.text:
                    description = li.text.strip()
                    break
        
        # Fallback to tiff:ImageDescription
        if not description:
            tiff_desc = root.find(".//tiff:ImageDescription", ns)
            if tiff_desc is not None and tiff_desc.text:
                description = tiff_desc.text.strip()

        # 3. Extract Album (digiKam:Album or xmp:Album)
        dk_album = root.find(".//digiKam:Album", ns)
        if dk_album is not None and dk_album.text:
            album = dk_album.text.strip()
        else:
            xmp_album = root.find(".//xmp:Album", ns)
            if xmp_album is not None and xmp_album.text:
                album = xmp_album.text.strip()

        # 4. Extract Date Taken (xmp:CreateDate)
        # Format: YYYY-MM-DDTHH:MM:SS
        create_date = root.find(".//xmp:CreateDate", ns)
        if create_date is not None and create_date.text:
            try:
                dt_str = create_date.text.strip()
                # Handle formats like 2023-05-15T12:00:00 or 2023-05-15T12:00:00.000
                if "T" in dt_str:
                    fmt = "%Y-%m-%dT%H:%M:%S"
                    # Strip any sub-second or timezone offset for simplicity
                    dt_str = dt_str.split(".")[0].split("+")[0].split("Z")[0]
                    date_taken = datetime.strptime(dt_str, fmt)
            except Exception:
                pass

    except Exception as e:
        print(f"[XMP] Parse error: {e}")

    return {
        "tags": tags,
        "description": description,
        "album": album,
        "date_taken": date_taken,
    }


def process_image_bytes(data: bytes) -> dict:
    """
    Process raw image bytes: correct orientation, generate thumbnail, extract metadata.
    Returns a dict with all extracted info.
    """
    file_hash = compute_hash(data)

    img = Image.open(BytesIO(data))
    img, orientation_corrected = correct_orientation(img)

    # Read EXIF from original (before orientation correction strips tags)
    original = Image.open(BytesIO(data))
    date_taken = extract_date_taken(original)
    gps_lat, gps_lon = extract_gps(original)
    camera_model = extract_camera_model(original)

    # No analysis performed in Viewer-only mode
    location_name = None
    quality_flags = json.dumps({"blur": False, "blur_score": 0.0, "overexposed": False, "underexposed": False})

    width, height = img.size
    thumbnail_filename = generate_thumbnail(img)

    return {
        "img": img,  # Return the PIL object for further tasks (like face cropping)
        "file_hash": file_hash,
        "width": width,
        "height": height,
        "orientation_corrected": orientation_corrected,
        "thumbnail_path": thumbnail_filename,
        "date_taken": date_taken,
        "gps_lat": gps_lat,
        "gps_lon": gps_lon,
        "camera_model": camera_model,
        "location_name": location_name,
        "quality_flags": quality_flags,
    }


