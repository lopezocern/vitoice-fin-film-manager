"""Perceptual hash service — for duplicate detection.

Reuses the approach from the old system's perceptual_hash.py but cleaned up.
Uses imagehash library for perceptual hashing of video thumbnails.
"""
import asyncio
import os

import imagehash
from PIL import Image
from sqlalchemy import select

from app.database import async_session
from app.models.media import Media


async def compute_perceptual_hash(image_path: str) -> str | None:
    """Compute perceptual hash (phash) of an image.

    Uses the imagehash library's phash — robust to resizing/compression.
    Returns a hex string, or None if the image can't be read.
    """
    def _compute():
        try:
            with Image.open(image_path) as img:
                return str(imagehash.phash(img))
        except (OSError, ValueError):
            return None

    return await asyncio.to_thread(_compute)


async def find_duplicates(library_id: int | None = None) -> list[tuple[int, int, float]]:
    """Find duplicate media by perceptual hash similarity.

    Returns list of (media_id_1, media_id_2, similarity) tuples where
    similarity is the Hamming distance (0 = identical, lower = more similar).
    """
    async with async_session() as session:
        query = select(Media.id, Media.thumbnail_path).where(
            Media.thumbnail_path.is_not(None)
        )
        if library_id is not None:
            query = query.where(Media.library_id == library_id)

        result = await session.execute(query)
        items = result.fetchall()

    if len(items) < 2:
        return []

    # Compute hashes
    hashes: dict[int, str] = {}
    for media_id, thumb_path in items:
        if thumb_path and os.path.exists(thumb_path):
            phash = await compute_perceptual_hash(thumb_path)
            if phash:
                hashes[media_id] = phash

    # Compare all pairs
    duplicates = []
    media_ids = list(hashes.keys())
    for i in range(len(media_ids)):
        for j in range(i + 1, len(media_ids)):
            id1, id2 = media_ids[i], media_ids[j]
            h1 = imagehash.hex_to_hash(hashes[id1])
            h2 = imagehash.hex_to_hash(hashes[id2])
            distance = h1 - h2  # Hamming distance
            if distance <= 5:  # Threshold: distance <= 5 considered similar
                duplicates.append((id1, id2, distance))

    return duplicates
