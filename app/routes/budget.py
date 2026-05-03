"""
Budget and Procurement management routes.
"""
from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, desc
from app import db
from app.models.budget import BudgetAllocation, Vendor, Procurement, BudgetRevision, BudgetLineItem, ProcurementWorkflowAudit
from app.utils.decorators import role_required

budget_bp = Blueprint('budget', __name__, url_prefix='/budget')


# ---------------------------------------------------------------------------
# Budget Allocations
# ---------------------------------------------------------------------------

@budget_bp.route('/allocations', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def budget_allocations():
    """Manage annual budget allocations by category."""
    if request.method == 'POST':
        action = request.form.get('action', '').strip().lower()
        
        if action == 'create':
            fiscal_year = int(request.form.get('fiscal_year', date.today().year) or date.today().year)
            category = request.form.get('category', '').strip()
            allocated_amount = request.form.get('allocated_amount', '0')
            description = request.form.get('description', '').strip()
            
            if not category or not allocated_amount:
                flash('Category and allocated amount are required.', 'danger')
                return redirect(url_for('budget.budget_allocations'))
            
            try:
                allocated_amount = Decimal(allocated_amount)
                existing = BudgetAllocation.query.filter_by(
                    fiscal_year=fiscal_year,
                    category=category
                ).first()
                
                if existing:
                    flash(f'Budget allocation for {category} in FY{fiscal_year} already exists.', 'warning')
                    return redirect(url_for('budget.budget_allocations'))
                
                allocation = BudgetAllocation(
                    fiscal_year=fiscal_year,
                    category=category,
                    allocated_amount=allocated_amount,
                    description=description,
                    updated_by_user_id=current_user.id,
                )
                db.session.add(allocation)
                db.session.commit()
                flash(f'Budget allocation {category} created for FY{fiscal_year}.', 'success')
                
            except (ValueError, TypeError) as e:
                flash(f'Invalid amount: {e}', 'danger')
                return redirect(url_for('budget.budget_allocations'))
        
        elif action == 'revise':
            allocation_id = int(request.form.get('allocation_id') or 0)
            new_amount = request.form.get('new_amount', '0')
            reason = request.form.get('reason', '').strip()
            
            allocation = BudgetAllocation.query.get(allocation_id)
            if not allocation:
                flash('Budget allocation not found.', 'danger')
                return redirect(url_for('budget.budget_allocations'))
            
            try:
                new_amount = Decimal(new_amount)
                old_amount = allocation.allocated_amount
                allocation.allocated_amount = new_amount
                
                revision = BudgetRevision(
                    budget_allocation_id=allocation.id,
                    old_amount=old_amount,
                    new_amount=new_amount,
                    reason=reason,
                    revised_by_user_id=current_user.id,
                )
                db.session.add(revision)
                db.session.commit()
                flash(f'Budget revised from ${old_amount} to ${new_amount}.', 'success')
                
            except (ValueError, TypeError) as e:
                flash(f'Invalid amount: {e}', 'danger')

        elif action == 'delete':
            allocation_id = int(request.form.get('allocation_id') or 0)
            allocation = BudgetAllocation.query.get(allocation_id)

            if not allocation:
                flash('Budget allocation not found.', 'danger')
                return redirect(url_for('budget.budget_allocations'))

            try:
                # Remove dependent records first to avoid FK violations in legacy schemas.
                procurement_ids = [
                    row[0] for row in db.session.query(Procurement.id).filter(
                        Procurement.budget_allocation_id == allocation.id
                    ).all()
                ]

                if procurement_ids:
                    ProcurementWorkflowAudit.query.filter(
                        ProcurementWorkflowAudit.procurement_id.in_(procurement_ids)
                    ).delete(synchronize_session=False)

                Procurement.query.filter_by(
                    budget_allocation_id=allocation.id
                ).delete(synchronize_session=False)
                BudgetLineItem.query.filter_by(
                    allocation_id=allocation.id
                ).delete(synchronize_session=False)
                BudgetRevision.query.filter_by(
                    budget_allocation_id=allocation.id
                ).delete(synchronize_session=False)

                category = allocation.category
                fiscal_year = allocation.fiscal_year
                db.session.delete(allocation)
                db.session.commit()

                flash(f'Budget allocation {category} (FY{fiscal_year}) deleted.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Unable to delete budget allocation: {e}', 'danger')
        
        return redirect(url_for('budget.budget_allocations'))
    
    # GET — display allocations grouped by fiscal year
    fiscal_year = int(request.args.get('fiscal_year', date.today().year))
    allocations = BudgetAllocation.query.filter_by(
        fiscal_year=fiscal_year,
        status='active'
    ).order_by(BudgetAllocation.category).all()
    
    # Summary stats
    total_allocated = sum(Decimal(str(a.allocated_amount)) for a in allocations)
    total_spent = sum(a.spent_amount() for a in allocations)
    total_remaining = total_allocated - total_spent
    
    return render_template(
        'budget/allocations.html',
        fiscal_year=fiscal_year,
        allocations=allocations,
        total_allocated=total_allocated,
        total_spent=total_spent,
        total_remaining=total_remaining,
    )


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------

@budget_bp.route('/vendors', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def vendors():
    """Manage vendor/supplier master data."""
    if request.method == 'POST':
        vendor_name = request.form.get('vendor_name', '').strip()
        vendor_code = request.form.get('vendor_code', '').strip()
        contact_person = request.form.get('contact_person', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        country = request.form.get('country', 'Uganda').strip()
        tax_id = request.form.get('tax_id', '').strip()
        
        if not vendor_name:
            flash('Vendor name is required.', 'danger')
            return redirect(url_for('budget.vendors'))
        
        existing = Vendor.query.filter_by(vendor_name=vendor_name).first()
        if existing:
            flash(f'Vendor {vendor_name} already exists.', 'warning')
            return redirect(url_for('budget.vendors'))
        
        vendor = Vendor(
            vendor_name=vendor_name,
            vendor_code=vendor_code or None,
            contact_person=contact_person or None,
            phone=phone or None,
            email=email or None,
            address=address or None,
            city=city or None,
            country=country,
            tax_id=tax_id or None,
        )
        db.session.add(vendor)
        db.session.commit()
        flash(f'Vendor {vendor_name} added.', 'success')
        return redirect(url_for('budget.vendors'))
    
    page = request.args.get('page', 1, type=int)
    vendors_q = Vendor.query.filter_by(is_active=True).order_by(Vendor.vendor_name)
    paginated = vendors_q.paginate(page=page, per_page=20)
    
    return render_template('budget/vendors.html', vendors=paginated.items, pagination=paginated)


# ---------------------------------------------------------------------------
# Procurements (PO Management)
# ---------------------------------------------------------------------------

@budget_bp.route('/procurements', methods=['GET'])
@role_required('admin', 'supervisor', 'operator')
def procurements():
    """List all procurements with filtering."""
    status_filter = request.args.get('status', 'all')
    fiscal_year = int(request.args.get('fiscal_year', date.today().year))
    page = request.args.get('page', 1, type=int)
    
    query = Procurement.query.join(BudgetAllocation).filter(
        BudgetAllocation.fiscal_year == fiscal_year
    )
    
    if status_filter != 'all':
        query = query.filter(Procurement.status == status_filter)
    
    paginated = query.order_by(desc(Procurement.po_date)).paginate(page=page, per_page=20)
    
    # Status summary for this FY
    statuses = db.session.query(
        Procurement.status,
        func.count(Procurement.id).label('count'),
        func.sum(Procurement.total_cost).label('total')
    ).join(BudgetAllocation).filter(
        BudgetAllocation.fiscal_year == fiscal_year
    ).group_by(Procurement.status).all()
    
    status_summary = {s[0]: {'count': s[1], 'total': Decimal(str(s[2] or 0))} for s in statuses}
    
    return render_template(
        'budget/procurements.html',
        procurements=paginated.items,
        pagination=paginated,
        fiscal_year=fiscal_year,
        status_filter=status_filter,
        status_summary=status_summary,
    )


@budget_bp.route('/procurements/create', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def create_procurement():
    """Create a new purchase order."""
    if request.method == 'POST':
        try:
            po_number = request.form.get('po_number', '').strip()
            allocation_id = int(request.form.get('allocation_id') or 0)
            vendor_id = int(request.form.get('vendor_id') or 0)
            item_description = request.form.get('item_description', '').strip()
            quantity = int(request.form.get('quantity', 1))
            unit_price = Decimal(request.form.get('unit_price', '0'))
            po_date = datetime.strptime(request.form.get('po_date', date.today().isoformat()), '%Y-%m-%d').date()
            expected_delivery_date = request.form.get('expected_delivery_date')
            capex_category = request.form.get('capex_category', '').strip()
            notes = request.form.get('notes', '').strip()
            
            if not all([po_number, allocation_id, vendor_id, item_description, quantity, unit_price]):
                flash('All required fields must be filled.', 'danger')
                return redirect(url_for('budget.create_procurement'))
            
            # Check PO uniqueness
            if Procurement.query.filter_by(po_number=po_number).first():
                flash(f'PO {po_number} already exists.', 'warning')
                return redirect(url_for('budget.create_procurement'))
            
            allocation = BudgetAllocation.query.get(allocation_id)
            vendor = Vendor.query.get(vendor_id)
            if not allocation or not vendor:
                flash('Invalid budget allocation or vendor.', 'danger')
                return redirect(url_for('budget.create_procurement'))
            
            total_cost = quantity * unit_price
            
            procurement = Procurement(
                po_number=po_number,
                budget_allocation_id=allocation_id,
                vendor_id=vendor_id,
                item_description=item_description,
                quantity=quantity,
                unit_price=unit_price,
                total_cost=total_cost,
                po_date=po_date,
                expected_delivery_date=datetime.strptime(expected_delivery_date, '%Y-%m-%d').date() if expected_delivery_date else None,
                capex_category=capex_category or None,
                notes=notes or None,
                created_by_user_id=current_user.id,
            )
            db.session.add(procurement)
            db.session.commit()
            flash(f'PO {po_number} created for ${total_cost}.', 'success')
            return redirect(url_for('budget.procurements'))
            
        except (ValueError, TypeError) as e:
            flash(f'Error creating procurement: {e}', 'danger')
            return redirect(url_for('budget.create_procurement'))
    
    allocations = BudgetAllocation.query.filter_by(status='active').order_by(BudgetAllocation.fiscal_year.desc(), BudgetAllocation.category).all()
    vendors = Vendor.query.filter_by(is_active=True).order_by(Vendor.vendor_name).all()
    
    return render_template(
        'budget/procurement_form.html',
        allocations=allocations,
        vendors=vendors,
        action='create',
    )


@budget_bp.route('/procurements/<int:procurement_id>/edit', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def edit_procurement(procurement_id):
    """Edit a procurement record."""
    procurement = Procurement.query.get_or_404(procurement_id)
    
    if request.method == 'POST':
        try:
            procurement.status = request.form.get('status', procurement.status)
            procurement.expected_delivery_date = request.form.get('expected_delivery_date')
            if procurement.expected_delivery_date:
                procurement.expected_delivery_date = datetime.strptime(procurement.expected_delivery_date, '%Y-%m-%d').date()
            
            procurement.actual_delivery_date = request.form.get('actual_delivery_date')
            if procurement.actual_delivery_date:
                procurement.actual_delivery_date = datetime.strptime(procurement.actual_delivery_date, '%Y-%m-%d').date()
            
            procurement.invoice_number = request.form.get('invoice_number', '').strip() or None
            procurement.invoice_date = request.form.get('invoice_date')
            if procurement.invoice_date:
                procurement.invoice_date = datetime.strptime(procurement.invoice_date, '%Y-%m-%d').date()
            
            procurement.payment_date = request.form.get('payment_date')
            if procurement.payment_date:
                procurement.payment_date = datetime.strptime(procurement.payment_date, '%Y-%m-%d').date()
            
            procurement.notes = request.form.get('notes', '').strip() or None
            procurement.asset_tag = request.form.get('asset_tag', '').strip() or None
            
            db.session.commit()
            flash(f'PO {procurement.po_number} updated.', 'success')
            return redirect(url_for('budget.procurements'))
            
        except (ValueError, TypeError) as e:
            flash(f'Error updating procurement: {e}', 'danger')
    
    return render_template('budget/procurement_form.html', procurement=procurement, action='edit')


# ---------------------------------------------------------------------------
# Budget Dashboard & Reports
# ---------------------------------------------------------------------------

@budget_bp.route('/dashboard')
@role_required('admin', 'supervisor', 'operator')
def dashboard():
    """Budget utilization dashboard."""
    fiscal_year = int(request.args.get('fiscal_year', date.today().year))
    
    allocations = BudgetAllocation.query.filter_by(
        fiscal_year=fiscal_year,
        status='active'
    ).order_by(BudgetAllocation.category).all()
    
    # Budget overview
    total_allocated = sum(Decimal(str(a.allocated_amount)) for a in allocations)
    total_spent = sum(a.spent_amount() for a in allocations)
    total_remaining = total_allocated - total_spent
    overall_utilization = float((total_spent / total_allocated * 100)) if total_allocated > 0 else 0
    
    # Procurement status summary
    status_summary = db.session.query(
        Procurement.status,
        func.count(Procurement.id).label('count'),
        func.sum(Procurement.total_cost).label('total')
    ).join(BudgetAllocation).filter(
        BudgetAllocation.fiscal_year == fiscal_year
    ).group_by(Procurement.status).all()
    
    # Top vendors
    top_vendors = db.session.query(
        Vendor.vendor_name,
        func.count(Procurement.id).label('po_count'),
        func.sum(Procurement.total_cost).label('total_spend')
    ).join(Procurement).join(BudgetAllocation).filter(
        BudgetAllocation.fiscal_year == fiscal_year,
        Procurement.status != 'cancelled'
    ).group_by(Vendor.vendor_name).order_by(desc('total_spend')).limit(10).all()
    
    # Overdue procurements
    overdue = Procurement.query.filter(
        Procurement.expected_delivery_date < date.today(),
        Procurement.status.notin_(['delivered', 'paid', 'cancelled'])
    ).join(BudgetAllocation).filter(
        BudgetAllocation.fiscal_year == fiscal_year
    ).all()
    
    return render_template(
        'budget/dashboard.html',
        fiscal_year=fiscal_year,
        allocations=allocations,
        total_allocated=total_allocated,
        total_spent=total_spent,
        total_remaining=total_remaining,
        overall_utilization=overall_utilization,
        status_summary=status_summary,
        top_vendors=top_vendors,
        overdue_count=len(overdue),
        overdue_procurements=overdue[:5],
    )


# ---------------------------------------------------------------------------
# Budget Tracking
# ---------------------------------------------------------------------------

@budget_bp.route('/tracking')
@role_required('admin', 'supervisor', 'operator')
def budget_tracking():
    """Budget tracking and spending visualization."""
    fiscal_year = int(request.args.get('fiscal_year', date.today().year))
    category = request.args.get('category', '').strip()
    
    # Get all allocations for the fiscal year
    query = BudgetAllocation.query.filter_by(fiscal_year=fiscal_year, status='active')
    if category:
        query = query.filter_by(category=category)
    
    allocations = query.order_by(BudgetAllocation.category).all()
    
    # Calculate totals
    total_allocated = sum(Decimal(str(a.allocated_amount)) for a in allocations)
    total_spent = sum(a.spent_amount() for a in allocations)
    total_remaining = total_allocated - total_spent
    overall_utilization = float((total_spent / total_allocated * 100)) if total_allocated > 0 else 0
    
    # Get categories for filter
    categories = db.session.query(
        func.distinct(BudgetAllocation.category)
    ).filter(BudgetAllocation.fiscal_year == fiscal_year).order_by(BudgetAllocation.category).all()
    categories = [c[0] for c in categories]
    
    # Status counts
    def get_utilization(alloc):
        if alloc.allocated_amount > 0:
            return (alloc.spent_amount() / alloc.allocated_amount * 100)
        return 0
    
    status_count = {
        'on_track': sum(1 for a in allocations if get_utilization(a) <= 80),
        'at_risk': sum(1 for a in allocations if 80 < get_utilization(a) <= 100),
        'over_budget': sum(1 for a in allocations if get_utilization(a) > 100)
    }
    
    # Monthly spending data (last 12 months)
    from datetime import timedelta
    procurements = Procurement.query.filter(
        Procurement.po_date >= date.today() - timedelta(days=365),
        Procurement.status != 'cancelled'
    ).all()
    
    monthly_data = {}
    for po in procurements:
        month_key = po.po_date.strftime('%Y-%m')
        if month_key not in monthly_data:
            monthly_data[month_key] = Decimal('0')
        monthly_data[month_key] += po.total_cost
    
    monthly_labels = sorted(monthly_data.keys())
    monthly_spending = [float(monthly_data[m]) for m in monthly_labels]
    
    # Category breakdown
    category_breakdown = {}
    for alloc in allocations:
        category_breakdown[alloc.category] = float(alloc.spent_amount())
    
    category_list = list(category_breakdown.keys())
    category_amounts = list(category_breakdown.values())
    
    # Get recent transactions/procurements
    recent_procurements = Procurement.query.order_by(desc(Procurement.po_date)).limit(50).all()
    
    return render_template('budget/tracking.html',
                         allocations=allocations,
                         fiscal_year=fiscal_year,
                         categories=categories,
                         total_allocated=float(total_allocated),
                         total_spent=float(total_spent),
                         total_remaining=float(total_remaining),
                         overall_utilization=overall_utilization,
                         status_count=status_count,
                         monthly_labels=monthly_labels,
                         monthly_spending=monthly_spending,
                         category_list=category_list,
                         category_amounts=category_amounts,
                         category_breakdown=category_breakdown,
                         transactions=recent_procurements)


# ---------------------------------------------------------------------------
# Budget Reports
# ---------------------------------------------------------------------------

@budget_bp.route('/reports')
@role_required('admin', 'supervisor')
def budget_reports():
    """Budget reporting interface."""
    fiscal_year = int(request.args.get('fiscal_year', date.today().year))
    
    # Get fiscal years for dropdown
    fiscal_years = db.session.query(
        func.distinct(BudgetAllocation.fiscal_year)
    ).order_by(BudgetAllocation.fiscal_year.desc()).all()
    fiscal_years = [y[0] for y in fiscal_years]
    
    # Get allocations for the selected fiscal year
    allocations = BudgetAllocation.query.filter_by(fiscal_year=fiscal_year, status='active').all()
    
    total_allocated = sum(Decimal(str(a.allocated_amount)) for a in allocations)
    total_spent = sum(a.spent_amount() for a in allocations)
    total_remaining = total_allocated - total_spent
    utilization_percent = float((total_spent / total_allocated * 100)) if total_allocated > 0 else 0
    
    # Budget summary data
    summary_data = []
    for alloc in allocations:
        spent = alloc.spent_amount()
        utilization = float((spent / alloc.allocated_amount * 100)) if alloc.allocated_amount > 0 else 0
        
        if utilization <= 80:
            status = 'on_track'
        elif utilization <= 100:
            status = 'at_risk'
        else:
            status = 'over_budget'
        
        summary_data.append({
            'category': alloc.category,
            'allocated': float(alloc.allocated_amount),
            'spent': float(spent),
            'remaining': float(alloc.allocated_amount - spent),
            'utilization': utilization,
            'status': status
        })
    
    # Variance analysis (comparing projected vs actual)
    variance_data = []
    for item in summary_data:
        # Simple projection: assume spending continues at current rate
        projected = item['spent'] * 1.1  # Project 10% buffer
        variance = item['spent'] - projected
        variance_percent = (variance / projected * 100) if projected > 0 else 0
        
        variance_data.append({
            'category': item['category'],
            'projected': projected,
            'actual': item['spent'],
            'variance': variance,
            'variance_percent': variance_percent
        })
    
    # Forecast data
    forecast_data = []
    current_month = date.today().month
    for item in summary_data:
        monthly_rate = item['spent'] / max(current_month, 1)
        projected_total = monthly_rate * 12
        projected_overage = max(0, projected_total - item['allocated'])
        
        forecast_data.append({
            'category': item['category'],
            'monthly_rate': monthly_rate,
            'projected_total': projected_total,
            'allocated': item['allocated'],
            'projected_overage': projected_overage
        })
    
    projected_year_end = sum(f['projected_total'] for f in forecast_data)
    projected_overage = sum(f['projected_overage'] for f in forecast_data)
    
    current_fiscal_year = int(request.args.get('current_fiscal_year', date.today().year))
    
    return render_template('budget/reports.html',
                         fiscal_years=fiscal_years,
                         current_fiscal_year=current_fiscal_year,
                         total_allocated=float(total_allocated),
                         total_spent=float(total_spent),
                         total_remaining=float(total_remaining),
                         utilization_percent=utilization_percent,
                         summary_data=summary_data,
                         variance_data=variance_data,
                         forecast_data=forecast_data,
                         projected_year_end=projected_year_end,
                         projected_overage=projected_overage)


# ---------------------------------------------------------------------------
# Budget Line Items (Approved Items within Allocations)
# ---------------------------------------------------------------------------

@budget_bp.route('/allocations/<int:allocation_id>/line-items', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def allocation_line_items(allocation_id):
    """Manage budget line items for a specific allocation."""
    allocation = BudgetAllocation.query.get_or_404(allocation_id)
    
    if request.method == 'POST':
        action = request.form.get('action', '').strip().lower()
        
        if action == 'add_line_item':
            try:
                description = request.form.get('description', '').strip()
                quantity = int(request.form.get('quantity', 1))
                unit_cost = Decimal(request.form.get('unit_cost', '0'))
                justification = request.form.get('justification', '').strip()
                
                if not description or quantity <= 0 or unit_cost <= 0:
                    flash('Description, quantity, and unit cost are required.', 'danger')
                    return redirect(url_for('budget.allocation_line_items', allocation_id=allocation_id))
                
                approved_amount = quantity * unit_cost
                
                line_item = BudgetLineItem(
                    allocation_id=allocation_id,
                    description=description,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    approved_amount=approved_amount,
                    justification=justification or None,
                    requested_by_user_id=current_user.id,
                    status='pending_approval',
                )
                db.session.add(line_item)
                db.session.commit()
                flash(f'Line item "{description}" added for UGX {approved_amount}.', 'success')
                
            except (ValueError, TypeError) as e:
                flash(f'Error adding line item: {e}', 'danger')
        
        elif action == 'approve_line_item':
            line_item_id = int(request.form.get('line_item_id') or 0)
            approval_notes = request.form.get('approval_notes', '').strip()
            
            line_item = BudgetLineItem.query.get(line_item_id)
            if not line_item:
                flash('Line item not found.', 'danger')
                return redirect(url_for('budget.allocation_line_items', allocation_id=allocation_id))
            
            line_item.status = 'approved'
            line_item.approved_by_user_id = current_user.id
            line_item.approval_date = datetime.utcnow()
            line_item.approval_notes = approval_notes or None
            db.session.commit()
            flash(f'Line item "{line_item.description}" approved.', 'success')
        
        return redirect(url_for('budget.allocation_line_items', allocation_id=allocation_id))
    
    # GET — display line items for this allocation
    line_items = BudgetLineItem.query.filter_by(allocation_id=allocation_id).all()
    total_line_items_approved = sum(
        li.approved_amount for li in line_items if li.status != 'cancelled'
    )
    
    return render_template(
        'budget/line_items.html',
        allocation=allocation,
        line_items=line_items,
        total_line_items_approved=total_line_items_approved,
    )


@budget_bp.route('/line-items/<int:line_item_id>/delete', methods=['POST'])
@role_required('admin', 'supervisor')
def delete_line_item(line_item_id):
    """Cancel a budget line item."""
    line_item = BudgetLineItem.query.get_or_404(line_item_id)
    allocation_id = line_item.allocation_id
    
    line_item.status = 'cancelled'
    db.session.commit()
    flash(f'Line item "{line_item.description}" cancelled.', 'success')
    
    return redirect(url_for('budget.allocation_line_items', allocation_id=allocation_id))


# ---------------------------------------------------------------------------
# Procurement Workflow & Stage Tracking
# ---------------------------------------------------------------------------

@budget_bp.route('/procurements/<int:procurement_id>/workflow', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def procurement_workflow(procurement_id):
    """Track and manage procurement workflow stages."""
    procurement = Procurement.query.get_or_404(procurement_id)
    
    if request.method == 'POST':
        action = request.form.get('action', '').strip().lower()
        
        if action == 'update_stage':
            new_status = request.form.get('new_status', '').strip()
            event_notes = request.form.get('event_notes', '').strip()
            
            valid_statuses = [
                'rfq_pending', 'rfq_issued', 'vendor_selection', 'finance_approval',
                'po_issued', 'in_delivery', 'delivered', 'invoiced', 'paid', 'cancelled'
            ]
            
            if new_status not in valid_statuses:
                flash('Invalid status.', 'danger')
                return redirect(url_for('budget.procurement_workflow', procurement_id=procurement_id))
            
            old_status = procurement.status
            
            # Update stage-specific timestamps
            if new_status == 'rfq_issued':
                procurement.rfq_date = datetime.utcnow()
            elif new_status == 'vendor_selection':
                procurement.vendor_selected_date = datetime.utcnow()
            elif new_status == 'finance_approval':
                procurement.finance_approval_date = datetime.utcnow()
                procurement.finance_approval_notes = event_notes or None
            elif new_status == 'po_issued':
                procurement.po_date = date.today()
            elif new_status == 'in_delivery':
                pass  # delivery tracking separate
            elif new_status == 'delivered':
                if not procurement.actual_delivery_date:
                    procurement.actual_delivery_date = date.today()
                    delivery_note = request.form.get('delivery_note_number', '').strip()
                    if delivery_note:
                        procurement.delivery_note_number = delivery_note
                        procurement.received_by_user_id = current_user.id
            elif new_status == 'invoiced':
                if not procurement.invoice_date:
                    procurement.invoice_date = date.today()
            elif new_status == 'paid':
                if not procurement.payment_date:
                    procurement.payment_date = date.today()
            
            procurement.status = new_status
            
            # Record workflow transition in audit trail
            audit = ProcurementWorkflowAudit(
                procurement_id=procurement_id,
                old_status=old_status,
                new_status=new_status,
                event_notes=event_notes or None,
                changed_by_user_id=current_user.id,
            )
            
            db.session.add(audit)
            db.session.commit()
            
            flash(f'PO {procurement.po_number} status updated to {new_status}.', 'success')
            return redirect(url_for('budget.procurement_workflow', procurement_id=procurement_id))
    
    # GET — display workflow timeline
    workflow_history = procurement.workflow_history
    
    return render_template(
        'budget/procurement_workflow.html',
        procurement=procurement,
        workflow_history=workflow_history,
    )


@budget_bp.route('/procurements/by-line-item/<int:line_item_id>', methods=['GET'])
@role_required('admin', 'supervisor', 'operator')
def procurements_by_line_item(line_item_id):
    """View all procurements for a specific budget line item."""
    line_item = BudgetLineItem.query.get_or_404(line_item_id)
    
    procurements = Procurement.query.filter_by(budget_line_item_id=line_item_id).all()
    
    total_committed = line_item.committed_amount()
    total_received = line_item.received_amount()
    remaining = line_item.remaining_amount()
    progress = line_item.procurement_progress()
    
    return render_template(
        'budget/line_item_procurement_tracking.html',
        line_item=line_item,
        procurements=procurements,
        total_committed=total_committed,
        total_received=total_received,
        remaining=remaining,
        progress=progress,
    )


@budget_bp.route('/line-items/<int:line_item_id>/create-procurement', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def create_procurement_for_line_item(line_item_id):
    """Create a procurement record for a specific budget line item."""
    line_item = BudgetLineItem.query.get_or_404(line_item_id)
    
    if request.method == 'POST':
        try:
            po_number = request.form.get('po_number', '').strip()
            vendor_id = int(request.form.get('vendor_id') or 0)
            quantity = int(request.form.get('quantity', line_item.quantity))
            unit_price = Decimal(request.form.get('unit_price', line_item.unit_cost))
            po_date = datetime.strptime(request.form.get('po_date', date.today().isoformat()), '%Y-%m-%d').date()
            expected_delivery_date = request.form.get('expected_delivery_date')
            notes = request.form.get('notes', '').strip()
            
            if not all([po_number, vendor_id, quantity, unit_price]):
                flash('All required fields must be filled.', 'danger')
                return redirect(url_for('budget.create_procurement_for_line_item', line_item_id=line_item_id))
            
            # Check PO uniqueness
            if Procurement.query.filter_by(po_number=po_number).first():
                flash(f'PO {po_number} already exists.', 'warning')
                return redirect(url_for('budget.create_procurement_for_line_item', line_item_id=line_item_id))
            
            vendor = Vendor.query.get(vendor_id)
            if not vendor:
                flash('Invalid vendor.', 'danger')
                return redirect(url_for('budget.create_procurement_for_line_item', line_item_id=line_item_id))
            
            # Check if adding this PO would exceed approved amount
            total_cost = quantity * unit_price
            if total_cost > line_item.remaining_amount():
                flash(f'PO amount (UGX {total_cost}) exceeds remaining approved budget (UGX {line_item.remaining_amount()}).', 'warning')
                return redirect(url_for('budget.create_procurement_for_line_item', line_item_id=line_item_id))
            
            procurement = Procurement(
                po_number=po_number,
                budget_allocation_id=line_item.allocation_id,
                budget_line_item_id=line_item_id,
                vendor_id=vendor_id,
                item_description=line_item.description,
                quantity=quantity,
                unit_price=unit_price,
                total_cost=total_cost,
                po_date=po_date,
                expected_delivery_date=datetime.strptime(expected_delivery_date, '%Y-%m-%d').date() if expected_delivery_date else None,
                notes=notes or None,
                created_by_user_id=current_user.id,
                status='rfq_pending',  # Start in RFQ stage
            )
            db.session.add(procurement)
            db.session.commit()
            flash(f'PO {po_number} created for "{line_item.description}" (UGX {total_cost}).', 'success')
            return redirect(url_for('budget.procurements_by_line_item', line_item_id=line_item_id))
            
        except (ValueError, TypeError) as e:
            flash(f'Error creating procurement: {e}', 'danger')
            return redirect(url_for('budget.create_procurement_for_line_item', line_item_id=line_item_id))
    
    vendors = Vendor.query.filter_by(is_active=True).order_by(Vendor.vendor_name).all()
    
    return render_template(
        'budget/procurement_form.html',
        line_item=line_item,
        vendors=vendors,
        action='create_for_line_item',
    )


# ---------------------------------------------------------------------------
# Report Export
# ---------------------------------------------------------------------------

@budget_bp.route('/reports/export', methods=['GET'])
@role_required('admin', 'supervisor')
def export_report():
    """Export budget reports in various formats."""
    report_format = request.args.get('format', 'pdf').lower()
    report_type = request.args.get('report_type', 'summary').lower()
    fiscal_year = int(request.args.get('fiscal_year', date.today().year))

    # Get allocations for the selected fiscal year
    allocations = BudgetAllocation.query.filter_by(fiscal_year=fiscal_year, status='active').all()

    total_allocated = sum(Decimal(str(a.allocated_amount)) for a in allocations)
    total_spent = sum(a.spent_amount() for a in allocations)
    total_remaining = total_allocated - total_spent
    utilization_percent = float((total_spent / total_allocated * 100)) if total_allocated > 0 else 0

    # Build summary data
    summary_data = []
    for alloc in allocations:
        spent = alloc.spent_amount()
        utilization = float((spent / alloc.allocated_amount * 100)) if alloc.allocated_amount > 0 else 0
        status = 'on_track' if utilization <= 80 else ('at_risk' if utilization <= 100 else 'over_budget')

        summary_data.append({
            'category': alloc.category,
            'allocated': float(alloc.allocated_amount),
            'spent': float(spent),
            'remaining': float(alloc.allocated_amount - spent),
            'utilization': utilization,
            'status': status
        })

    if report_format == 'pdf':
        # Simple text response for now (full PDF generation would require ReportLab)
        flash('PDF export coming soon. Use browser print-to-PDF feature.', 'info')
        return redirect(url_for('budget.budget_reports', fiscal_year=fiscal_year))

    if report_format == 'excel':
        # Simple text response for now (full Excel export would require openpyxl)
        flash('Excel export coming soon. Use browser export as CSV feature.', 'info')
        return redirect(url_for('budget.budget_reports', fiscal_year=fiscal_year))

    flash('Invalid export format.', 'danger')
    return redirect(url_for('budget.budget_reports', fiscal_year=fiscal_year))
