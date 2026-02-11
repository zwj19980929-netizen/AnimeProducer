"""
LoRA API Routes - LoRA 训练管理 API

提供 LoRA 训练流水线的 RESTful API：
- 启动训练
- 查询状态
- 列出 LoRA
- 取消训练
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from api.deps import get_db
from core.lora_manager import lora_manager
from core.models import CharacterLoRA, LoRATrainingStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["LoRA Training"])


# ============================================================================
# Request/Response Schemas
# ============================================================================


class StartTrainingRequest(BaseModel):
    """启动训练请求"""
    character_id: str = Field(..., description="角色 ID")
    ancestor_image_path: Optional[str] = Field(None, description="始祖图路径（可选，不提供则使用锚定图）")
    image_ids: Optional[List[str]] = Field(None, description="指定用于训练的图片 ID 列表（可选）")
    use_selected_images: bool = Field(True, description="是否使用图片库中标记为训练的图片")
    num_dataset_images: int = Field(20, ge=10, le=50, description="数据集图片数量（当需要额外生成时）")
    training_steps: int = Field(1000, ge=500, le=3000, description="训练步数")
    provider: str = Field("fal", description="训练提供商: fal, replicate")


class LoRAResponse(BaseModel):
    """LoRA 响应"""
    id: str
    character_id: str
    trigger_word: str
    status: str
    progress: float
    lora_url: Optional[str]
    dataset_size: int
    training_provider: str
    error_message: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, lora: CharacterLoRA) -> "LoRAResponse":
        return cls(
            id=lora.id,
            character_id=lora.character_id,
            trigger_word=lora.trigger_word,
            status=lora.status.value,
            progress=lora.progress,
            lora_url=lora.lora_url,
            dataset_size=lora.dataset_size,
            training_provider=lora.training_provider,
            error_message=lora.error_message,
            created_at=lora.created_at.isoformat(),
            updated_at=lora.updated_at.isoformat(),
        )


class TrainingStatusResponse(BaseModel):
    """训练状态响应"""
    lora_id: str
    status: str
    progress: float
    lora_url: Optional[str]
    error_message: Optional[str]


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/train", response_model=LoRAResponse, status_code=status.HTTP_201_CREATED)
async def start_lora_training(
    request: StartTrainingRequest,
    db: Session = Depends(get_db)
):
    """
    启动 LoRA 训练

    训练图片来源（按优先级）：
    1. 如果指定了 image_ids，使用这些图片
    2. 如果 use_selected_images=True，使用图片库中标记为训练的图片
    3. 如果图片不足，基于锚定图自动生成补充图片
    4. 如果没有锚定图，使用 ancestor_image_path 或参考图
    """
    try:
        lora = lora_manager.start_lora_training(
            character_id=request.character_id,
            ancestor_image_path=request.ancestor_image_path,
            image_ids=request.image_ids,
            use_selected_images=request.use_selected_images,
            num_dataset_images=request.num_dataset_images,
            training_steps=request.training_steps,
            provider=request.provider,
            session=db
        )
        return LoRAResponse.from_model(lora)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting LoRA training: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start training: {str(e)}"
        )


@router.get("/{lora_id}", response_model=LoRAResponse)
async def get_lora(
    lora_id: str,
    db: Session = Depends(get_db)
):
    """获取 LoRA 详情"""
    lora = db.get(CharacterLoRA, lora_id)
    if not lora:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LoRA not found")
    return LoRAResponse.from_model(lora)


@router.get("/{lora_id}/status", response_model=TrainingStatusResponse)
async def check_training_status(
    lora_id: str,
    db: Session = Depends(get_db)
):
    """
    检查训练状态

    轮询云端训练任务状态，更新数据库记录。
    """
    try:
        lora = lora_manager.check_training_status(lora_id, session=db)
        return TrainingStatusResponse(
            lora_id=lora.id,
            status=lora.status.value,
            progress=lora.progress,
            lora_url=lora.lora_url,
            error_message=lora.error_message
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/character/{character_id}", response_model=List[LoRAResponse])
async def list_character_loras(
    character_id: str,
    db: Session = Depends(get_db)
):
    """列出角色的所有 LoRA"""
    loras = lora_manager.list_character_loras(character_id, session=db)
    return [LoRAResponse.from_model(lora) for lora in loras]


@router.get("/character/{character_id}/active", response_model=Optional[LoRAResponse])
async def get_active_lora(
    character_id: str,
    db: Session = Depends(get_db)
):
    """获取角色当前可用的 LoRA"""
    lora = lora_manager.get_character_lora(character_id, session=db)
    if not lora:
        return None
    return LoRAResponse.from_model(lora)


@router.post("/{lora_id}/cancel", response_model=dict)
async def cancel_training(
    lora_id: str,
    db: Session = Depends(get_db)
):
    """取消训练任务"""
    try:
        success = lora_manager.cancel_training(lora_id, session=db)
        return {"success": success, "message": "Training cancelled" if success else "Cannot cancel"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
