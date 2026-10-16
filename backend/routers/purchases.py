"""Purchase endpoints (stock coming in): single product, many products, and history."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Product, Supplier, Purchase
from schemas.purchase import PurchaseCreate, PurchaseBulkCreate
from services.stock import record_movement
from utils.validation import MAX_STOCK, calc_total

router = APIRouter(tags=["Purchases"])


@router.post("/purchases")
def create_purchase(purchase_data: PurchaseCreate, db: Session = Depends(get_db)):
    """Record a purchase of one product and add the units to stock.

    The product row is locked while this runs, so two requests can't change
    its stock at the same moment. The purchase, the stock increase and the
    stock-history entry are saved together in one transaction: if anything
    fails, none of them are saved. The total cost is calculated by the
    backend, never taken from the request.

    Args:
        purchase_data: Supplier, product, quantity and unit cost from the
            request body.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with a message, purchase_id, product_id, quantity_added, the new
        current_stock and total_cost.

    Raises:
        HTTPException: 404 if the supplier or product does not exist, 400 if
            the product is deactivated or stock would exceed MAX_STOCK, 500 if
            something unexpected goes wrong (everything is rolled back).
    """
    try:
        supplier = db.query(Supplier).filter(
            Supplier.id == purchase_data.supplier_id
        ).first()
        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found")

        product = db.query(Product).filter(
            Product.id == purchase_data.product_id
        ).with_for_update().first()
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        if not product.is_active:
            raise HTTPException(status_code=400, detail="Product is deactivated")
        if product.current_stock + purchase_data.quantity > MAX_STOCK:
            raise HTTPException(
                status_code=400,
                detail=f"Stock cannot exceed {MAX_STOCK:,} units"
            )

        total_cost = calc_total(purchase_data.quantity, purchase_data.unit_cost)

        purchase = Purchase(
            supplier_id=purchase_data.supplier_id,
            product_id=purchase_data.product_id,
            quantity=purchase_data.quantity,
            unit_cost=purchase_data.unit_cost,
            total_cost=total_cost,
        )

        product.current_stock += purchase_data.quantity

        db.add(purchase)
        db.flush()  # gives the purchase an id before saving
        record_movement(db, product.id, purchase_data.quantity, "purchase",
                        "Purchase recorded", "purchase", purchase.id)
        db.commit()
        db.refresh(purchase)

        return {
            "message": "Purchase recorded successfully",
            "purchase_id": purchase.id,
            "product_id": product.id,
            "quantity_added": purchase_data.quantity,
            "current_stock": product.current_stock,
            "total_cost": float(purchase.total_cost),
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Purchase could not be recorded")


@router.get("/purchases")
def get_purchases(db: Session = Depends(get_db)):
    """List all purchase lines, newest first.

    Args:
        db: Database session, injected by FastAPI.

    Returns:
        List of Purchase records. For a grouped view with supplier and
        product names, use /purchases-history instead.
    """
    return db.query(Purchase).order_by(Purchase.id.desc()).all()


@router.get("/purchases/{purchase_id}")
def get_purchase(purchase_id: int, db: Session = Depends(get_db)):
    """Get one purchase line by ID.

    Args:
        purchase_id: ID of the purchase.
        db: Database session, injected by FastAPI.

    Returns:
        The Purchase record.

    Raises:
        HTTPException: 404 if the purchase does not exist.
    """
    purchase = db.query(Purchase).filter(Purchase.id == purchase_id).first()
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return purchase


@router.put("/purchases/{purchase_id}")
def update_purchase(purchase_id: int, purchase_data: PurchaseCreate,
                    db: Session = Depends(get_db)):
    """Edit a purchase and correct the stock to match.

    The old quantity is taken back out of the old product's stock and the new
    quantity is added to the (possibly different) new product, each with its
    own "adjustment" entry in the stock history, so the audit trail shows
    exactly what changed. All of it is saved in one transaction.

    The edit is refused if the old product no longer has enough stock to take
    the old quantity back out (for example, some of it has already been sold),
    because that would push stock below zero.

    Args:
        purchase_id: ID of the purchase to edit.
        purchase_data: New supplier, product, quantity and unit cost.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with a message, purchase_id, product_id, quantity and total_cost.

    Raises:
        HTTPException: 404 if the purchase, supplier or product does not
            exist, 400 if the new product is deactivated or stock would exceed
            MAX_STOCK, 409 if current stock is below the old quantity, 500 on
            unexpected errors (everything is rolled back).
    """
    try:
        purchase = db.query(Purchase).filter(
            Purchase.id == purchase_id
        ).with_for_update().first()
        if purchase is None:
            raise HTTPException(status_code=404, detail="Purchase not found")

        supplier = db.query(Supplier).filter(
            Supplier.id == purchase_data.supplier_id
        ).first()
        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found")

        new_product = db.query(Product).filter(
            Product.id == purchase_data.product_id
        ).with_for_update().first()
        if new_product is None:
            raise HTTPException(status_code=404, detail="Product not found")

        # Moving a purchase onto a different product: that product must be active.
        if new_product.id != purchase.product_id and not new_product.is_active:
            raise HTTPException(status_code=400, detail="Product is deactivated")

        old_product_id = purchase.product_id
        old_quantity = purchase.quantity

        if old_product_id == new_product.id:
            old_product = new_product
        else:
            old_product = db.query(Product).filter(
                Product.id == old_product_id
            ).with_for_update().first()
            if old_product is None:
                raise HTTPException(status_code=500, detail="Original product not found")

        if old_product.current_stock < old_quantity:
            raise HTTPException(
                status_code=409,
                detail="Cannot update: current stock is below the previous purchase quantity"
            )

        total_cost = calc_total(purchase_data.quantity, purchase_data.unit_cost)

        old_product.current_stock -= old_quantity
        record_movement(db, old_product.id, -old_quantity, "adjustment",
                        f"Purchase #{purchase.id} edited: old quantity reversed",
                        "purchase", purchase.id)

        new_product.current_stock += purchase_data.quantity
        if new_product.current_stock > MAX_STOCK:
            raise HTTPException(
                status_code=400,
                detail=f"Stock cannot exceed {MAX_STOCK:,} units"
            )
        record_movement(db, new_product.id, purchase_data.quantity, "adjustment",
                        f"Purchase #{purchase.id} edited: new quantity applied",
                        "purchase", purchase.id)

        purchase.supplier_id = purchase_data.supplier_id
        purchase.product_id = purchase_data.product_id
        purchase.quantity = purchase_data.quantity
        purchase.unit_cost = purchase_data.unit_cost
        purchase.total_cost = total_cost

        db.commit()
        db.refresh(purchase)

        return {
            "message": "Purchase updated successfully",
            "purchase_id": purchase.id,
            "product_id": purchase.product_id,
            "quantity": purchase.quantity,
            "total_cost": float(purchase.total_cost),
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Purchase could not be updated")


@router.delete("/purchases/{purchase_id}")
def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    """Delete a purchase and take its units back out of stock.

    The removal is written to the stock history as an "adjustment" before the
    purchase row is deleted, all in one transaction. The delete is refused if
    the product no longer has enough stock (for example, some of it has
    already been sold), because that would push stock below zero.

    Args:
        purchase_id: ID of the purchase to delete.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with a message and stock_removed (units taken out of stock).

    Raises:
        HTTPException: 404 if the purchase does not exist, 409 if current
            stock is below the purchase quantity, 500 on unexpected errors
            (everything is rolled back).
    """
    try:
        purchase = db.query(Purchase).filter(
            Purchase.id == purchase_id
        ).with_for_update().first()
        if purchase is None:
            raise HTTPException(status_code=404, detail="Purchase not found")

        product = db.query(Product).filter(
            Product.id == purchase.product_id
        ).with_for_update().first()
        if product is None:
            raise HTTPException(status_code=500,
                                detail="Product associated with purchase not found")

        if product.current_stock < purchase.quantity:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete: current stock is below the purchase quantity"
            )

        removed = purchase.quantity
        product.current_stock -= purchase.quantity
        record_movement(db, product.id, -purchase.quantity, "adjustment",
                        f"Purchase #{purchase.id} deleted", "purchase", purchase.id)
        db.delete(purchase)
        db.commit()

        return {"message": "Purchase deleted successfully", "stock_removed": removed}

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Purchase could not be deleted")


@router.post("/purchases-bulk")
def create_purchase_bulk(data: PurchaseBulkCreate, db: Session = Depends(get_db)):
    """Many products in one purchase: all lines succeed, or none do.

    Lines for the same product are merged before checking limits. Product
    rows are locked in ID order, which prevents two bulk requests from
    blocking each other in a deadlock. Every line becomes one Purchase row
    sharing a generated reference (e.g. PUR-1A2B3C4D), and each line writes
    its own stock-history entry. Everything is saved in one transaction.

    Args:
        data: Supplier ID and the list of lines (product_id, quantity,
            unit_cost) from the request body.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with the shared reference, the number of lines and total_amount.

    Raises:
        HTTPException: 404 if the supplier or any product does not exist, 400
            if any product is deactivated or would exceed MAX_STOCK, 500 on
            unexpected errors (nothing is saved).
    """
    try:
        supplier = db.query(Supplier).filter(Supplier.id == data.supplier_id).first()
        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found")

        added = {}
        for line in data.items:
            added[line.product_id] = added.get(line.product_id, 0) + line.quantity

        ids = sorted(added)
        products = (
            db.query(Product).filter(Product.id.in_(ids))
            .order_by(Product.id).with_for_update().all()
        )
        by_id = {p.id: p for p in products}
        for pid in ids:
            product = by_id.get(pid)
            if product is None:
                raise HTTPException(status_code=404, detail=f"Product {pid} not found")
            if not product.is_active:
                raise HTTPException(status_code=400, detail=f"{product.name} is deactivated")
            if product.current_stock + added[pid] > MAX_STOCK:
                raise HTTPException(
                    status_code=400,
                    detail=f"{product.name}: stock cannot exceed {MAX_STOCK:,} units"
                )

        reference = f"PUR-{uuid.uuid4().hex[:8].upper()}"
        total = Decimal("0")
        for line in data.items:
            product = by_id[line.product_id]
            amount = calc_total(line.quantity, line.unit_cost)
            purchase = Purchase(supplier_id=supplier.id, product_id=product.id,
                                quantity=line.quantity, unit_cost=line.unit_cost,
                                total_cost=amount, reference=reference)
            product.current_stock += line.quantity
            db.add(purchase)
            db.flush()
            record_movement(db, product.id, line.quantity, "purchase",
                            f"Purchase {reference}", "purchase", purchase.id)
            total += amount

        db.commit()
        return {"reference": reference, "lines": len(data.items),
                "total_amount": float(total)}

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not record purchase")


@router.get("/purchases-history")
def get_purchases_history(limit: int = 200, db: Session = Depends(get_db)):
    """Get purchase history grouped by reference, newest first.

    Lines that share a reference (one bulk purchase) are shown as one entry
    with their lines listed inside. Older single purchases without a
    reference get a generated one like PUR-12.

    Args:
        limit: Maximum number of purchase lines to read, clamped to 1-5000
            (default 200). This counts lines, not grouped purchases.
        db: Database session, injected by FastAPI.

    Returns:
        List of dicts with reference, date, supplier, total_amount and lines
        (each with product_name, quantity, unit_cost and total_amount).
    """
    limit = max(1, min(limit, 5000))
    rows = (
        db.query(Purchase, Product.name, Supplier.name)
        .join(Product, Product.id == Purchase.product_id)
        .join(Supplier, Supplier.id == Purchase.supplier_id)
        .order_by(Purchase.id.desc()).limit(limit).all()
    )
    groups = {}
    for purchase, product_name, supplier_name in rows:
        ref = purchase.reference or f"PUR-{purchase.id}"
        g = groups.setdefault(ref, {"reference": ref, "date": purchase.purchase_date,
                                    "supplier": supplier_name, "total_amount": 0.0,
                                    "lines": []})
        g["total_amount"] = round(g["total_amount"] + float(purchase.total_cost), 2)
        g["lines"].append({"product_name": product_name, "quantity": purchase.quantity,
                           "unit_cost": float(purchase.unit_cost),
                           "total_amount": float(purchase.total_cost)})
    return list(groups.values())