"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   Volume Reconciliation & Material Traceability System                       ║
║   SQLAlchemy 2.0 Models – GRS / GOTS / RCS / OCS Compliant                 ║
║                                                                              ║
║   Tác giả / Author : Senior Full-Stack + Textile Compliance Expert           ║
║   Chuẩn / Standard : Textile Exchange GRS 4.0, GOTS 6.0                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

ER Diagram (text) – xem cuối file / see bottom of file for ER diagram
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
import enum

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum,
    ForeignKey, Index, Integer, JSON, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, MappedColumn, mapped_column, relationship,
)


# ─────────────────────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """Base class cho tất cả models / Base class for all models"""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Enums  (dùng String trong DB để dễ đọc khi audit / stored as String for audit readability)
# ─────────────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    """Vai trò người dùng / User roles"""
    ADMIN         = "admin"           # Quản trị hệ thống
    FACTORY_STAFF = "factory_staff"   # Nhân viên nhà máy
    QC            = "qc"              # Kiểm soát chất lượng
    AUDITOR       = "auditor"         # Kiểm toán viên (read-only)


class CertStandard(str, enum.Enum):
    """Tiêu chuẩn chứng nhận / Certification standards"""
    GRS  = "GRS"   # Global Recycled Standard
    GOTS = "GOTS"  # Global Organic Textile Standard
    RCS  = "RCS"   # Recycled Claim Standard
    OCS  = "OCS"   # Organic Content Standard


class TCInStatus(str, enum.Enum):
    """Trạng thái In TC / Incoming TC status"""
    ACTIVE          = "active"
    PARTIALLY_USED  = "partially_used"
    FULLY_USED      = "fully_used"
    EXPIRED         = "expired"
    CANCELLED       = "cancelled"


class TCOutStatus(str, enum.Enum):
    """Trạng thái Out TC / Outgoing TC status"""
    DRAFT     = "draft"    # Nháp
    ISSUED    = "issued"   # Đã phát hành
    CANCELLED = "cancelled"


class BatchStatus(str, enum.Enum):
    """Trạng thái lô sản xuất / Production batch status"""
    PLANNED     = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    CANCELLED   = "cancelled"


class StageType(str, enum.Enum):
    """Công đoạn sản xuất / Production stage type"""
    CUTTING = "cutting"  # Cắt
    SEWING  = "sewing"   # May
    PACKING = "packing"  # Đóng gói


class TxType(str, enum.Enum):
    """Loại giao dịch kho / Stock transaction type"""
    TC_IN_RECEIPT    = "tc_in_receipt"    # Nhập kho từ In TC
    ISSUE_CUTTING    = "issue_cutting"    # Xuất cho Cắt
    CUTTING_OUTPUT   = "cutting_output"   # Nhập từ đầu ra Cắt
    CUTTING_LOSS     = "cutting_loss"     # Ghi nhận hao hụt Cắt
    ISSUE_SEWING     = "issue_sewing"     # Xuất cho May
    SEWING_OUTPUT    = "sewing_output"    # Nhập từ đầu ra May
    SEWING_LOSS      = "sewing_loss"      # Ghi nhận hao hụt May
    ISSUE_PACKING    = "issue_packing"    # Xuất cho Đóng gói
    PACKING_OUTPUT   = "packing_output"   # Nhập từ đầu ra Đóng gói
    PACKING_LOSS     = "packing_loss"     # Ghi nhận hao hụt Đóng gói
    TC_OUT_SALE      = "tc_out_sale"      # Bán với Out TC
    NORMAL_SALE      = "normal_sale"      # Bán thường (không TC)
    ADJUSTMENT       = "adjustment"       # Điều chỉnh kiểm kê
    RETURN_IN        = "return_in"        # Hàng trả lại (nhận về)
    RETURN_OUT       = "return_out"       # Trả hàng cho NCC


class BalanceStatus(str, enum.Enum):
    """Trạng thái Mass Balance / Mass Balance reconciliation status"""
    PASS    = "PASS"     # Đạt – chênh lệch ≤ 0.5%
    WARNING = "WARNING"  # Cảnh báo – chênh lệch 0.5–2%
    FAIL    = "FAIL"     # Không đạt – chênh lệch > 2%
    PENDING = "PENDING"  # Chưa tính


class QtyType(str, enum.Enum):
    """Loại số lượng / Quantity type"""
    CERTIFIED     = "certified"
    NON_CERTIFIED = "non_certified"


# ─────────────────────────────────────────────────────────────────────────────
# Users / Người dùng
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    """
    Người dùng hệ thống – hỗ trợ multi-role cho Factory, QC và Auditor
    System users – multi-role support for Factory, QC, and Auditor access
    """
    __tablename__ = "users"

    id            : Mapped[int]            = mapped_column(primary_key=True)
    username      : Mapped[str]            = mapped_column(String(50),  unique=True, nullable=False)
    email         : Mapped[str]            = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str]           = mapped_column(String(255), nullable=False)
    full_name     : Mapped[Optional[str]]  = mapped_column(String(100))
    role          : Mapped[str]            = mapped_column(String(20),  nullable=False, default=UserRole.FACTORY_STAFF)
    is_active     : Mapped[bool]           = mapped_column(Boolean, default=True)
    last_login    : Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at    : Mapped[datetime]       = mapped_column(DateTime, server_default=func.now())
    updated_at    : Mapped[datetime]       = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    tc_ins_created  : Mapped[List["TCIn"]]           = relationship(back_populates="creator",   foreign_keys="TCIn.created_by")
    tc_outs_created : Mapped[List["TCOut"]]          = relationship(back_populates="creator",   foreign_keys="TCOut.created_by")
    batches_created : Mapped[List["ProductionBatch"]] = relationship(back_populates="creator",  foreign_keys="ProductionBatch.created_by")
    audit_logs      : Mapped[List["AuditLog"]]       = relationship(back_populates="user")


# ─────────────────────────────────────────────────────────────────────────────
# Suppliers / Nhà cung cấp
# ─────────────────────────────────────────────────────────────────────────────

class Supplier(Base):
    """
    Nhà cung cấp vật liệu có chứng nhận
    Certified material suppliers (must hold valid Scope Certificate)
    """
    __tablename__ = "suppliers"

    id                       : Mapped[int]           = mapped_column(primary_key=True)
    code                     : Mapped[str]           = mapped_column(String(50),  unique=True, nullable=False)
    name                     : Mapped[str]           = mapped_column(String(200), nullable=False)
    address                  : Mapped[Optional[str]] = mapped_column(Text)
    country                  : Mapped[Optional[str]] = mapped_column(String(100))

    # Chứng nhận của NCC / Supplier's own certification
    certification_body       : Mapped[Optional[str]] = mapped_column(String(100))  # Control Union, Bureau Veritas…
    scope_cert_number        : Mapped[Optional[str]] = mapped_column(String(100))  # SC number
    scope_cert_expiry        : Mapped[Optional[date]] = mapped_column(Date)
    certification_standards  : Mapped[Optional[str]] = mapped_column(String(200))  # "GRS,GOTS"

    # Liên hệ / Contact
    contact_name  : Mapped[Optional[str]] = mapped_column(String(100))
    contact_email : Mapped[Optional[str]] = mapped_column(String(100))
    contact_phone : Mapped[Optional[str]] = mapped_column(String(50))

    is_active  : Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at : Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    tc_ins : Mapped[List["TCIn"]] = relationship(back_populates="supplier")


# ─────────────────────────────────────────────────────────────────────────────
# Buyers / Khách hàng
# ─────────────────────────────────────────────────────────────────────────────

class Buyer(Base):
    """Khách hàng mua sản phẩm có chứng nhận / Certified product buyers"""
    __tablename__ = "buyers"

    id            : Mapped[int]            = mapped_column(primary_key=True)
    code          : Mapped[str]            = mapped_column(String(50),  unique=True, nullable=False)
    name          : Mapped[str]            = mapped_column(String(200), nullable=False)
    address       : Mapped[Optional[str]]  = mapped_column(Text)
    country       : Mapped[Optional[str]]  = mapped_column(String(100))
    contact_name  : Mapped[Optional[str]]  = mapped_column(String(100))
    contact_email : Mapped[Optional[str]]  = mapped_column(String(100))
    is_active     : Mapped[bool]           = mapped_column(Boolean, default=True)
    created_at    : Mapped[datetime]       = mapped_column(DateTime, server_default=func.now())

    # Relationships
    tc_outs : Mapped[List["TCOut"]] = relationship(back_populates="buyer")


# ─────────────────────────────────────────────────────────────────────────────
# Materials / Vật liệu
# ─────────────────────────────────────────────────────────────────────────────

class MaterialCategory(Base):
    """Danh mục loại vật liệu / Material type categories"""
    __tablename__ = "material_categories"

    id                    : Mapped[int]            = mapped_column(primary_key=True)
    code                  : Mapped[str]            = mapped_column(String(50),  unique=True, nullable=False)
    name                  : Mapped[str]            = mapped_column(String(100), nullable=False)
    fiber_type            : Mapped[Optional[str]]  = mapped_column(String(100))   # Polyester / Cotton / Nylon…
    certification_standard: Mapped[Optional[str]]  = mapped_column(String(20))    # GRS / GOTS
    min_recycled_content  : Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))  # Minimum % by standard
    description           : Mapped[Optional[str]]  = mapped_column(Text)

    # Relationships
    materials : Mapped[List["Material"]] = relationship(back_populates="category")


class Material(Base):
    """
    Vật liệu cụ thể (vải, sợi…) được theo dõi trong hệ thống
    Specific material items tracked through the supply chain
    """
    __tablename__ = "materials"

    id               : Mapped[int]             = mapped_column(primary_key=True)
    code             : Mapped[str]             = mapped_column(String(100), unique=True, nullable=False)
    name             : Mapped[str]             = mapped_column(String(200), nullable=False)
    category_id      : Mapped[Optional[int]]   = mapped_column(ForeignKey("material_categories.id"))
    unit             : Mapped[str]             = mapped_column(String(20), default="kg")
    recycled_content : Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))   # % recycled content
    color            : Mapped[Optional[str]]   = mapped_column(String(50))
    composition      : Mapped[Optional[str]]   = mapped_column(String(200))       # "100% rPET"
    description      : Mapped[Optional[str]]   = mapped_column(Text)
    is_active        : Mapped[bool]            = mapped_column(Boolean, default=True)

    # Relationships
    category          : Mapped[Optional["MaterialCategory"]] = relationship(back_populates="materials")
    tc_ins            : Mapped[List["TCIn"]]               = relationship(back_populates="material")
    stock_transactions: Mapped[List["StockTransaction"]]   = relationship(back_populates="material")
    mb_periods        : Mapped[List["MassBalancePeriod"]]  = relationship(back_populates="material")

    __table_args__ = (
        Index("ix_material_code", "code"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Transaction Certificates / Chứng nhận giao dịch
# ─────────────────────────────────────────────────────────────────────────────

class TCIn(Base):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  IN TC  – Transaction Certificate Đầu vào                               │
    │  Xác nhận mua vật liệu có chứng nhận từ nhà cung cấp                   │
    │  Certifies the purchase of certified material from a supplier            │
    │                                                                          │
    │  Ràng buộc quan trọng / Key constraints:                                │
    │  • quantity_remaining phải ≤ certified_quantity                          │
    │  • Tổng allocated_quantity trong tc_linkage ≤ certified_quantity        │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    __tablename__ = "tc_in"

    id           : Mapped[int]  = mapped_column(primary_key=True)
    tc_number    : Mapped[str]  = mapped_column(String(100), unique=True, nullable=False)
    issue_date   : Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date  : Mapped[Optional[date]] = mapped_column(Date)

    # Parties
    supplier_id  : Mapped[int]  = mapped_column(ForeignKey("suppliers.id"), nullable=False)

    # Material
    material_id         : Mapped[int]           = mapped_column(ForeignKey("materials.id"), nullable=False)
    material_description: Mapped[Optional[str]] = mapped_column(Text)   # Mô tả trên TC gốc / As stated on TC

    # Certification
    certification_standard : Mapped[str]     = mapped_column(String(20), nullable=False)
    certified_quantity     : Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    # Số lượng còn lại – tự động cập nhật khi tạo linkage
    # Automatically updated when creating TC linkages
    quantity_remaining     : Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)

    # Financials / Tài chính
    unit_price   : Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    currency     : Mapped[str]               = mapped_column(String(10), default="USD")
    total_amount : Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))

    # Reference documents / Chứng từ
    invoice_number  : Mapped[Optional[str]] = mapped_column(String(100))
    po_number       : Mapped[Optional[str]] = mapped_column(String(100))
    shipment_date   : Mapped[Optional[date]] = mapped_column(Date)
    received_date   : Mapped[Optional[date]] = mapped_column(Date)
    certification_body: Mapped[Optional[str]] = mapped_column(String(100))

    status     : Mapped[str]            = mapped_column(String(20), default=TCInStatus.ACTIVE)
    notes      : Mapped[Optional[str]]  = mapped_column(Text)
    created_by : Mapped[Optional[int]]  = mapped_column(ForeignKey("users.id"))
    created_at : Mapped[datetime]       = mapped_column(DateTime, server_default=func.now())
    updated_at : Mapped[datetime]       = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    supplier           : Mapped["Supplier"]              = relationship(back_populates="tc_ins")
    material           : Mapped["Material"]              = relationship(back_populates="tc_ins")
    creator            : Mapped[Optional["User"]]        = relationship(back_populates="tc_ins_created", foreign_keys=[created_by])
    linkages           : Mapped[List["TCLinkage"]]       = relationship(back_populates="tc_in", cascade="all, delete-orphan")
    production_batches : Mapped[List["ProductionBatch"]] = relationship(back_populates="tc_in")
    stock_transactions : Mapped[List["StockTransaction"]]= relationship(back_populates="tc_in")

    __table_args__ = (
        Index("ix_tc_in_number",   "tc_number"),
        Index("ix_tc_in_supplier", "supplier_id"),
        Index("ix_tc_in_date",     "issue_date"),
        CheckConstraint("certified_quantity > 0",                                     name="chk_tc_in_qty_positive"),
        CheckConstraint("quantity_remaining >= 0",                                    name="chk_tc_in_remaining_nonneg"),
        CheckConstraint("quantity_remaining <= certified_quantity",                   name="chk_tc_in_remaining_lte"),
    )

    # ── Computed properties (không lưu DB, tính khi cần) ────────────────────

    @property
    def quantity_used(self) -> Decimal:
        """Kg đã cấp phát / Quantity already allocated"""
        return self.certified_quantity - self.quantity_remaining

    @property
    def usage_pct(self) -> Decimal:
        """% đã sử dụng / Usage percentage"""
        if self.certified_quantity > 0:
            return (self.quantity_used / self.certified_quantity) * Decimal("100")
        return Decimal("0")

    @property
    def is_expired(self) -> bool:
        return bool(self.expiry_date and date.today() > self.expiry_date)

    def __repr__(self) -> str:
        return f"<TCIn {self.tc_number} | {self.certified_quantity} kg | {self.status}>"


class TCOut(Base):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  OUT TC  – Transaction Certificate Đầu ra                               │
    │  Xác nhận bán sản phẩm có chứng nhận cho khách hàng                    │
    │  Certifies the sale of certified finished goods to a buyer               │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    __tablename__ = "tc_out"

    id           : Mapped[int]  = mapped_column(primary_key=True)
    tc_number    : Mapped[str]  = mapped_column(String(100), unique=True, nullable=False)
    issue_date   : Mapped[date] = mapped_column(Date, nullable=False)

    # Buyer
    buyer_id : Mapped[int] = mapped_column(ForeignKey("buyers.id"), nullable=False)

    # Product
    product_name  : Mapped[str]            = mapped_column(String(200), nullable=False)
    product_code  : Mapped[Optional[str]]  = mapped_column(String(100))
    style_number  : Mapped[Optional[str]]  = mapped_column(String(100))

    # Certification
    certification_standard : Mapped[str]     = mapped_column(String(20), nullable=False)
    certified_quantity     : Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)

    # Financials
    unit_price   : Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    currency     : Mapped[str]               = mapped_column(String(10), default="USD")
    total_amount : Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))

    # Reference documents
    invoice_number    : Mapped[Optional[str]]  = mapped_column(String(100))
    po_number         : Mapped[Optional[str]]  = mapped_column(String(100))
    shipment_date     : Mapped[Optional[date]] = mapped_column(Date)
    certification_body: Mapped[Optional[str]]  = mapped_column(String(100))

    status     : Mapped[str]           = mapped_column(String(20), default=TCOutStatus.DRAFT)
    notes      : Mapped[Optional[str]] = mapped_column(Text)
    created_by : Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at : Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())
    updated_at : Mapped[datetime]      = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    buyer              : Mapped["Buyer"]               = relationship(back_populates="tc_outs")
    creator            : Mapped[Optional["User"]]      = relationship(back_populates="tc_outs_created", foreign_keys=[created_by])
    linkages           : Mapped[List["TCLinkage"]]     = relationship(back_populates="tc_out", cascade="all, delete-orphan")
    stock_transactions : Mapped[List["StockTransaction"]] = relationship(back_populates="tc_out")

    __table_args__ = (
        Index("ix_tc_out_number", "tc_number"),
        Index("ix_tc_out_buyer",  "buyer_id"),
        CheckConstraint("certified_quantity > 0", name="chk_tc_out_qty_positive"),
    )

    def __repr__(self) -> str:
        return f"<TCOut {self.tc_number} | {self.certified_quantity} kg | {self.status}>"


class TCLinkage(Base):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  TC LINKAGE  – Liên kết In TC → Out TC                                  │
    │  1 In TC có thể cấp nguồn cho NHIỀU Out TC (mass balance split)         │
    │  1 In TC can source MULTIPLE Out TCs                                    │
    │                                                                          │
    │  Đây là bảng trọng tâm để kiểm toán GRS chain-of-custody               │
    │  This is the core table for GRS chain-of-custody audit                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    __tablename__ = "tc_linkage"

    id                  : Mapped[int]            = mapped_column(primary_key=True)
    tc_in_id            : Mapped[int]            = mapped_column(ForeignKey("tc_in.id"),  nullable=False)
    tc_out_id           : Mapped[int]            = mapped_column(ForeignKey("tc_out.id"), nullable=False)
    # Kg từ In TC này được cấp cho Out TC này
    # kg from this In TC allocated to this Out TC
    allocated_quantity  : Mapped[Decimal]        = mapped_column(Numeric(15, 3), nullable=False)
    allocation_pct      : Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))   # % of In TC certified_qty
    notes               : Mapped[Optional[str]]  = mapped_column(Text)
    created_by          : Mapped[Optional[int]]  = mapped_column(ForeignKey("users.id"))
    created_at          : Mapped[datetime]       = mapped_column(DateTime, server_default=func.now())

    # Relationships
    tc_in  : Mapped["TCIn"]  = relationship(back_populates="linkages")
    tc_out : Mapped["TCOut"] = relationship(back_populates="linkages")

    __table_args__ = (
        UniqueConstraint("tc_in_id", "tc_out_id", name="uq_tc_linkage"),
        CheckConstraint("allocated_quantity > 0", name="chk_linkage_qty_positive"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Production / Sản xuất
# ─────────────────────────────────────────────────────────────────────────────

class ProductionBatch(Base):
    """
    Lô sản xuất – đơn vị theo dõi Mass Balance trong sản xuất
    Production batch – the unit of Mass Balance tracking during manufacturing

    Mỗi batch được gắn với 1 In TC chính và đi qua 3 công đoạn:
    Each batch is linked to 1 primary In TC and goes through 3 stages:
        Cutting (Cắt) → Sewing (May) → Packing (Đóng gói)
    """
    __tablename__ = "production_batches"

    id             : Mapped[int]  = mapped_column(primary_key=True)
    batch_number   : Mapped[str]  = mapped_column(String(100), unique=True, nullable=False)

    # Product info
    product_name   : Mapped[str]           = mapped_column(String(200), nullable=False)
    product_code   : Mapped[Optional[str]] = mapped_column(String(100))
    style_number   : Mapped[Optional[str]] = mapped_column(String(100))
    order_number   : Mapped[Optional[str]] = mapped_column(String(100))

    # Source TC – In TC chính cho lô này
    tc_in_id : Mapped[Optional[int]] = mapped_column(ForeignKey("tc_in.id"))

    # Quantities
    planned_input_qty  : Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 3))  # kg kế hoạch sử dụng
    actual_input_qty   : Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 3))  # kg thực tế xuất cắt
    planned_output_qty : Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 3))  # kg thành phẩm kế hoạch
    actual_output_qty  : Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 3))  # kg thành phẩm thực tế

    start_date : Mapped[date]           = mapped_column(Date, nullable=False)
    end_date   : Mapped[Optional[date]] = mapped_column(Date)

    status     : Mapped[str]           = mapped_column(String(20), default=BatchStatus.PLANNED)
    notes      : Mapped[Optional[str]] = mapped_column(Text)
    created_by : Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at : Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())
    updated_at : Mapped[datetime]      = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    tc_in              : Mapped[Optional["TCIn"]]           = relationship(back_populates="production_batches")
    creator            : Mapped[Optional["User"]]           = relationship(back_populates="batches_created", foreign_keys=[created_by])
    stages             : Mapped[List["ProductionStage"]]    = relationship(back_populates="batch", order_by="ProductionStage.stage_date", cascade="all, delete-orphan")
    stock_transactions : Mapped[List["StockTransaction"]]   = relationship(back_populates="batch")

    __table_args__ = (
        Index("ix_batch_number", "batch_number"),
        Index("ix_batch_tc_in",  "tc_in_id"),
        Index("ix_batch_status", "status"),
    )

    @property
    def total_loss_kg(self) -> Optional[Decimal]:
        if self.actual_input_qty is not None and self.actual_output_qty is not None:
            return self.actual_input_qty - self.actual_output_qty
        return None

    @property
    def total_loss_pct(self) -> Optional[Decimal]:
        loss = self.total_loss_kg
        if loss is not None and self.actual_input_qty and self.actual_input_qty > 0:
            return (loss / self.actual_input_qty) * Decimal("100")
        return None

    def __repr__(self) -> str:
        return f"<Batch {self.batch_number} | {self.status}>"


class ProductionStage(Base):
    """
    Ghi nhận hao hụt tại từng công đoạn sản xuất
    Records material loss at each production stage (Cutting / Sewing / Packing)

    Công thức hao hụt / Loss formula:
        loss_qty = input_quantity - output_quantity
        loss_pct = loss_qty / input_quantity × 100

    Ngưỡng cảnh báo GRS thông thường / Typical GRS alert thresholds:
        Cutting  : > 15% is unusual
        Sewing   : > 10% is unusual
        Packing  : > 5%  is unusual
    """
    __tablename__ = "production_stages"

    id             : Mapped[int]  = mapped_column(primary_key=True)
    batch_id       : Mapped[int]  = mapped_column(ForeignKey("production_batches.id"), nullable=False)
    stage          : Mapped[str]  = mapped_column(String(20), nullable=False)   # cutting / sewing / packing
    stage_date     : Mapped[date] = mapped_column(Date, nullable=False)

    input_quantity  : Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)   # kg đầu vào công đoạn
    output_quantity : Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)   # kg đầu ra công đoạn
    # loss = input - output (computed property, không lưu DB)

    loss_reason    : Mapped[Optional[str]] = mapped_column(Text)
    operator_name  : Mapped[Optional[str]] = mapped_column(String(100))
    verified_by    : Mapped[Optional[str]] = mapped_column(String(100))
    notes          : Mapped[Optional[str]] = mapped_column(Text)
    created_by     : Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at     : Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())

    # Relationships
    batch : Mapped["ProductionBatch"] = relationship(back_populates="stages")

    __table_args__ = (
        UniqueConstraint("batch_id", "stage", name="uq_batch_stage"),     # 1 lô chỉ có 1 record Cắt, 1 May, 1 Đóng gói
        CheckConstraint("input_quantity > 0",                             name="chk_stage_input_pos"),
        CheckConstraint("output_quantity >= 0",                           name="chk_stage_output_nonneg"),
        CheckConstraint("output_quantity <= input_quantity",              name="chk_stage_output_lte_input"),
    )

    @property
    def loss_quantity(self) -> Decimal:
        """Kg hao hụt / Loss in kg"""
        return self.input_quantity - self.output_quantity

    @property
    def loss_pct(self) -> Decimal:
        """% hao hụt / Loss percentage"""
        if self.input_quantity > 0:
            return (self.loss_quantity / self.input_quantity) * Decimal("100")
        return Decimal("0")

    @property
    def yield_pct(self) -> Decimal:
        return Decimal("100") - self.loss_pct

    def __repr__(self) -> str:
        return f"<Stage {self.stage} | batch={self.batch_id} | {self.input_quantity}→{self.output_quantity} kg>"


# ─────────────────────────────────────────────────────────────────────────────
# Stock Transactions / Giao dịch kho
# ─────────────────────────────────────────────────────────────────────────────

class StockTransaction(Base):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  STOCK TRANSACTION – Sổ kho bất biến                                    │
    │  Ghi nhận MỌI chuyển động của vật liệu/sản phẩm có chứng nhận          │
    │  Records EVERY movement of certified material/product                    │
    │                                                                          │
    │  Quy ước dấu / Sign convention:                                          │
    │    quantity > 0  →  Nhập kho (stock increases)                          │
    │    quantity < 0  →  Xuất kho (stock decreases)                          │
    │                                                                          │
    │  running_balance phải được tính và cập nhật sau mỗi giao dịch           │
    │  running_balance must be computed and stored after each transaction       │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    __tablename__ = "stock_transactions"

    id               : Mapped[int]  = mapped_column(primary_key=True)
    transaction_date : Mapped[date] = mapped_column(Date, nullable=False)
    transaction_type : Mapped[str]  = mapped_column(String(30), nullable=False)

    # Foreign keys – không bắt buộc, phụ thuộc loại giao dịch
    tc_in_id   : Mapped[Optional[int]] = mapped_column(ForeignKey("tc_in.id"))
    tc_out_id  : Mapped[Optional[int]] = mapped_column(ForeignKey("tc_out.id"))
    batch_id   : Mapped[Optional[int]] = mapped_column(ForeignKey("production_batches.id"))
    stage_id   : Mapped[Optional[int]] = mapped_column(ForeignKey("production_stages.id"))

    material_id     : Mapped[int]     = mapped_column(ForeignKey("materials.id"), nullable=False)
    quantity        : Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)   # + nhập / – xuất
    quantity_type   : Mapped[str]     = mapped_column(String(20), default=QtyType.CERTIFIED)
    running_balance : Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 3))   # Tồn sau giao dịch

    reference_number : Mapped[Optional[str]] = mapped_column(String(100))
    notes            : Mapped[Optional[str]] = mapped_column(Text)
    created_by       : Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at       : Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())

    # Relationships
    material : Mapped["Material"]              = relationship(back_populates="stock_transactions")
    tc_in    : Mapped[Optional["TCIn"]]        = relationship(back_populates="stock_transactions")
    tc_out   : Mapped[Optional["TCOut"]]       = relationship(back_populates="stock_transactions")
    batch    : Mapped[Optional["ProductionBatch"]] = relationship(back_populates="stock_transactions")

    __table_args__ = (
        Index("ix_stock_date",     "transaction_date"),
        Index("ix_stock_material", "material_id"),
        Index("ix_stock_tc_in",    "tc_in_id"),
        Index("ix_stock_tc_out",   "tc_out_id"),
        Index("ix_stock_batch",    "batch_id"),
    )

    def __repr__(self) -> str:
        return f"<StockTx {self.transaction_type} | {self.quantity:+.3f} kg | {self.transaction_date}>"


# ─────────────────────────────────────────────────────────────────────────────
# Mass Balance Period / Kỳ Mass Balance
# ─────────────────────────────────────────────────────────────────────────────

class MassBalancePeriod(Base):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  MASS BALANCE PERIOD – Bản cân đối Mass Balance theo kỳ                 │
    │  Đây là tài liệu kiểm toán GRS/GOTS chính thức                         │
    │  This is the official GRS/GOTS Mass Balance audit record                 │
    │                                                                          │
    │  Công thức cân đối / Balance formula:                                    │
    │    Opening Stock                                                         │
    │    + Certified Purchased (∑ In TC)                                       │
    │    ─────────────────────────────                                         │
    │    = Total Available                                                     │
    │    − Issued to Production                                                │
    │      → − Cutting Loss                                                   │
    │      → − Sewing Loss                                                    │
    │      → − Packing Loss                                                   │
    │    = Certified Produced                                                  │
    │    − Certified Sold (∑ Out TC)                                           │
    │    ─────────────────────────────                                         │
    │    = Closing Stock (theoretical)                                         │
    │                                                                          │
    │    Difference = Actual Closing − Theoretical Closing                    │
    │    PASS if |Difference| ≤ 0.5% of Total Available                       │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    __tablename__ = "mass_balance_periods"

    id                     : Mapped[int]  = mapped_column(primary_key=True)
    period_start           : Mapped[date] = mapped_column(Date, nullable=False)
    period_end             : Mapped[date] = mapped_column(Date, nullable=False)
    certification_standard : Mapped[str]  = mapped_column(String(20), nullable=False)
    material_id            : Mapped[Optional[int]] = mapped_column(ForeignKey("materials.id"))

    # ── Số dư đầu kỳ / Opening balance ──────────────────────────────────────
    opening_stock_raw : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))  # Tồn nguyên liệu
    opening_stock_wip : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))  # Tồn WIP
    opening_stock_fg  : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))  # Tồn thành phẩm

    # ── Đầu vào / Inputs ─────────────────────────────────────────────────────
    certified_purchased : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))  # ∑ In TC
    number_of_tc_in     : Mapped[int]     = mapped_column(Integer, default=0)

    # ── Sản xuất / Production ─────────────────────────────────────────────────
    issued_to_production : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))  # Xuất cắt

    # Cutting / Cắt
    cutting_input    : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    cutting_output   : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    cutting_loss     : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    cutting_loss_pct : Mapped[Decimal] = mapped_column(Numeric(8, 4),  default=Decimal("0"))

    # Sewing / May
    sewing_input    : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    sewing_output   : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    sewing_loss     : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    sewing_loss_pct : Mapped[Decimal] = mapped_column(Numeric(8, 4),  default=Decimal("0"))

    # Packing / Đóng gói
    packing_input    : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    packing_output   : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    packing_loss     : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    packing_loss_pct : Mapped[Decimal] = mapped_column(Numeric(8, 4),  default=Decimal("0"))

    # Tổng / Totals
    total_process_loss : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    total_loss_pct     : Mapped[Decimal] = mapped_column(Numeric(8, 4),  default=Decimal("0"))

    # ── Đầu ra / Outputs ─────────────────────────────────────────────────────
    certified_produced  : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))  # Thành phẩm
    certified_sold      : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))  # ∑ Out TC
    number_of_tc_out    : Mapped[int]     = mapped_column(Integer, default=0)

    # ── Số dư cuối kỳ / Closing balance ──────────────────────────────────────
    closing_stock_raw   : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    closing_stock_fg    : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    closing_stock_total : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))

    # ── Đối soát / Reconciliation ─────────────────────────────────────────────
    theoretical_closing : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))
    difference          : Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("0"))   # + = surplus, − = deficit
    difference_pct      : Mapped[Decimal] = mapped_column(Numeric(8, 4),  default=Decimal("0"))
    balance_status      : Mapped[str]     = mapped_column(String(20), default=BalanceStatus.PENDING)

    # ── Audit metadata ────────────────────────────────────────────────────────
    calculated_at  : Mapped[Optional[datetime]] = mapped_column(DateTime)
    calculated_by  : Mapped[Optional[int]]      = mapped_column(ForeignKey("users.id"))
    approved_by    : Mapped[Optional[int]]      = mapped_column(ForeignKey("users.id"))
    approved_at    : Mapped[Optional[datetime]] = mapped_column(DateTime)
    notes          : Mapped[Optional[str]]      = mapped_column(Text)

    created_at : Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at : Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    material : Mapped[Optional["Material"]] = relationship(back_populates="mb_periods")

    __table_args__ = (
        UniqueConstraint("period_start", "period_end", "certification_standard", "material_id",
                         name="uq_mb_period"),
        CheckConstraint("period_end >= period_start", name="chk_mb_period_valid"),
    )

    def __repr__(self) -> str:
        return f"<MBPeriod {self.period_start}→{self.period_end} | {self.certification_standard} | {self.balance_status}>"


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log / Nhật ký kiểm toán
# ─────────────────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Nhật ký kiểm toán KHÔNG THỂ SỬA / Immutable audit trail
    Ghi lại mọi INSERT / UPDATE / DELETE trong hệ thống
    Required by GRS clause 5.1.3 (data integrity & traceability)
    """
    __tablename__ = "audit_logs"

    id             : Mapped[int]           = mapped_column(primary_key=True)
    table_name     : Mapped[str]           = mapped_column(String(100), nullable=False)
    record_id      : Mapped[Optional[int]] = mapped_column(Integer)
    action         : Mapped[str]           = mapped_column(String(20),  nullable=False)   # INSERT / UPDATE / DELETE
    old_values     : Mapped[Optional[dict]] = mapped_column(JSON)   # giá trị cũ
    new_values     : Mapped[Optional[dict]] = mapped_column(JSON)   # giá trị mới
    changed_fields : Mapped[Optional[str]] = mapped_column(Text)    # JSON array
    user_id        : Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    ip_address     : Mapped[Optional[str]] = mapped_column(String(45))
    user_agent     : Mapped[Optional[str]] = mapped_column(Text)
    created_at     : Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())

    # Relationships
    user : Mapped[Optional["User"]] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_table_record", "table_name", "record_id"),
        Index("ix_audit_user",         "user_id"),
        Index("ix_audit_created_at",   "created_at"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# System Settings / Cài đặt hệ thống
# ─────────────────────────────────────────────────────────────────────────────

class SystemSetting(Base):
    """Cài đặt hệ thống (thresholds, company info…) / System configuration"""
    __tablename__ = "system_settings"

    id          : Mapped[int]           = mapped_column(primary_key=True)
    key         : Mapped[str]           = mapped_column(String(100), unique=True, nullable=False)
    value       : Mapped[Optional[str]] = mapped_column(Text)
    description : Mapped[Optional[str]] = mapped_column(Text)
    updated_by  : Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    updated_at  : Mapped[datetime]      = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# ER Diagram (text) / Sơ đồ quan hệ thực thể
# ─────────────────────────────────────────────────────────────────────────────
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    ER DIAGRAM – TEXTILE TRACEABILITY SYSTEM                  ║
║                    (đọc từ trái sang phải / read left to right)              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  [users] ─────────┬──────────────────────────────────────────────────────   ║
║  (created_by)     │ (FK to all tables)                                       ║
║                   │                                                          ║
║  [suppliers] ─────┼──(1:M)──► [tc_in] ──(1:M)──► [tc_linkage] ◄──(M:1)── [tc_out] ──(M:1)── [buyers]
║                   │                │                                │                                  ║
║  [materials] ─────┼──(1:M)──►─────┘             (allocated_qty)   └──────────────────────────────────║
║      │            │                │                                                                    ║
║      │ (1:M)      │                │ (1:M)                                                             ║
║      ▼            │                ▼                                                                    ║
║  [material_       │        [production_batches] ──(1:M)──► [production_stages]                        ║
║   categories]     │                │                        cutting / sewing / packing                 ║
║                   │                │ (1:M)                  input_qty, output_qty                      ║
║                   │                ▼                                                                    ║
║                   │        [stock_transactions] ◄── tất cả movements qua đây                          ║
║                   │                │              all movements go through here                        ║
║                   │                │                                                                    ║
║                   │                ▼                                                                    ║
║                   │        [mass_balance_periods] ── kỳ kiểm toán / audit period                      ║
║                   │                                                                                     ║
║                   └──────────────────────────────────────────────────────── [audit_logs]              ║
║                                                                                                         ║
║  Cardinality:                                                                                           ║
║    suppliers  (1)──(M)  tc_in                                                                          ║
║    buyers     (1)──(M)  tc_out                                                                         ║
║    materials  (1)──(M)  tc_in                                                                          ║
║    tc_in      (1)──(M)  tc_linkage  (M)──(1)  tc_out    ← mass balance split                         ║
║    tc_in      (1)──(M)  production_batches                                                             ║
║    production_batches (1)──(M)  production_stages                                                      ║
║    production_batches (1)──(M)  stock_transactions                                                     ║
║    tc_in  (1)──(M)  stock_transactions                                                                 ║
║    tc_out (1)──(M)  stock_transactions                                                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
