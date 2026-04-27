from datetime import datetime
from pydantic import BaseModel


# --- Tags ---
class TagBase(BaseModel):
    name: str

class TagOut(TagBase):
    id: int
    image_count: int = 0
    model_config = {"from_attributes": True}


# --- Categories ---
class CategoryBase(BaseModel):
    name: str

class CategoryOut(CategoryBase):
    id: int
    parent_id: int | None = None
    image_count: int = 0
    model_config = {"from_attributes": True}


# --- Image Tags / Categories ---
class ImageTagOut(BaseModel):
    tag_id: int
    tag_name: str
    model_config = {"from_attributes": True}

class ImageCategoryOut(BaseModel):
    category_id: int
    category_name: str
    model_config = {"from_attributes": True}


# --- Images ---
class FaceOut(BaseModel):
    id: int
    person_name: str | None = None
    description: str | None = None
    estimated_age: str | None = None
    gender: str | None = None
    position: str | None = None
    model_config = {"from_attributes": True}


class ImageSummary(BaseModel):
    id: int
    filename: str
    source_folder: str
    width: int | None = None
    height: int | None = None
    analyzed: bool
    thumbnail_path: str | None = None
    ai_description: str | None = None
    album: str | None = None
    favorite: bool = False
    date_taken: datetime | None = None
    location_name: str | None = None
    camera_model: str | None = None
    quality_flags: str | None = None  # JSON string
    is_video: bool = False
    created_at: datetime
    tags: list[ImageTagOut] = []
    categories: list[ImageCategoryOut] = []
    faces: list[FaceOut] = []
    model_config = {"from_attributes": True}

class ImageDetail(ImageSummary):
    file_path: str
    file_size: int | None = None
    file_hash: str | None = None
    orientation_corrected: bool
    gps_lat: float | None = None
    gps_lon: float | None = None
    lens_model: str | None = None
    aperture: float | None = None
    shutter_speed: str | None = None
    iso: int | None = None
    focal_length: float | None = None
    updated_at: datetime


class AlbumOut(BaseModel):
    name: str
    image_count: int
    thumbnail_image_id: int | None = None

class ImageListResponse(BaseModel):
    images: list[ImageSummary]
    total: int
    page: int
    page_size: int


# --- Scan ---
class ScanJobOut(BaseModel):
    id: int
    status: str
    source_folder: str | None = None
    total_images: int
    processed_images: int
    phase1_total: int = 0
    phase1_done: int = 0
    phase2_total: int = 0
    phase2_done: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    model_config = {"from_attributes": True}


# --- Stats ---
class StatsOut(BaseModel):
    total_images: int
    analyzed_images: int
    total_tags: int
    total_categories: int
    images_by_folder: dict[str, int]
    top_tags: list[dict]
    images_by_category: list[dict]
    phash_count: int = 0
    duplicate_groups: int = 0
    untagged_images: int = 0


# --- Request bodies ---
class TagUpdateRequest(BaseModel):
    tags: list[str]

class CategoryUpdateRequest(BaseModel):
    category: str
