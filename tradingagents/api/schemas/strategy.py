"""Strategy schemas."""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class StrategyCreate(BaseModel):
    """Schema for creating a new strategy."""

    name: str = Field(..., min_length=1, max_length=255, description="Strategy name")
    description: Optional[str] = Field(None, description="Strategy description")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Strategy parameters (JSON)")
    is_active: bool = Field(default=True, description="Whether strategy is active")

    model_config = {"json_schema_extra": {
        "example": {
            "name": "Moving Average Crossover",
            "description": "Simple MA crossover strategy",
            "parameters": {
                "short_window": 50,
                "long_window": 200
            },
            "is_active": True
        }
    }}


class StrategyUpdate(BaseModel):
    """Schema for updating an existing strategy."""

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Strategy name")
    description: Optional[str] = Field(None, description="Strategy description")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Strategy parameters (JSON)")
    is_active: Optional[bool] = Field(None, description="Whether strategy is active")

    model_config = {"json_schema_extra": {
        "example": {
            "name": "Updated Strategy Name",
            "is_active": False
        }
    }}


class StrategyResponse(BaseModel):
    """Schema for strategy response."""

    id: int = Field(..., description="Strategy ID")
    user_id: int = Field(..., description="User ID")
    name: str = Field(..., description="Strategy name")
    description: Optional[str] = Field(None, description="Strategy description")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Strategy parameters (JSON)")
    is_active: bool = Field(..., description="Whether strategy is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "user_id": 1,
                "name": "Moving Average Crossover",
                "description": "Simple MA crossover strategy",
                "parameters": {
                    "short_window": 50,
                    "long_window": 200
                },
                "is_active": True,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }
        }
    }


class StrategyListResponse(BaseModel):
    """Schema for paginated strategy list response."""

    items: List[StrategyResponse] = Field(..., description="List of strategies")
    total: int = Field(..., description="Total number of strategies")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum number of items returned")

    model_config = {"json_schema_extra": {
        "example": {
            "items": [
                {
                    "id": 1,
                    "user_id": 1,
                    "name": "Strategy 1",
                    "description": "Description 1",
                    "parameters": {},
                    "is_active": True,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z"
                }
            ],
            "total": 1,
            "skip": 0,
            "limit": 10
        }
    }}
