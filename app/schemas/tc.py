"""
Pydantic schemas cho Transaction Certificates và Master Data
Pydantic schemas for Transaction Certificates and Master Data
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Supplier / Nhà cung cấp
# ─────────────────────────────────────────────────────────────────────────────

class SupplierCreate(BaseModel):
    code                    : str
    name                    : str
    address                 : Optional[str] = None
    country                 : Optional[str] = None
    certification_body      : Optional[str] = None
    scope_cert_number       : Optional[str] = None
    scope_cert_expiry       : Optional[date] = None
    certification_standards : Optional[str] = None   # "GRS,GOTS"
    contact_name            : Optional[str] = None
    contact_email           : Optional[str] = None
    contact_phone           : Optional[str] = None


class SupplierRead(SupplierCreate):
    model_config = ConfigDict(from_attributes=True)
    id         : int
    is_active  : bool
    created_at : datetime


# ─────────────────────────────────────────────────────────────────────────────
# Buyer / Khách hàng
# ─────────────────────────────────────────────────────────────────────────────

class BuyerCreate(BaseModel):
    code          : str
    name          : str
    address       : Optional[str] = None
    country       : Optional[str] = None
    contact_name  : Optional[str] = None
    contact_email : Optional[str] = None


class BuyerRead(BuyerCreate):
    model_config = ConfigDict(from_attributes=True)
    id         : int
    is_active  : bool
    created_at : datetime


# ─────────────────────────────────────────────────────────────────────────────
# Material / Vật liệu
# ─────────────────────────────────────────────────────────────────────────────

class MaterialCreate(BaseModel):
    code             : str
    name             : str
    category_id      : Optional[int]    = None
    unit             : str              = "kg"
    recycled_content : Optional[Decimal] = None
    color            : Optional[str]    = None
    composition      : Optional[str]    = None
    description      : Optional[str]    = None


class MaterialRead(MaterialCreate):
    model_config = ConfigDict(from_attributes=True)
    id        : int
    is_active : bool


# ─────────────────────────────────────────────────────────────────────────────
# Incoming TC / In TC
# ─────────────────────────────────────────────────────────────────────────────

class TCInCreate(BaseModel):
    tc_number              : str
    issue_date             : date
    expiry_date            : Optional[date]    = None
    supplier_id            : int
    material_id            : int
    material_description   : Optional[str]     = None
    certification_standard : str               = Field(..., pattern="^(GRS|GOTS|RCS|OCS)$")
    certified_quantity     : Decimal           = Field(..., gt=0)
    unit_price             : Optional[Decimal] = None
    currency               : str               = "USD"
    total_amount           : Optional[Decimal] = None
    invoice_number         : Optional[str]     = None
    po_number              : Optional[str]     = None
    shipment_date          : Optional[date]    = None
    received_date          : Optional[date]    = None
    certification_body     : Optional[str]     = None
    notes                  : Optional[str]     = None


class TCInUpdate(BaseModel):
    expiry_date        : Optional[date] = None
    received_date      : Optional[date] = None
    invoice_number     : Optional[str]  = None
    certification_body : Optional[str]  = None
    notes              : Optional[str]  = None


class TCInRead(TCInCreate):
    model_config = ConfigDict(from_attributes=True)
    id                 : int
    quantity_remaining : Decimal
    quantity_used      : Decimal
    usage_pct          : Decimal
    status             : str
    created_at         : datetime
    updated_at         : datetime

    # Denormalized for convenience
    supplier_name : Optional[str] = None
    material_name : Optional[str] = None
    material_code : Optional[str] = None


class TCInSummary(BaseModel):
    """Dùng trong dropdown và bảng tóm tắt / Used in dropdowns and summary tables"""
    model_config = ConfigDict(from_attributes=True)
    id                     : int
    tc_number              : str
    issue_date             : date
    supplier_name          : str
    material_name          : str
    certification_standard : str
    certified_quantity     : Decimal
    quantity_remaining     : Decimal
    status                 : str


# ─────────────────────────────────────────────────────────────────────────────
# Outgoing TC / Out TC
# ─────────────────────────────────────────────────────────────────────────────

class TCOutCreate(BaseModel):
    tc_number              : str
    issue_date             : date
    buyer_id               : int
    product_name           : str
    product_code           : Optional[str]     = None
    style_number           : Optional[str]     = None
    certification_standard : str               = Field(..., pattern="^(GRS|GOTS|RCS|OCS)$")
    certified_quantity     : Decimal           = Field(..., gt=0)
    unit_price             : Optional[Decimal] = None
    currency               : str               = "USD"
    total_amount           : Optional[Decimal] = None
    invoice_number         : Optional[str]     = None
    po_number              : Optional[str]     = None
    shipment_date          : Optional[date]    = None
    certification_body     : Optional[str]     = None
    notes                  : Optional[str]     = None


class TCOutUpdate(BaseModel):
    shipment_date      : Optional[date] = None
    invoice_number     : Optional[str]  = None
    certification_body : Optional[str]  = None
    notes              : Optional[str]  = None


class TCOutRead(TCOutCreate):
    model_config = ConfigDict(from_attributes=True)
    id         : int
    status     : str
    created_at : datetime
    updated_at : datetime

    buyer_name : Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# TC Linkage / Liên kết In TC ↔ Out TC
# ─────────────────────────────────────────────────────────────────────────────

class TCLinkageCreate(BaseModel):
    tc_in_id           : int
    tc_out_id          : int
    allocated_quantity : Decimal = Field(..., gt=0)
    notes              : Optional[str] = None


class TCLinkageRead(TCLinkageCreate):
    model_config = ConfigDict(from_attributes=True)
    id             : int
    allocation_pct : Optional[Decimal]
    created_at     : datetime

    # Denormalized
    tc_in_number   : Optional[str] = None
    tc_out_number  : Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# TCOut Issue request / Yêu cầu phát hành Out TC
# ─────────────────────────────────────────────────────────────────────────────

class TCInAllocation(BaseModel):
    """Một dòng cấp phát từ In TC khi phát hành Out TC"""
    tc_in_id           : int
    allocated_quantity : Decimal = Field(..., gt=0)
    notes              : Optional[str] = None


class TCOutIssueRequest(BaseModel):
    """
    Yêu cầu phát hành Out TC – phải kèm danh sách In TC nguồn
    Issue request for an Out TC – must include list of source In TCs

    Tổng allocated_quantity phải = tc_out.certified_quantity
    Total allocated_quantity must equal tc_out.certified_quantity
    """
    tc_out_id   : int
    allocations : List[TCInAllocation] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_allocations_not_empty(self) -> "TCOutIssueRequest":
        if not self.allocations:
            raise ValueError("Phải có ít nhất 1 In TC nguồn / At least 1 source In TC required")
        return self
