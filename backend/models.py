from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship

from database import Base


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_path = Column(String(1024), nullable=False, unique=True)
    source_folder = Column(String(255), nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=True)
    file_hash = Column(String(64), nullable=True, index=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    orientation_corrected = Column(Boolean, default=False)
    thumbnail_path = Column(String(1024), nullable=True)
    analyzed = Column(Boolean, default=False, index=True)
    ai_description = Column(Text, nullable=True)
    album = Column(String(255), nullable=True, index=True)
    face_count = Column(Integer, nullable=True, default=0)
    favorite = Column(Boolean, default=False, nullable=False, server_default="0")
    perceptual_hash = Column(String(64), nullable=True, index=True)
    date_taken = Column(DateTime, nullable=True)
    # EXIF / location metadata
    gps_lat = Column(Float, nullable=True)
    gps_lon = Column(Float, nullable=True)
    camera_model = Column(String(255), nullable=True)
    location_name = Column(String(255), nullable=True, index=True)
    # Quality analysis flags (JSON: {"blur": bool, "overexposed": bool, "underexposed": bool, "blur_score": float})
    quality_flags = Column(Text, nullable=True)
    is_video = Column(Boolean, default=False, nullable=False, server_default="0", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tags = relationship("ImageTag", back_populates="image", cascade="all, delete-orphan")
    categories = relationship("ImageCategory", back_populates="image", cascade="all, delete-orphan")
    faces = relationship("Face", back_populates="image", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    images = relationship("ImageTag", back_populates="tag")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship("Category", remote_side=[id])
    images = relationship("ImageCategory", back_populates="category")


class ImageTag(Base):
    __tablename__ = "image_tags"

    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    image = relationship("Image", back_populates="tags")
    tag = relationship("Tag", back_populates="images")


class ImageCategory(Base):
    __tablename__ = "image_categories"

    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)

    image = relationship("Image", back_populates="categories")
    category = relationship("Category", back_populates="images")


class Face(Base):
    __tablename__ = "faces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True)
    person_name = Column(String(255), nullable=True, index=True)
    cluster_id = Column(Integer, nullable=True, index=True)
    description = Column(String(512), nullable=True)
    estimated_age = Column(String(20), nullable=True)
    gender = Column(String(20), nullable=True)
    position = Column(String(50), nullable=True)
    face_bbox = Column(String(100), nullable=True)   # JSON "[x1,y1,x2,y2]"
    embedding = Column(Text, nullable=True)           # JSON array of floats
    crop_path = Column(String(512), nullable=True)
    ignored = Column(Boolean, default=False, nullable=False, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow)

    image = relationship("Image", back_populates="faces")


class ImageTagBlock(Base):
    """Tags that must never be auto-applied to a specific image by the scanner."""
    __tablename__ = "image_tag_blocks"

    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)
    tag_name = Column(String(255), nullable=False, primary_key=True)


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(50), default="pending", index=True)  # pending, listing, running, analyzing, completed, failed
    source_folder = Column(String(255), nullable=True)
    total_images = Column(Integer, default=0)
    processed_images = Column(Integer, default=0)
    phase1_total = Column(Integer, default=0)
    phase1_done = Column(Integer, default=0)
    phase2_total = Column(Integer, default=0)
    phase2_done = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
