# Copyright (c) 2026 Lekkalu
from typing import Literal

from pydantic import BaseModel


class MatchResult(BaseModel):
    status: Literal["matched", "ambiguous", "not_found"]
    customer_id: int | None = None  # set only when matched
    candidate_ids: list[int] = []  # set only when ambiguous


class DuplicateCustomer(Exception):
    """A customer with this normalized name already exists in the business."""
