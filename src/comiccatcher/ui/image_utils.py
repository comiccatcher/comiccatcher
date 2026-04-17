# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("comiccatcher.ui.image_utils")

# Toggle this to False if you want to revert to PyQt's faster but lower-quality scaling
USE_PILLOW_LANCZOS = True

def scale_image_to_bytes(data: bytes, max_width: int, max_height: int, quality: int = 85) -> Optional[bytes]:
    """
    Scales image bytes to fit within max_width/max_height while maintaining aspect ratio.
    If USE_PILLOW_LANCZOS is True, uses Pillow's high-quality Lanczos filter.
    Otherwise, uses PyQt6's SmoothTransformation.
    """
    if not data:
        return None

    if USE_PILLOW_LANCZOS:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            
            # Convert to RGB if necessary (e.g., CMYK or RGBA)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            
            # thumbnail() preserves aspect ratio and uses LANCZOS by default for downscaling
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            if img.mode == "RGBA":
                # Flatten RGBA to RGB with white background for JPEG compatibility
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
                
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=quality)
            return out.getvalue()
        except Exception as e:
            logger.error(f"Pillow scaling error: {e}")
            # Fall through to PyQt on failure

    # PyQt Fallback
    try:
        from PyQt6.QtGui import QImage
        from PyQt6.QtCore import Qt, QBuffer, QIODevice
        
        img = QImage()
        if not img.loadFromData(data):
            return None
            
        scaled = img.scaled(max_width, max_height, 
                          Qt.AspectRatioMode.KeepAspectRatio, 
                          Qt.TransformationMode.SmoothTransformation)
        
        ba = QBuffer()
        ba.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(ba, "JPEG", quality)
        return ba.data().data()
    except Exception as e:
        logger.error(f"PyQt scaling fallback error: {e}")
        return None

def scale_image_to_file(data: bytes, dest_path: Path, max_width: int, max_height: int, quality: int = 85) -> bool:
    """Scales image bytes and saves directly to a file path."""
    scaled_data = scale_image_to_bytes(data, max_width, max_height, quality)
    if scaled_data:
        try:
            dest_path.write_bytes(scaled_data)
            return True
        except Exception as e:
            logger.error(f"Failed to write scaled image to {dest_path}: {e}")
    return False
