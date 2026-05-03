"""
Budget and Procurement models for tracking CAPEX and purchase orders.
"""
from datetime import datetime
from decimal import Decimal
from app import db


COMMITTED_PROCUREMENT_STATUSES = (
    'pending',
    'approved',
    'ordered',
    'in_transit',
    'rfq_pending',
    'rfq_issued',
    'vendor_selection',
    'finance_approval',
    'po_issued',
    'in_delivery',
)

RECEIVED_PROCUREMENT_STATUSES = (
    'delivered',
    'invoiced',
    'paid',
)


class BudgetAllocation(db.Model):
    """Annual/periodic budget allocation by category."""
    __tablename__ = 'budget_allocations'

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year = db.Column(db.Integer, nullable=False, index=True)
    category = db.Column(db.String(64), nullable=False, index=True)  # e.g., 'Equipment', 'Infrastructure', 'Maintenance'
    allocated_amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    description = db.Column(db.String(256), nullable=True)
    status = db.Column(db.String(16), default='active', index=True)  # active, archived, modified
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    updated_by = db.relationship('User', backref='budget_allocations')
    procurements = db.relationship('Procurement', backref='allocation', lazy='dynamic')
    line_items = db.relationship('BudgetLineItem', backref='allocation', lazy='dynamic', cascade='all, delete-orphan')

    def total_approved_amount(self) -> Decimal:
        """Total of all approved budget line items."""
        result = db.session.query(db.func.coalesce(db.func.sum(BudgetLineItem.approved_amount), 0)).filter(
            BudgetLineItem.allocation_id == self.id,
            BudgetLineItem.status != 'cancelled'
        ).scalar()
        return Decimal(str(result or 0))

    def total_committed_amount(self) -> Decimal:
        """Total committed through POs (not yet delivered)."""
        result = db.session.query(db.func.coalesce(db.func.sum(Procurement.total_cost), 0)).filter(
            Procurement.budget_line_item_id.isnot(None),
            db.and_(
                Procurement.status.in_(COMMITTED_PROCUREMENT_STATUSES),
                BudgetLineItem.id == Procurement.budget_line_item_id
            ),
            BudgetLineItem.allocation_id == self.id
        ).scalar()
        return Decimal(str(result or 0))

    def spent_amount(self) -> Decimal:
        """Total actually spent (delivered/paid)."""
        result = db.session.query(db.func.coalesce(db.func.sum(Procurement.total_cost), 0)).filter(
            Procurement.budget_allocation_id == self.id,
            Procurement.status.in_(RECEIVED_PROCUREMENT_STATUSES),
            Procurement.status != 'cancelled'
        ).scalar()
        return Decimal(str(result or 0))

    def remaining_amount(self) -> Decimal:
        """Remaining budget after approvals and actual spend."""
        return Decimal(str(self.allocated_amount)) - self.total_committed_amount() - self.spent_amount()

    def utilization_percent(self) -> float:
        """Budget utilization percentage."""
        if self.allocated_amount <= 0:
            return 0.0
        used = self.total_committed_amount() + self.spent_amount()
        return float((used / Decimal(str(self.allocated_amount))) * 100)

    def __repr__(self):
        return f'<BudgetAllocation FY{self.fiscal_year} {self.category} UGX{self.allocated_amount}>'


class BudgetLineItem(db.Model):
    """Individual approved budget line items within a category allocation."""
    __tablename__ = 'budget_line_items'

    id = db.Column(db.Integer, primary_key=True)
    allocation_id = db.Column(db.Integer, db.ForeignKey('budget_allocations.id'), nullable=False, index=True)
    
    # Item details (what was approved)
    description = db.Column(db.String(256), nullable=False)  # e.g., "Smart watches for field staff"
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_cost = db.Column(db.Numeric(15, 2), nullable=False)  # e.g., UGX 250,000 per unit
    approved_amount = db.Column(db.Numeric(15, 2), nullable=False)  # quantity × unit_cost or custom amount
    
    justification = db.Column(db.Text, nullable=True)  # Why this item is needed
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Status tracking through approval workflow
    status = db.Column(db.String(32), default='pending_approval', index=True)
    # pending_approval → approved → rfq_issued → vendor_selected → po_issued → in_delivery → completed | cancelled
    
    approval_date = db.Column(db.DateTime, nullable=True)
    approval_notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    requested_by = db.relationship('User', foreign_keys=[requested_by_user_id], backref='budget_line_items_requested')
    approved_by = db.relationship('User', foreign_keys=[approved_by_user_id], backref='budget_line_items_approved')
    procurements = db.relationship('Procurement', backref='budget_line_item', lazy='dynamic')

    def committed_amount(self) -> Decimal:
        """Amount committed via POs (ordered but not yet received)."""
        result = db.session.query(db.func.coalesce(db.func.sum(Procurement.total_cost), 0)).filter(
            Procurement.budget_line_item_id == self.id,
            Procurement.status.in_(COMMITTED_PROCUREMENT_STATUSES),
            Procurement.status != 'cancelled'
        ).scalar()
        return Decimal(str(result or 0))

    def received_amount(self) -> Decimal:
        """Amount actually received (delivery notes processed)."""
        result = db.session.query(db.func.coalesce(db.func.sum(Procurement.total_cost), 0)).filter(
            Procurement.budget_line_item_id == self.id,
            Procurement.status.in_(RECEIVED_PROCUREMENT_STATUSES),
            Procurement.status != 'cancelled'
        ).scalar()
        return Decimal(str(result or 0))

    def remaining_amount(self) -> Decimal:
        """Amount still available for this line item."""
        committed = self.committed_amount()
        received = self.received_amount()
        return Decimal(str(self.approved_amount)) - committed - received

    def procurement_progress(self) -> dict:
        """Get status breakdown of all procurements for this line item."""
        procurements = self.procurements.filter(Procurement.status != 'cancelled').all()
        return {
            'total_pos': len(procurements),
            'pending': len([p for p in procurements if p.status in ['pending', 'approved', 'rfq_pending', 'rfq_issued', 'vendor_selection', 'finance_approval']]),
            'ordered': len([p for p in procurements if p.status in ['ordered', 'in_transit', 'po_issued', 'in_delivery']]),
            'delivered': len([p for p in procurements if p.status in RECEIVED_PROCUREMENT_STATUSES])
        }

    def __repr__(self):
        return f'<BudgetLineItem {self.description} UGX{self.approved_amount} {self.status}>'


class Vendor(db.Model):
    """Vendor/supplier master data."""
    __tablename__ = 'vendors'

    id = db.Column(db.Integer, primary_key=True)
    vendor_name = db.Column(db.String(128), nullable=False, unique=True, index=True)
    vendor_code = db.Column(db.String(32), nullable=True, unique=True)
    contact_person = db.Column(db.String(128), nullable=True)
    phone = db.Column(db.String(16), nullable=True)
    email = db.Column(db.String(128), nullable=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(64), nullable=True)
    country = db.Column(db.String(64), nullable=True, default='Uganda')
    tax_id = db.Column(db.String(32), nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    procurements = db.relationship('Procurement', backref='vendor', lazy='dynamic')

    def __repr__(self):
        return f'<Vendor {self.vendor_name}>'


class Procurement(db.Model):
    """Purchase order and procurement tracking."""
    __tablename__ = 'procurements'

    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(32), nullable=False, unique=True, index=True)
    budget_allocation_id = db.Column(db.Integer, db.ForeignKey('budget_allocations.id'), nullable=False, index=True)
    budget_line_item_id = db.Column(db.Integer, db.ForeignKey('budget_line_items.id'), nullable=True, index=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=False, index=True)
    
    # Item details
    item_description = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(15, 2), nullable=False)
    total_cost = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Procurement Workflow Stages
    status = db.Column(db.String(32), default='rfq_pending', index=True)
    # Workflow: rfq_pending → rfq_issued → vendor_selection → finance_approval → po_issued → in_delivery → delivered → invoiced → paid | cancelled
    
    # Timeline tracking through procurement stages
    rfq_date = db.Column(db.DateTime, nullable=True)  # RFQ/Quotation request issued
    vendor_selected_date = db.Column(db.DateTime, nullable=True)  # Vendor selected
    finance_approval_date = db.Column(db.DateTime, nullable=True)  # Finance approved
    finance_approval_notes = db.Column(db.Text, nullable=True)
    
    # Purchase Order
    po_date = db.Column(db.Date, nullable=False, index=True)
    expected_delivery_date = db.Column(db.Date, nullable=True)
    
    # Delivery
    actual_delivery_date = db.Column(db.Date, nullable=True)
    delivery_note_number = db.Column(db.String(32), nullable=True)  # Reference to delivery note
    received_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Invoice & Payment
    invoice_number = db.Column(db.String(32), nullable=True, unique=True)
    invoice_date = db.Column(db.Date, nullable=True)
    payment_date = db.Column(db.Date, nullable=True)
    
    # Notes and tracking
    notes = db.Column(db.Text, nullable=True)
    capex_category = db.Column(db.String(64), nullable=True)  # e.g., 'Vehicles', 'Equipment', 'Infrastructure'
    asset_tag = db.Column(db.String(32), nullable=True)  # If this becomes a fixed asset
    
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    created_by = db.relationship('User', foreign_keys=[created_by_user_id], backref='procurements')
    received_by = db.relationship('User', foreign_keys=[received_by_user_id], backref='procurements_received')

    def is_overdue(self) -> bool:
        """Check if delivery is overdue."""
        if self.expected_delivery_date and self.status not in ('delivered', 'paid', 'cancelled'):
            return datetime.now().date() > self.expected_delivery_date
        return False

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'po_number': self.po_number,
            'vendor_name': self.vendor.vendor_name if self.vendor else None,
            'item_description': self.item_description,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price) if self.unit_price else 0,
            'total_cost': float(self.total_cost) if self.total_cost else 0,
            'po_date': self.po_date.isoformat() if self.po_date else None,
            'status': self.status,
            'expected_delivery_date': self.expected_delivery_date.isoformat() if self.expected_delivery_date else None,
            'actual_delivery_date': self.actual_delivery_date.isoformat() if self.actual_delivery_date else None,
        }

    def __repr__(self):
        return f'<Procurement {self.po_number} UGX{self.total_cost} {self.status}>'


class BudgetRevision(db.Model):
    """Audit trail for budget modifications."""
    __tablename__ = 'budget_revisions'

    id = db.Column(db.Integer, primary_key=True)
    budget_allocation_id = db.Column(db.Integer, db.ForeignKey('budget_allocations.id'), nullable=False, index=True)
    old_amount = db.Column(db.Numeric(15, 2), nullable=False)
    new_amount = db.Column(db.Numeric(15, 2), nullable=False)
    reason = db.Column(db.String(256), nullable=True)
    revision_date = db.Column(db.DateTime, default=datetime.utcnow)
    revised_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    revised_by = db.relationship('User', backref='budget_revisions')

    def __repr__(self):
        return f'<BudgetRevision {self.budget_allocation_id} ${self.old_amount}->${self.new_amount}>'

class ProcurementWorkflowAudit(db.Model):
    """Audit trail for procurement workflow stage transitions."""
    __tablename__ = 'procurement_workflow_audits'

    id = db.Column(db.Integer, primary_key=True)
    procurement_id = db.Column(db.Integer, db.ForeignKey('procurements.id'), nullable=False, index=True)
    
    # Stage transition
    old_status = db.Column(db.String(32), nullable=True)
    new_status = db.Column(db.String(32), nullable=False)
    
    # Event details
    event_date = db.Column(db.DateTime, default=datetime.utcnow)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_notes = db.Column(db.Text, nullable=True)  # e.g., "RFQ sent to 3 vendors", "Finance approved UGX amount", "Delivery confirmed"
    
    changed_by = db.relationship('User', backref='procurement_workflow_changes')
    procurement = db.relationship('Procurement', backref='workflow_history')

    def __repr__(self):
        return f'<ProcurementWorkflowAudit {self.procurement_id} {self.old_status}→{self.new_status}>'