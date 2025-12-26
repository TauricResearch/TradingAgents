"""Strategy CRUD routes."""

from typing import List, Union
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from tradingagents.api.database import get_db
from tradingagents.api.dependencies import get_current_user
from tradingagents.api.models import User, Strategy
from tradingagents.api.schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    StrategyListResponse,
)


router = APIRouter(prefix="/strategies", tags=["Strategies"])


@router.get("", response_model=Union[List[StrategyResponse], StrategyListResponse])
async def list_strategies(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of items to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Union[List[StrategyResponse], StrategyListResponse]:
    """
    List all strategies for the current user.

    Args:
        skip: Number of items to skip (pagination)
        limit: Maximum number of items to return
        current_user: Current authenticated user
        db: Database session

    Returns:
        List of strategies or paginated response
    """
    # Get total count
    count_result = await db.execute(
        select(func.count(Strategy.id)).where(Strategy.user_id == current_user.id)
    )
    total = count_result.scalar_one()

    # Get strategies with pagination
    result = await db.execute(
        select(Strategy)
        .where(Strategy.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
        .order_by(Strategy.created_at.desc())
    )
    strategies = result.scalars().all()

    # Convert to response models
    items = [StrategyResponse.model_validate(strategy) for strategy in strategies]

    # Return paginated response if pagination params were provided
    if skip > 0 or limit < 100:
        return StrategyListResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit
        )

    # Return simple list for backward compatibility
    return items


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    strategy_data: StrategyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> StrategyResponse:
    """
    Create a new strategy for the current user.

    Args:
        strategy_data: Strategy creation data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Created strategy
    """
    # Create new strategy
    strategy = Strategy(
        user_id=current_user.id,
        name=strategy_data.name,
        description=strategy_data.description,
        parameters=strategy_data.parameters,
        is_active=strategy_data.is_active,
    )

    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)

    return StrategyResponse.model_validate(strategy)


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> StrategyResponse:
    """
    Get a single strategy by ID.

    Args:
        strategy_id: Strategy ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Strategy details

    Raises:
        HTTPException: If strategy not found or not owned by user
    """
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )

    # Ensure user owns the strategy
    if strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )

    return StrategyResponse.model_validate(strategy)


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    strategy_data: StrategyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> StrategyResponse:
    """
    Update an existing strategy.

    Args:
        strategy_id: Strategy ID
        strategy_data: Strategy update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated strategy

    Raises:
        HTTPException: If strategy not found or not owned by user
    """
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )

    # Ensure user owns the strategy
    if strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )

    # Update fields
    update_data = strategy_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(strategy, field, value)

    await db.commit()
    await db.refresh(strategy)

    return StrategyResponse.model_validate(strategy)


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Delete a strategy.

    Args:
        strategy_id: Strategy ID
        current_user: Current authenticated user
        db: Database session

    Raises:
        HTTPException: If strategy not found or not owned by user
    """
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )

    # Ensure user owns the strategy
    if strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )

    await db.delete(strategy)
    await db.commit()
