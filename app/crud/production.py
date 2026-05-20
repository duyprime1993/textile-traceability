"""
CRUD services cho Production Batch + Stage
Tự động tạo StockTransaction cho từng công đoạn
Auto-creates StockTransactions for each production stage
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.crud.base import get_or_404, model_to_dict, write_audit_log
from app.crud.tc import _create_stock_tx
from app.models import (
    ProductionBatch, ProductionStage, StockTransaction,
    BatchStatus, StageType, TxType,
)
from app.schemas.production import (
    ProductionBatchCreate, ProductionBatchUpdate,
    ProductionStageCreate,
)


class ProductionBatchService:
    """
    Quản lý lô sản xuất từ tạo đến hoàn thành
    Manages production batches from creation to completion
    """

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: ProductionBatchCreate, user_id: Optional[int] = None) -> ProductionBatch:
        """Tạo lô sản xuất mới / Create new production batch"""
        existing = self.db.query(ProductionBatch).filter(
            ProductionBatch.batch_number == data.batch_number
        ).first()
        if existing:
            raise ValueError(f"Batch number '{data.batch_number}' đã tồn tại")

        batch = ProductionBatch(**data.model_dump(), created_by=user_id)
        self.db.add(batch)
        self.db.flush()
        write_audit_log(self.db, "production_batches", batch.id, "INSERT",
                        new_values=model_to_dict(batch), user_id=user_id)
        return batch

    def get(self, batch_id: int) -> ProductionBatch:
        return get_or_404(self.db, ProductionBatch, batch_id)

    def list(
        self,
        tc_in_id  : Optional[int]  = None,
        status    : Optional[str]  = None,
        date_from : Optional[date] = None,
        date_to   : Optional[date] = None,
    ) -> List[ProductionBatch]:
        q = self.db.query(ProductionBatch)
        if tc_in_id:
            q = q.filter(ProductionBatch.tc_in_id == tc_in_id)
        if status:
            q = q.filter(ProductionBatch.status == status)
        if date_from:
            q = q.filter(ProductionBatch.start_date >= date_from)
        if date_to:
            q = q.filter(ProductionBatch.start_date <= date_to)
        return q.order_by(ProductionBatch.start_date.desc()).all()

    def update(self, batch_id: int, data: ProductionBatchUpdate, user_id: Optional[int] = None) -> ProductionBatch:
        batch = get_or_404(self.db, ProductionBatch, batch_id)
        old   = model_to_dict(batch)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(batch, field, value)
        write_audit_log(self.db, "production_batches", batch.id, "UPDATE",
                        old_values=old, new_values=model_to_dict(batch), user_id=user_id)
        return batch

    def complete(self, batch_id: int, user_id: Optional[int] = None) -> ProductionBatch:
        """
        Đánh dấu lô hoàn thành – tính actual_input_qty và actual_output_qty
        Mark batch as completed – compute actual input/output quantities
        """
        batch = get_or_404(self.db, ProductionBatch, batch_id)
        if batch.status == BatchStatus.COMPLETED:
            raise ValueError(f"Batch '{batch.batch_number}' đã hoàn thành rồi")

        # Lấy input từ cutting stage, output từ packing (hoặc sewing, hoặc cutting)
        cutting = next((s for s in batch.stages if s.stage == StageType.CUTTING), None)
        packing = next((s for s in batch.stages if s.stage == StageType.PACKING), None)
        sewing  = next((s for s in batch.stages if s.stage == StageType.SEWING),  None)

        old = model_to_dict(batch)
        if cutting:
            batch.actual_input_qty = cutting.input_quantity
        if packing:
            batch.actual_output_qty = packing.output_quantity
        elif sewing:
            batch.actual_output_qty = sewing.output_quantity
        elif cutting:
            batch.actual_output_qty = cutting.output_quantity

        batch.status   = BatchStatus.COMPLETED
        batch.end_date = batch.end_date or date.today()
        self.db.flush()
        write_audit_log(self.db, "production_batches", batch.id, "UPDATE",
                        old_values=old, new_values=model_to_dict(batch), user_id=user_id)
        return batch


class ProductionStageService:
    """
    Ghi nhận hao hụt từng công đoạn + tạo StockTransactions tương ứng
    Record stage loss + create corresponding StockTransactions

    Khi ghi nhận một công đoạn, hệ thống tự động tạo 3 stock transactions:
    When recording a stage, the system auto-creates 3 stock transactions:
      1. issue_XX   (−input)  Xuất nguyên liệu vào công đoạn
      2. XX_output  (+output) Nhập thành phẩm/bán thành phẩm
      3. XX_loss    (ghi nhận hao hụt, không ảnh hưởng balance vì đã tính trong 1+2)

    Lưu ý: issue và output cùng nhau đã phản ánh đúng balance, nên loss transaction
    chỉ mang tính ghi nhận / phân tích, quantity = 0 (hoặc không tạo).
    Thay vào đó: quantity của issue = −input, quantity của output = +output.
    Difference = loss, running_balance hạ đi đúng lượng loss.
    """

    # TX type map per stage
    STAGE_TX_MAP = {
        StageType.CUTTING : (TxType.ISSUE_CUTTING, TxType.CUTTING_OUTPUT),
        StageType.SEWING  : (TxType.ISSUE_SEWING,  TxType.SEWING_OUTPUT),
        StageType.PACKING : (TxType.ISSUE_PACKING,  TxType.PACKING_OUTPUT),
    }

    def __init__(self, db: Session):
        self.db = db

    def record_stage(
        self,
        data    : ProductionStageCreate,
        user_id : Optional[int] = None,
    ) -> ProductionStage:
        """
        Ghi nhận kết quả một công đoạn sản xuất
        Record the result of a production stage

        Raises:
            ValueError: nếu công đoạn này đã được ghi nhận, hoặc batch không tồn tại
        """
        batch = get_or_404(self.db, ProductionBatch, data.batch_id)

        # Kiểm tra công đoạn này chưa được ghi nhận / Check stage not already recorded
        # Query DB directly to avoid stale ORM cache
        from app.models import ProductionStage as PS
        existing_stage = self.db.query(PS).filter(
            PS.batch_id == batch.id, PS.stage == data.stage
        ).first()
        if existing_stage:
            raise ValueError(
                f"Công đoạn '{data.stage}' của lô '{batch.batch_number}' "
                f"đã được ghi nhận vào ngày {existing_stage.stage_date}. "
                f"Stage already recorded."
            )

        # Validate thứ tự công đoạn / Validate stage order
        self._validate_stage_order(batch, data.stage)

        # Lấy material_id từ In TC của batch
        if not batch.tc_in_id:
            raise ValueError(
                f"Batch '{batch.batch_number}' chưa được liên kết với In TC. "
                f"Batch must be linked to an In TC before recording production stages."
            )
        material_id = batch.tc_in.material_id

        # Tạo stage record
        stage = ProductionStage(
            **data.model_dump(),
            created_by = user_id,
        )
        self.db.add(stage)
        self.db.flush()

        # Lấy TX types cho công đoạn này
        issue_type, output_type = self.STAGE_TX_MAP[data.stage]

        # TX 1: Xuất vào công đoạn (−input) / Issue to stage (−input)
        # Với cutting: xuất từ kho nguyên liệu
        # Với sewing/packing: xuất từ kho bán thành phẩm (nhưng cùng material)
        _create_stock_tx(
            db               = self.db,
            transaction_date = data.stage_date,
            transaction_type = issue_type,
            material_id      = material_id,
            quantity         = -data.input_quantity,
            tc_in_id         = batch.tc_in_id,
            batch_id         = batch.id,
            stage_id         = stage.id,
            notes            = f"Xuất {data.stage} lô {batch.batch_number}",
            user_id          = user_id,
        )

        # TX 2: Nhập đầu ra công đoạn (+output) / Receive stage output (+output)
        _create_stock_tx(
            db               = self.db,
            transaction_date = data.stage_date,
            transaction_type = output_type,
            material_id      = material_id,
            quantity         = +data.output_quantity,
            tc_in_id         = batch.tc_in_id,
            batch_id         = batch.id,
            stage_id         = stage.id,
            notes            = f"Nhập đầu ra {data.stage} lô {batch.batch_number}",
            user_id          = user_id,
        )
        # Net effect: balance -= loss_quantity (= input - output)

        # Cập nhật batch nếu là cutting (cập nhật actual_input_qty)
        if data.stage == StageType.CUTTING:
            old = model_to_dict(batch)
            batch.actual_input_qty = data.input_quantity
            if batch.status == BatchStatus.PLANNED:
                batch.status = BatchStatus.IN_PROGRESS
            write_audit_log(self.db, "production_batches", batch.id, "UPDATE",
                            old_values=old, new_values=model_to_dict(batch), user_id=user_id)

        write_audit_log(self.db, "production_stages", stage.id, "INSERT",
                        new_values=model_to_dict(stage), user_id=user_id)
        return stage

    def update_stage(
        self,
        stage_id : int,
        output_quantity: Decimal,
        notes    : Optional[str] = None,
        user_id  : Optional[int] = None,
    ) -> ProductionStage:
        """
        Cập nhật output của một stage (ví dụ khi phát hiện sai sót)
        Update output of a stage (e.g., when correcting a mistake)

        Tạo adjustment transactions để điều chỉnh balance
        Creates adjustment transactions to correct balance
        """
        stage = get_or_404(self.db, ProductionStage, stage_id)
        old_output = stage.output_quantity
        diff = output_quantity - old_output   # dương = tăng output, âm = giảm

        if output_quantity > stage.input_quantity:
            raise ValueError("output_quantity không thể > input_quantity")

        old = model_to_dict(stage)
        stage.output_quantity = output_quantity
        if notes:
            stage.notes = notes

        # Tạo adjustment transaction để bù chênh lệch
        if diff != Decimal("0"):
            batch = stage.batch
            material_id = batch.tc_in.material_id if batch and batch.tc_in else None
            if material_id:
                _create_stock_tx(
                    db               = self.db,
                    transaction_date = date.today(),
                    transaction_type = TxType.ADJUSTMENT,
                    material_id      = material_id,
                    quantity         = diff,  # + nếu tăng output, − nếu giảm
                    batch_id         = batch.id if batch else None,
                    stage_id         = stage.id,
                    notes            = f"Điều chỉnh output {stage.stage} stage {stage_id}",
                    user_id          = user_id,
                )

        write_audit_log(self.db, "production_stages", stage.id, "UPDATE",
                        old_values=old, new_values=model_to_dict(stage), user_id=user_id)
        return stage

    def _validate_stage_order(self, batch: ProductionBatch, new_stage: str) -> None:
        """
        Kiểm tra thứ tự công đoạn: Cutting → Sewing → Packing
        Validate stage order: Cutting must come before Sewing, Sewing before Packing
        """
        # Query DB directly to get fresh data (avoids stale ORM relationship cache)
        from app.models import ProductionStage as PS
        existing_stages = {
            s.stage for s in
            self.db.query(PS).filter(PS.batch_id == batch.id).all()
        }
        if new_stage == StageType.SEWING and StageType.CUTTING not in existing_stages:
            raise ValueError(
                f"Phải ghi nhận Cắt trước khi ghi nhận May. "
                f"Cutting must be recorded before Sewing."
            )
        if new_stage == StageType.PACKING and StageType.SEWING not in existing_stages:
            raise ValueError(
                f"Phải ghi nhận May trước khi ghi nhận Đóng gói. "
                f"Sewing must be recorded before Packing."
            )
