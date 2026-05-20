"""
CRUD services cho Transaction Certificates (In TC + Out TC)
Business logic đầy đủ, tự động tạo StockTransaction + AuditLog

Rules:
  • Tạo In TC  → tự động nhập kho (tc_in_receipt, +qty)
  • Issue Out TC → tạo TC Linkages, xuất kho (tc_out_sale, -qty), kiểm tra đủ tồn
  • Huỷ TC       → chỉ cho phép nếu chưa có giao dịch liên quan
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crud.base import get_or_404, model_to_dict, write_audit_log
from app.models import (
    Buyer, Material, StockTransaction, Supplier,
    TCIn, TCInStatus, TCLinkage, TCOut, TCOutStatus, TxType, QtyType,
)
from app.schemas.tc import (
    BuyerCreate, MaterialCreate, SupplierCreate,
    TCInCreate, TCInUpdate,
    TCLinkageCreate, TCOutCreate, TCOutIssueRequest, TCOutUpdate,
)


# ─────────────────────────────────────────────────────────────────────────────
# Master Data Services / Dịch vụ danh mục
# ─────────────────────────────────────────────────────────────────────────────

class SupplierService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: SupplierCreate, user_id: Optional[int] = None) -> Supplier:
        supplier = Supplier(**data.model_dump())
        self.db.add(supplier)
        self.db.flush()
        write_audit_log(self.db, "suppliers", supplier.id, "INSERT",
                        new_values=model_to_dict(supplier), user_id=user_id)
        return supplier

    def get(self, supplier_id: int) -> Supplier:
        return get_or_404(self.db, Supplier, supplier_id)

    def list_active(self) -> List[Supplier]:
        return self.db.query(Supplier).filter(Supplier.is_active == True).order_by(Supplier.name).all()

    def deactivate(self, supplier_id: int, user_id: Optional[int] = None) -> Supplier:
        s = get_or_404(self.db, Supplier, supplier_id)
        old = model_to_dict(s)
        s.is_active = False
        write_audit_log(self.db, "suppliers", s.id, "UPDATE",
                        old_values=old, new_values=model_to_dict(s), user_id=user_id)
        return s


class BuyerService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: BuyerCreate, user_id: Optional[int] = None) -> Buyer:
        buyer = Buyer(**data.model_dump())
        self.db.add(buyer)
        self.db.flush()
        write_audit_log(self.db, "buyers", buyer.id, "INSERT",
                        new_values=model_to_dict(buyer), user_id=user_id)
        return buyer

    def get(self, buyer_id: int) -> Buyer:
        return get_or_404(self.db, Buyer, buyer_id)

    def list_active(self) -> List[Buyer]:
        return self.db.query(Buyer).filter(Buyer.is_active == True).order_by(Buyer.name).all()


class MaterialService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: MaterialCreate, user_id: Optional[int] = None) -> Material:
        material = Material(**data.model_dump())
        self.db.add(material)
        self.db.flush()
        write_audit_log(self.db, "materials", material.id, "INSERT",
                        new_values=model_to_dict(material), user_id=user_id)
        return material

    def get(self, material_id: int) -> Material:
        return get_or_404(self.db, Material, material_id)

    def list_active(self) -> List[Material]:
        return self.db.query(Material).filter(Material.is_active == True).order_by(Material.code).all()


# ─────────────────────────────────────────────────────────────────────────────
# Stock Transaction Helper (dùng nội bộ)
# ─────────────────────────────────────────────────────────────────────────────

def _create_stock_tx(
    db               : Session,
    transaction_date : date,
    transaction_type : str,
    material_id      : int,
    quantity         : Decimal,     # positive = in, negative = out
    tc_in_id         : Optional[int] = None,
    tc_out_id        : Optional[int] = None,
    batch_id         : Optional[int] = None,
    stage_id         : Optional[int] = None,
    reference_number : Optional[str] = None,
    quantity_type    : str           = QtyType.CERTIFIED,
    notes            : Optional[str] = None,
    user_id          : Optional[int] = None,
) -> StockTransaction:
    """
    Tạo StockTransaction và tính running_balance
    Create StockTransaction and compute running_balance
    """
    # Lấy balance trước giao dịch này (tính trên toàn bộ lịch sử theo material)
    # Get balance before this transaction (over full history for this material)
    last_tx = (
        db.query(StockTransaction)
        .filter(
            StockTransaction.material_id   == material_id,
            StockTransaction.quantity_type == quantity_type,
        )
        .order_by(StockTransaction.created_at.desc())
        .first()
    )
    prev_balance = last_tx.running_balance if (last_tx and last_tx.running_balance is not None) else Decimal("0")
    new_balance  = prev_balance + quantity

    tx = StockTransaction(
        transaction_date = transaction_date,
        transaction_type = transaction_type,
        material_id      = material_id,
        quantity         = quantity,
        quantity_type    = quantity_type,
        running_balance  = new_balance,
        tc_in_id         = tc_in_id,
        tc_out_id        = tc_out_id,
        batch_id         = batch_id,
        stage_id         = stage_id,
        reference_number = reference_number,
        notes            = notes,
        created_by       = user_id,
    )
    db.add(tx)
    db.flush()
    return tx


def get_current_balance(db: Session, material_id: int, quantity_type: str = QtyType.CERTIFIED) -> Decimal:
    """
    Tồn kho hiện tại theo vật liệu
    Current stock balance for a material
    """
    last_tx = (
        db.query(StockTransaction)
        .filter(
            StockTransaction.material_id   == material_id,
            StockTransaction.quantity_type == quantity_type,
        )
        .order_by(StockTransaction.created_at.desc())
        .first()
    )
    if last_tx and last_tx.running_balance is not None:
        return last_tx.running_balance
    return Decimal("0")


def get_balance_at_date(
    db           : Session,
    material_id  : int,
    as_of_date   : date,
    quantity_type: str = QtyType.CERTIFIED,
) -> Decimal:
    """
    Tồn kho tại một ngày cụ thể
    Stock balance at a specific date (for opening balance calculation)
    """
    result = (
        db.query(func.sum(StockTransaction.quantity))
        .filter(
            StockTransaction.material_id    == material_id,
            StockTransaction.quantity_type  == quantity_type,
            StockTransaction.transaction_date <= as_of_date,
        )
        .scalar()
    )
    return result or Decimal("0")


# ─────────────────────────────────────────────────────────────────────────────
# TCIn Service / Dịch vụ In TC
# ─────────────────────────────────────────────────────────────────────────────

class TCInService:
    """
    Quản lý toàn bộ vòng đời của Incoming Transaction Certificate
    Manages the full lifecycle of an Incoming Transaction Certificate
    """

    def __init__(self, db: Session):
        self.db = db

    # ── Create / Tạo mới ──────────────────────────────────────────────────

    def create(self, data: TCInCreate, user_id: Optional[int] = None) -> TCIn:
        """
        Tạo In TC mới + tự động nhập kho
        Create new In TC + automatically create receipt stock transaction

        Raises:
            ValueError: nếu supplier/material không tồn tại hoặc không active
        """
        # Validate supplier
        supplier = self.db.get(Supplier, data.supplier_id)
        if not supplier or not supplier.is_active:
            raise ValueError(f"Supplier id={data.supplier_id} không tồn tại hoặc đã ngưng hoạt động")

        # Validate material
        material = self.db.get(Material, data.material_id)
        if not material or not material.is_active:
            raise ValueError(f"Material id={data.material_id} không tồn tại hoặc đã ngưng hoạt động")

        # Kiểm tra TC number trùng / Check duplicate TC number
        existing = self.db.query(TCIn).filter(TCIn.tc_number == data.tc_number).first()
        if existing:
            raise ValueError(f"TC number '{data.tc_number}' đã tồn tại / already exists")

        # Tạo TCIn – quantity_remaining = certified_quantity (chưa dùng gì)
        tc = TCIn(
            **data.model_dump(),
            quantity_remaining = data.certified_quantity,   # 100% remaining at creation
            status             = TCInStatus.ACTIVE,
            created_by         = user_id,
        )
        self.db.add(tc)
        self.db.flush()   # lấy id trước khi tạo stock tx

        # Tự động nhập kho / Auto-create receipt stock transaction
        received_date = data.received_date or data.issue_date
        _create_stock_tx(
            db               = self.db,
            transaction_date = received_date,
            transaction_type = TxType.TC_IN_RECEIPT,
            material_id      = data.material_id,
            quantity         = +data.certified_quantity,    # +  = nhập kho
            tc_in_id         = tc.id,
            reference_number = data.tc_number,
            notes            = f"Nhập kho từ In TC {data.tc_number}",
            user_id          = user_id,
        )

        write_audit_log(self.db, "tc_in", tc.id, "INSERT",
                        new_values=model_to_dict(tc), user_id=user_id)
        return tc

    # ── Read / Đọc ────────────────────────────────────────────────────────

    def get(self, tc_in_id: int) -> TCIn:
        return get_or_404(self.db, TCIn, tc_in_id)

    def get_by_number(self, tc_number: str) -> Optional[TCIn]:
        return self.db.query(TCIn).filter(TCIn.tc_number == tc_number).first()

    def list(
        self,
        supplier_id             : Optional[int]  = None,
        material_id             : Optional[int]  = None,
        certification_standard  : Optional[str]  = None,
        status                  : Optional[str]  = None,
        date_from               : Optional[date] = None,
        date_to                 : Optional[date] = None,
        has_remaining           : Optional[bool] = None,   # Lọc TC còn số dư
    ) -> List[TCIn]:
        """Danh sách In TC với nhiều bộ lọc / List In TCs with multiple filters"""
        q = self.db.query(TCIn)
        if supplier_id:
            q = q.filter(TCIn.supplier_id == supplier_id)
        if material_id:
            q = q.filter(TCIn.material_id == material_id)
        if certification_standard:
            q = q.filter(TCIn.certification_standard == certification_standard)
        if status:
            q = q.filter(TCIn.status == status)
        if date_from:
            q = q.filter(TCIn.issue_date >= date_from)
        if date_to:
            q = q.filter(TCIn.issue_date <= date_to)
        if has_remaining is True:
            q = q.filter(TCIn.quantity_remaining > 0)
        return q.order_by(TCIn.issue_date.desc()).all()

    # ── Update / Cập nhật ─────────────────────────────────────────────────

    def update(self, tc_in_id: int, data: TCInUpdate, user_id: Optional[int] = None) -> TCIn:
        tc  = get_or_404(self.db, TCIn, tc_in_id)
        old = model_to_dict(tc)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(tc, field, value)
        write_audit_log(self.db, "tc_in", tc.id, "UPDATE",
                        old_values=old, new_values=model_to_dict(tc), user_id=user_id)
        return tc

    # ── Cancel / Huỷ ─────────────────────────────────────────────────────

    def cancel(self, tc_in_id: int, user_id: Optional[int] = None) -> TCIn:
        """
        Huỷ In TC – chỉ cho phép nếu chưa có linkage và chưa xuất sản xuất
        Cancel In TC – only allowed if no linkages and no production issues
        """
        tc = get_or_404(self.db, TCIn, tc_in_id)

        if tc.linkages:
            raise ValueError(
                f"Không thể huỷ TC '{tc.tc_number}' – đã có {len(tc.linkages)} linkage với Out TC. "
                f"Cannot cancel – has existing linkages."
            )

        if tc.quantity_remaining < tc.certified_quantity:
            raise ValueError(
                f"Không thể huỷ TC '{tc.tc_number}' – đã xuất "
                f"{tc.quantity_used:.3f} kg cho sản xuất. "
                f"Cannot cancel – material already issued to production."
            )

        old = model_to_dict(tc)
        tc.status = TCInStatus.CANCELLED

        # Đảo ngược stock transaction nhập kho
        # Reverse the receipt stock transaction
        _create_stock_tx(
            db               = self.db,
            transaction_date = date.today(),
            transaction_type = TxType.ADJUSTMENT,
            material_id      = tc.material_id,
            quantity         = -tc.certified_quantity,   # trừ lại
            tc_in_id         = tc.id,
            notes            = f"Huỷ In TC {tc.tc_number} / Cancelled",
            user_id          = user_id,
        )
        write_audit_log(self.db, "tc_in", tc.id, "UPDATE",
                        old_values=old, new_values=model_to_dict(tc), user_id=user_id)
        return tc

    # ── Allocation (internal) / Cấp phát nội bộ ──────────────────────────

    def _deduct_remaining(self, tc: TCIn, qty: Decimal) -> None:
        """
        Trừ quantity_remaining khi cấp phát cho batch/out-TC
        Deduct remaining when allocating to a batch / out-TC.
        Gọi trong cùng transaction, không commit riêng.
        """
        if qty > tc.quantity_remaining:
            raise ValueError(
                f"Cấp phát {qty:.3f} kg vượt tồn còn lại {tc.quantity_remaining:.3f} kg "
                f"trong TC '{tc.tc_number}'. "
                f"Allocation {qty:.3f} kg exceeds remaining {tc.quantity_remaining:.3f} kg."
            )
        tc.quantity_remaining -= qty
        # Cập nhật trạng thái TC tự động
        if tc.quantity_remaining == Decimal("0"):
            tc.status = TCInStatus.FULLY_USED
        elif tc.quantity_remaining < tc.certified_quantity:
            tc.status = TCInStatus.PARTIALLY_USED

    def issue_to_batch(
        self,
        tc_in_id   : int,
        batch_id   : int,
        quantity   : Decimal,
        issue_date : date,
        user_id    : Optional[int] = None,
    ) -> StockTransaction:
        """
        Xuất vật liệu từ In TC cho lô sản xuất → trừ quantity_remaining
        Issue material from In TC to production batch → reduces remaining

        Gọi khi tạo cutting stage / Called when recording cutting stage
        """
        tc = get_or_404(self.db, TCIn, tc_in_id)
        self._deduct_remaining(tc, quantity)

        tx = _create_stock_tx(
            db               = self.db,
            transaction_date = issue_date,
            transaction_type = TxType.ISSUE_CUTTING,
            material_id      = tc.material_id,
            quantity         = -quantity,      # − = xuất kho
            tc_in_id         = tc.id,
            batch_id         = batch_id,
            notes            = f"Xuất cắt cho lô / Issue to cutting for batch {batch_id}",
            user_id          = user_id,
        )
        return tx


# ─────────────────────────────────────────────────────────────────────────────
# TCOut Service / Dịch vụ Out TC
# ─────────────────────────────────────────────────────────────────────────────

class TCOutService:
    """
    Quản lý toàn bộ vòng đời của Outgoing Transaction Certificate
    Manages the full lifecycle of an Outgoing Transaction Certificate
    """

    def __init__(self, db: Session):
        self.db   = db
        self.tc_in_svc = TCInService(db)

    # ── Create draft / Tạo nháp ──────────────────────────────────────────

    def create(self, data: TCOutCreate, user_id: Optional[int] = None) -> TCOut:
        """Tạo Out TC ở trạng thái DRAFT / Create Out TC in DRAFT status"""
        # Kiểm tra buyer
        buyer = self.db.get(Buyer, data.buyer_id)
        if not buyer or not buyer.is_active:
            raise ValueError(f"Buyer id={data.buyer_id} không tồn tại hoặc không active")

        existing = self.db.query(TCOut).filter(TCOut.tc_number == data.tc_number).first()
        if existing:
            raise ValueError(f"TC number '{data.tc_number}' đã tồn tại")

        tc = TCOut(
            **data.model_dump(),
            status     = TCOutStatus.DRAFT,
            created_by = user_id,
        )
        self.db.add(tc)
        self.db.flush()
        write_audit_log(self.db, "tc_out", tc.id, "INSERT",
                        new_values=model_to_dict(tc), user_id=user_id)
        return tc

    # ── Issue / Phát hành ─────────────────────────────────────────────────

    def issue(self, req: TCOutIssueRequest, user_id: Optional[int] = None) -> TCOut:
        """
        Phát hành Out TC:
          1. Kiểm tra tổng allocation = certified_quantity
          2. Kiểm tra từng In TC có đủ remaining
          3. Tạo TCLinkage cho mỗi In TC
          4. Trừ quantity_remaining của từng In TC
          5. Tạo StockTransaction tc_out_sale (−qty)
          6. Đánh dấu Out TC là ISSUED

        Issue Out TC:
          1. Validate total allocation = certified_quantity
          2. Validate each In TC has sufficient remaining
          3. Create TCLinkage per In TC
          4. Deduct quantity_remaining from each In TC
          5. Create tc_out_sale StockTransaction (−qty)
          6. Mark Out TC as ISSUED
        """
        tc_out = get_or_404(self.db, TCOut, req.tc_out_id)

        if tc_out.status == TCOutStatus.ISSUED:
            raise ValueError(f"Out TC '{tc_out.tc_number}' đã được phát hành rồi / already issued")
        if tc_out.status == TCOutStatus.CANCELLED:
            raise ValueError(f"Out TC '{tc_out.tc_number}' đã bị huỷ / already cancelled")

        # Validate tổng allocation / Validate total allocation
        total_alloc = sum(a.allocated_quantity for a in req.allocations)
        if abs(total_alloc - tc_out.certified_quantity) > Decimal("0.001"):
            raise ValueError(
                f"Tổng allocation ({total_alloc:.3f} kg) ≠ certified_quantity "
                f"({tc_out.certified_quantity:.3f} kg). "
                f"Total allocation must equal certified_quantity."
            )

        # Kiểm tra tất cả In TC trước khi thực hiện / Pre-validate all In TCs
        tc_ins = []
        for alloc in req.allocations:
            tc_in = get_or_404(self.db, TCIn, alloc.tc_in_id)
            if tc_in.status == TCInStatus.CANCELLED:
                raise ValueError(f"In TC '{tc_in.tc_number}' đã bị huỷ")
            if alloc.allocated_quantity > tc_in.quantity_remaining:
                raise ValueError(
                    f"In TC '{tc_in.tc_number}' chỉ còn {tc_in.quantity_remaining:.3f} kg "
                    f"nhưng cần {alloc.allocated_quantity:.3f} kg. "
                    f"Insufficient remaining quantity."
                )
            tc_ins.append((tc_in, alloc))

        # Lấy material_id từ In TC đầu tiên (phải cùng loại vật liệu)
        material_id = tc_ins[0][0].material_id

        # Thực hiện / Execute
        for tc_in, alloc in tc_ins:
            # Trừ remaining
            self.tc_in_svc._deduct_remaining(tc_in, alloc.allocated_quantity)

            # Tạo linkage
            alloc_pct = (alloc.allocated_quantity / tc_in.certified_quantity) * Decimal("100")
            linkage = TCLinkage(
                tc_in_id           = tc_in.id,
                tc_out_id          = tc_out.id,
                allocated_quantity = alloc.allocated_quantity,
                allocation_pct     = alloc_pct.quantize(Decimal("0.0001")),
                notes              = alloc.notes,
                created_by         = user_id,
            )
            self.db.add(linkage)

        # Tạo stock transaction xuất kho / Create outbound stock transaction
        _create_stock_tx(
            db               = self.db,
            transaction_date = tc_out.issue_date,
            transaction_type = TxType.TC_OUT_SALE,
            material_id      = material_id,
            quantity         = -tc_out.certified_quantity,    # − = xuất kho bán
            tc_out_id        = tc_out.id,
            reference_number = tc_out.tc_number,
            notes            = f"Bán với Out TC {tc_out.tc_number}",
            user_id          = user_id,
        )

        old = model_to_dict(tc_out)
        tc_out.status = TCOutStatus.ISSUED
        self.db.flush()

        write_audit_log(self.db, "tc_out", tc_out.id, "UPDATE",
                        old_values=old, new_values=model_to_dict(tc_out), user_id=user_id)
        return tc_out

    # ── Cancel / Huỷ ─────────────────────────────────────────────────────

    def cancel(self, tc_out_id: int, user_id: Optional[int] = None) -> TCOut:
        """
        Huỷ Out TC đã phát hành: đảo ngược linkages và stock transaction
        Cancel an issued Out TC: reverse linkages and stock transaction
        """
        tc_out = get_or_404(self.db, TCOut, tc_out_id)
        if tc_out.status != TCOutStatus.ISSUED:
            raise ValueError("Chỉ có thể huỷ Out TC đã ISSUED / Can only cancel ISSUED Out TCs")

        # Hoàn trả remaining cho từng In TC / Restore remaining to each In TC
        for linkage in tc_out.linkages:
            tc_in = linkage.tc_in
            tc_in.quantity_remaining += linkage.allocated_quantity
            if tc_in.quantity_remaining > 0 and tc_in.status == TCInStatus.FULLY_USED:
                tc_in.status = TCInStatus.PARTIALLY_USED
            self.db.delete(linkage)

        # Đảo ngược stock transaction / Reverse stock transaction
        _create_stock_tx(
            db               = self.db,
            transaction_date = date.today(),
            transaction_type = TxType.RETURN_IN,
            material_id      = tc_out.linkages[0].tc_in.material_id if tc_out.linkages else 0,
            quantity         = +tc_out.certified_quantity,   # + = nhập lại
            tc_out_id        = tc_out.id,
            notes            = f"Hoàn trả do huỷ Out TC {tc_out.tc_number}",
            user_id          = user_id,
        )

        old = model_to_dict(tc_out)
        tc_out.status = TCOutStatus.CANCELLED
        self.db.flush()
        write_audit_log(self.db, "tc_out", tc_out.id, "UPDATE",
                        old_values=old, new_values=model_to_dict(tc_out), user_id=user_id)
        return tc_out

    # ── Read / Đọc ────────────────────────────────────────────────────────

    def get(self, tc_out_id: int) -> TCOut:
        return get_or_404(self.db, TCOut, tc_out_id)

    def list(
        self,
        buyer_id               : Optional[int]  = None,
        certification_standard : Optional[str]  = None,
        status                 : Optional[str]  = None,
        date_from              : Optional[date] = None,
        date_to                : Optional[date] = None,
    ) -> List[TCOut]:
        q = self.db.query(TCOut)
        if buyer_id:
            q = q.filter(TCOut.buyer_id == buyer_id)
        if certification_standard:
            q = q.filter(TCOut.certification_standard == certification_standard)
        if status:
            q = q.filter(TCOut.status == status)
        if date_from:
            q = q.filter(TCOut.issue_date >= date_from)
        if date_to:
            q = q.filter(TCOut.issue_date <= date_to)
        return q.order_by(TCOut.issue_date.desc()).all()
