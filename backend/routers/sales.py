"""Sale endpoints (stock going out): single product, many products, and history."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Product, Sale
from schemas.sale import SaleCreate, SaleBulkCreate
from services.stock import record_movement
from utils.validation import calc_total

router = APIRouter(tags=["Sales"])


@router.post("/sales")
def create_sale(sale: SaleCreate, db: Session = Depends(get_db)):
    """Record a sale of one product and take the units out of stock.

    The product row is locked while this runs, so two sales can't both pass
    the stock check and push stock below zero. The sale, the stock decrease
    and the stock-history entry are saved together in one transaction: if
    anything fails, none of them are saved. The total is calculated by the
    backend, never taken from the request.

    Args:
        sale: Product, quantity and unit price from the request body.
        db: Database session, injected by FastAPI.

    Returns:
        The created Sale record.

    Raises:
        HTTPException: 404 if the product does not exist, 400 if the product
            is deactivated or there is not enough stock, 500 on unexpected
            errors (everything is rolled back).
    """
    try:
        product = (
            db.query(Product).filter(Product.id == sale.product_id)
            .with_for_update().first()
        )
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        if not product.is_active:
            raise HTTPException(status_code=400, detail="Product is deactivated")
        if product.current_stock < sale.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock. Available: {product.current_stock}"
            )

        new_sale = Sale(
            product_id=sale.product_id,
            quantity=sale.quantity,
            unit_price=sale.unit_price,
            total_amount=calc_total(sale.quantity, sale.unit_price),
        )

        product.current_stock -= sale.quantity
        db.add(new_sale)
        db.flush()
        record_movement(db, product.id, -sale.quantity, "sale",
                        "Sale recorded", "sale", new_sale.id)
        db.commit()
        db.refresh(new_sale)
        return new_sale

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create sale")


@router.get("/sales")
def get_sales(db: Session = Depends(get_db)):
    """List all sale lines, newest first.

    Args:
        db: Database session, injected by FastAPI.

    Returns:
        List of Sale records. For a grouped view with product names, use
        /sales-history instead.
    """
    return db.query(Sale).order_by(Sale.id.desc()).all()


@router.get("/sales/{sale_id}")
def get_sale(sale_id: int, db: Session = Depends(get_db)):
    """Get one sale line by ID.

    Args:
        sale_id: ID of the sale.
        db: Database session, injected by FastAPI.

    Returns:
        The Sale record.

    Raises:
        HTTPException: 404 if the sale does not exist.
    """
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    return sale


@router.put("/sales/{sale_id}")
def update_sale(sale_id: int, updated_data: SaleCreate, db: Session = Depends(get_db)):
    """Edit a sale and correct the stock to match.

    The old quantity is put back into the old product's stock, then the new
    quantity is taken out of the (possibly different) new product, each with
    its own "adjustment" entry in the stock history. Product rows are locked
    in ID order to avoid deadlocks with other requests. If the new quantity
    is more than the stock available, the whole edit is rolled back and
    nothing changes.

    Args:
        sale_id: ID of the sale to edit.
        updated_data: New product, quantity and unit price.
        db: Database session, injected by FastAPI.

    Returns:
        The updated Sale record.

    Raises:
        HTTPException: 404 if the sale or product does not exist, 400 if the
            new product is deactivated or has insufficient stock, 500 on
            unexpected errors (everything is rolled back).
    """
    try:
        sale = db.query(Sale).filter(Sale.id == sale_id).with_for_update().first()
        if sale is None:
            raise HTTPException(status_code=404, detail="Sale not found")

        product_ids = sorted({sale.product_id, updated_data.product_id})
        products = (
            db.query(Product).filter(Product.id.in_(product_ids))
            .order_by(Product.id).with_for_update().all()
        )
        products_by_id = {product.id: product for product in products}

        old_product = products_by_id.get(sale.product_id)
        new_product = products_by_id.get(updated_data.product_id)
        if old_product is None or new_product is None:
            raise HTTPException(status_code=404, detail="Product not found")

        # Moving a sale onto a different product: that product must be active.
        if new_product.id != sale.product_id and not new_product.is_active:
            raise HTTPException(status_code=400, detail="Product is deactivated")

        total_amount = calc_total(updated_data.quantity, updated_data.unit_price)

        old_product.current_stock += sale.quantity
        record_movement(db, old_product.id, sale.quantity, "adjustment",
                        f"Sale #{sale.id} edited: old quantity restored", "sale", sale.id)

        if new_product.current_stock < updated_data.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock. Available: {new_product.current_stock}"
            )

        new_product.current_stock -= updated_data.quantity
        record_movement(db, new_product.id, -updated_data.quantity, "adjustment",
                        f"Sale #{sale.id} edited: new quantity applied", "sale", sale.id)

        sale.product_id = updated_data.product_id
        sale.quantity = updated_data.quantity
        sale.unit_price = updated_data.unit_price
        sale.total_amount = total_amount

        db.commit()
        db.refresh(sale)
        return sale

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not update sale")


@router.delete("/sales/{sale_id}")
def delete_sale(sale_id: int, db: Session = Depends(get_db)):
    """Delete a sale and put its units back into stock.

    The restored units are written to the stock history before the sale row
    is deleted, all in one transaction.

    Args:
        sale_id: ID of the sale to delete.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with a confirmation message.

    Raises:
        HTTPException: 404 if the sale or its product does not exist, 500 on
            unexpected errors (everything is rolled back).
    """
    try:
        sale = db.query(Sale).filter(Sale.id == sale_id).with_for_update().first()
        if sale is None:
            raise HTTPException(status_code=404, detail="Sale not found")

        product = (
            db.query(Product).filter(Product.id == sale.product_id)
            .with_for_update().first()
        )
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")

        product.current_stock += sale.quantity
        record_movement(db, product.id, sale.quantity, "return",
                        f"Sale #{sale.id} deleted, stock restored", "sale", sale.id)
        db.delete(sale)
        db.commit()

        return {"message": "Sale deleted and stock restored successfully"}

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not delete sale")


@router.post("/sales-bulk")
def create_sale_bulk(data: SaleBulkCreate, db: Session = Depends(get_db)):
    """Many products in one sale: all lines succeed, or none do.

    Quantities for the same product are added up before checking stock, so
    selling the same product on two lines can't sneak past the limit. Product
    rows are locked in ID order to avoid deadlocks. Every line becomes one
    Sale row sharing a generated reference (e.g. SALE-1A2B3C4D), and each
    line writes its own stock-history entry. Everything is saved in one
    transaction.

    Args:
        data: The list of lines (product_id, quantity, unit_price) from the
            request body.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with the shared reference, the number of lines and total_amount.

    Raises:
        HTTPException: 404 if any product does not exist, 400 if any product
            is deactivated or has insufficient stock, 500 on unexpected
            errors (nothing is saved).
    """
    try:
        needed = {}
        for line in data.items:
            needed[line.product_id] = needed.get(line.product_id, 0) + line.quantity

        products = (
            db.query(Product).filter(Product.id.in_(list(needed)))
            .order_by(Product.id).with_for_update().all()
        )
        by_id = {p.id: p for p in products}

        for pid, qty in needed.items():
            product = by_id.get(pid)
            if product is None:
                raise HTTPException(status_code=404, detail=f"Product {pid} not found")
            if not product.is_active:
                raise HTTPException(status_code=400, detail=f"{product.name} is deactivated")
            if product.current_stock < qty:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for {product.name}. Available: {product.current_stock}"
                )

        reference = f"SALE-{uuid.uuid4().hex[:8].upper()}"
        total = Decimal("0")
        for line in data.items:
            product = by_id[line.product_id]
            amount = calc_total(line.quantity, line.unit_price)
            sale = Sale(product_id=product.id, quantity=line.quantity,
                        unit_price=line.unit_price, total_amount=amount,
                        reference=reference)
            product.current_stock -= line.quantity
            db.add(sale)
            db.flush()
            record_movement(db, product.id, -line.quantity, "sale",
                            f"Sale {reference}", "sale", sale.id)
            total += amount

        db.commit()
        return {"reference": reference, "lines": len(data.items),
                "total_amount": float(total)}

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not record sale")


@router.get("/sales-history")
def get_sales_history(limit: int = 200, db: Session = Depends(get_db)):
    """Get sales history grouped by reference, newest first.

    Lines that share a reference (one bulk sale) are shown as one entry with
    their lines listed inside. Older single sales without a reference get a
    generated one like SALE-12.

    Args:
        limit: Maximum number of sale lines to read, clamped to 1-5000
            (default 200). This counts lines, not grouped sales.
        db: Database session, injected by FastAPI.

    Returns:
        List of dicts with reference, date, total_amount and lines (each with
        product_name, quantity, unit_price and total_amount).
    """
    limit = max(1, min(limit, 5000))
    rows = (
        db.query(Sale, Product.name)
        .join(Product, Product.id == Sale.product_id)
        .order_by(Sale.id.desc()).limit(limit).all()
    )
    groups = {}
    for sale, product_name in rows:
        ref = sale.reference or f"SALE-{sale.id}"
        g = groups.setdefault(ref, {"reference": ref, "date": sale.sale_date,
                                    "total_amount": 0.0, "lines": []})
        g["total_amount"] = round(g["total_amount"] + float(sale.total_amount), 2)
        g["lines"].append({"product_name": product_name, "quantity": sale.quantity,
                           "unit_price": float(sale.unit_price),
                           "total_amount": float(sale.total_amount)})
    return list(groups.values())