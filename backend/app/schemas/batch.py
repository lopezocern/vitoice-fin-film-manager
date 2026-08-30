"""Batch operation schemas."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class BatchActionRequest(BaseModel):
    """Request body for POST /api/media/batch."""
    action: Literal[
        "tag", "untag", "rating", "delete", "move", "rename",
        "metadata_ignore", "scrape", "thumbnail", "export"
    ]
    media_ids: list[int] = Field(..., min_length=1, max_length=1000)
    params: dict[str, Any] = {}

    # Action-specific params:
    # tag:       { tag_ids: [1,2,3] }
    # untag:     { tag_ids: [1,2] } or { all: true }
    # rating:    { rating: 1-5 }
    # delete:    { permanent: false }  (soft delete by default)
    # move:      { target_library_id: 5 }
    # rename:    { template: "{title} ({year})" , start_index: 1 }
    # metadata_ignore: { ignored: true }  (false = restore)
    # scrape:    {} (async — creates task)
    # thumbnail: {} (async — creates task)
    # export:    { format: "json" | "csv" }


class BatchFailedItem(BaseModel):
    """Details of a single failed item in a batch operation."""
    id: int
    error: str


class BatchActionResponse(BaseModel):
    """Response for batch operations."""
    action: str
    total: int
    success_count: int
    failed: list[BatchFailedItem] = []
    task_id: int | None = None      # For async operations (scrape/thumbnail)
    export_url: str | None = None    # For export operation
    message: str = ""
