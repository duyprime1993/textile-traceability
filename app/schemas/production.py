"""
Pydantic schemas cho sản xuất và kho
Pydantic schemas for production and stock operations
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Production Stage / Công đoạn sản xuất
# ─────────────────────────────────────────────────────────────────────────────

class ProductionStageCreate(BaseModel):
    batch_id        : int
    stage           : str  = Field(..., pattern="^(cutting|sewing|packing)$")
    stage_date      : date
    input_quantity  : Decimal = Field(..., gt=0)
    output_quantity : Decimal = Field(..., ge=0)
    loss_reason     : Optional[str] = None
    operator_name   : Optional[str] = None
    verified_by     : Optional[str] = None
    notes           : Optional[str] = None

    @model_validator(mode="after")
    def validate_output_lte_input(self) -> "ProductionStageCreate":
        if self.output_quantity > self.input_quantity:
            raise ValueError(
                f"output_quantity ({self.output_quantity}) không thể lớn hơn "
                f"input_quantity ({self.input_quantity})"
            )
        return self


class ProductionStageRead(ProductionStageCreate):
    model_config = ConfigDict(from_attributes=True)
    id           : int
    loss_quantity : Decimal
    loss_pct      : Decimal
    yield_pct     : Decimal
    created_at    : datetime


# ─────────────────────────────────────────────────────────────────────────────
# Production Batch / Lô sản xuất
# ─────────────────────────────────────────────────────────────────────────────

class ProductionBatchCreate(BaseModel):
    batch_number       : str
    product_name       : str
    product_code       : Optional[str]     = None
    style_number       : Optional[str]     = None
    order_number       : Optional[str]     = None
    tc_in_id           : Optional[int]     = None
    planned_input_qty  : Optional[Decimal] = Field(default=None, gt=0)
    planned_output_qty : Optional[Decimal] = Field(default=None, gt=0)
    start_date         : date
    end_date           : Optional[date]    = None
    notes              : Optional[str]     = None


class ProductionBatchUpdate(BaseModel):
    end_date           : Optional[date]    = None
    actual_input_qty   : Optional[Decimal] = None
    actual_output_qty  : Optional[Decimal] = None
    status             : Optional[str]     = None
    notes              : Optional[str]     = None


class ProductionBatchRead(ProductionBatchCreate):
    model_config = ConfigDict(from_attributes=True)
    id                : int
    actual_input_qty  : Optional[Decimal]
    actual_output_qty : Optional[Decimal]
    total_loss_kg     : Optional[Decimal]
    total_loss_pct    : Optional[Decimal]
    status            : str
    created_at        : datetime
    updated_at        : datetime

    # Related
    tc_in_number      : Optional[str] = None
    stages            : List[ProductionStageRead] = []


# ─────────────────────────────────────────────────────────────────────────────
# Stock Transaction / Giao dịch kho
# ─────────────────────────────────────────────────────────────────────────────

class StockTransactionCreate(BaseModel):
    transaction_date : date
    transaction_type : str
    material_id      : int
    quantity         : Decimal    # positive = in, negative = out
    quantity_type    : str        = "certified"
    tc_in_id         : Optional[int] = None
    tc_out_id        : Optional[int] = None
    batch_id         : Optional[int] = None
    stage_id         : Optional[int] = None
    reference_number : Optional[str] = None
    notes            : Optional[str] = None


class StockTransactionRead(StockTransactionCreate):
    model_config = ConfigDict(from_attributes=True)
    id              : int
    running_balance : Optional[Decimal]
    created_at      : datetime

    material_code   : Optional[str] = None
    material_name   : Optional[str] = None
