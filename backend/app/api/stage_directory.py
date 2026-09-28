from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query

from ..catalog import directory_for, object_types
from ..models import User
from ..schemas import StageDirectoryItem
from .dependencies import get_current_user


router = APIRouter(prefix="/stage-directory", tags=["stage-directory"])


@router.get("", response_model=List[StageDirectoryItem])
def get_stage_directory(
    object_type: str = Query(min_length=1, max_length=80),
    _user: User = Depends(get_current_user),
) -> List[StageDirectoryItem]:
    return [StageDirectoryItem.model_validate(item) for item in directory_for(object_type)]


@router.get("/object-types", response_model=List[str])
def get_object_types(_user: User = Depends(get_current_user)) -> List[str]:
    return object_types()
