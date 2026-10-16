"""Supplier endpoints, plus a supplier's products and purchase history."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Product, Supplier, Purchase
from schemas.supplier import SupplierCreate

router = APIRouter(tags=["Suppliers"])


def check_supplier_name_free(db, name, exclude_id=None):
    """Make sure no other supplier already uses this name (case-insensitive).

    Args:
        db: SQLAlchemy session.
        name: The supplier name to check.
        exclude_id: Supplier ID to ignore, used when editing a supplier so it
            doesn't clash with its own name.

    Raises:
        HTTPException: 409 if another supplier already has this name.
    """
    query = db.query(Supplier).filter(func.lower(Supplier.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(Supplier.id != exclude_id)
    if query.first() is not None:
        raise HTTPException(status_code=409, detail=f"A supplier named '{name}' already exists")


@router.post("/suppliers")
def create_supplier(supplier_data: SupplierCreate, db: Session = Depends(get_db)):
    """Create a new supplier.

    Args:
        supplier_data: Supplier details from the request body (name, contact
            person, email, phone, address, lead time).
        db: Database session, injected by FastAPI.

    Returns:
        The created Supplier record.

    Raises:
        HTTPException: 409 if a supplier with the same name already exists.
    """
    check_supplier_name_free(db, supplier_data.name)
    supplier = Supplier(**supplier_data.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("/suppliers")
def get_suppliers(db: Session = Depends(get_db)):
    """List all suppliers, ordered by ID.

    Args:
        db: Database session, injected by FastAPI.

    Returns:
        List of Supplier records.
    """
    return db.query(Supplier).order_by(Supplier.id).all()


@router.get("/suppliers/{supplier_id}")
def get_supplier(supplier_id: int, db: Session = Depends(get_db)):
    """Get one supplier by ID.

    Args:
        supplier_id: ID of the supplier.
        db: Database session, injected by FastAPI.

    Returns:
        The Supplier record.

    Raises:
        HTTPException: 404 if the supplier does not exist.
    """
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@router.put("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, supplier_data: SupplierCreate,
                    db: Session = Depends(get_db)):
    """Edit a supplier's details.

    All fields are replaced with the values sent. The name uniqueness check
    only runs if the name actually changed (ignoring upper/lower case), so
    saving a supplier without renaming it never clashes with itself.

    Args:
        supplier_id: ID of the supplier to edit.
        supplier_data: New supplier details from the request body.
        db: Database session, injected by FastAPI.

    Returns:
        The updated Supplier record.

    Raises:
        HTTPException: 404 if the supplier does not exist, 409 if the new
            name is used by another supplier.
    """
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    if supplier_data.name.lower() != supplier.name.lower():
        check_supplier_name_free(db, supplier_data.name, exclude_id=supplier.id)

    for field, value in supplier_data.model_dump().items():
        setattr(supplier, field, value)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: int, db: Session = Depends(get_db)):
    """Permanently delete a supplier that has no purchase history.

    The delete is refused while the supplier still has active products. For
    inactive products, the supplier link is cleared first (set to none) so
    they don't block the delete. If the supplier has purchases, the database
    blocks the delete and everything, including the cleared links, is rolled
    back.

    Args:
        supplier_id: ID of the supplier to delete.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with a confirmation message.

    Raises:
        HTTPException: 404 if the supplier does not exist, 409 if the supplier
            has active products or purchase history.
    """
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Active products still depend on this supplier: block the delete.
    active_count = (
        db.query(Product)
        .filter(Product.supplier_id == supplier_id, Product.is_active.is_(True))
        .count()
    )
    if active_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"This supplier still has {active_count} active product(s). "
                   "Deactivate or reassign them first."
        )

    try:
        (db.query(Product)
           .filter(Product.supplier_id == supplier_id)
           .update({Product.supplier_id: None}, synchronize_session=False))
        db.delete(supplier)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This supplier has purchase history and cannot be deleted."
        )
    return {"message": "Supplier deleted successfully"}


@router.get("/suppliers/{supplier_id}/products")
def get_supplier_products(supplier_id: int, db: Session = Depends(get_db)):
    """List the products linked to a supplier (active and inactive).

    Args:
        supplier_id: ID of the supplier.
        db: Database session, injected by FastAPI.

    Returns:
        List of Product records, ordered by ID.

    Raises:
        HTTPException: 404 if the supplier does not exist.
    """
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return (db.query(Product).filter(Product.supplier_id == supplier_id)
            .order_by(Product.id).all())


@router.get("/suppliers/{supplier_id}/purchases")
def get_supplier_purchases(supplier_id: int, db: Session = Depends(get_db)):
    """Get the purchase history for one supplier, with a spending total.

    Each purchase line is listed separately, newest first. The totals are
    calculated from the recorded purchases, not stored.

    Args:
        supplier_id: ID of the supplier.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with supplier (name), purchase_count, total_spent and purchases
        (each with purchase_id, product_id, product_name, quantity, unit_cost,
        total_cost and purchase_date).

    Raises:
        HTTPException: 404 if the supplier does not exist.
    """
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    rows = (
        db.query(Purchase, Product.name)
        .join(Product, Product.id == Purchase.product_id)
        .filter(Purchase.supplier_id == supplier_id)
        .order_by(Purchase.id.desc())
        .all()
    )
    history = [
        {
            "purchase_id": p.id,
            "product_id": p.product_id,
            "product_name": name,
            "quantity": p.quantity,
            "unit_cost": float(p.unit_cost),
            "total_cost": float(p.total_cost),
            "purchase_date": p.purchase_date,
        }
        for p, name in rows
    ]
    return {
        "supplier": supplier.name,
        "purchase_count": len(history),
        "total_spent": round(sum(h["total_cost"] for h in history), 2),
        "purchases": history,
    }