"""Product endpoints: create, list, edit, delete, activate / deactivate, set supplier."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Product, Supplier
from schemas.product import ProductCreate, ProductUpdate, ProductSupplierUpdate
from services.stock import record_movement, low_stock_filter

router = APIRouter(tags=["Products"])


def check_supplier_exists(db, supplier_id):
    """Make sure a supplier exists before linking a product to it.

    A supplier_id of None is allowed, because a product can have no supplier.

    Args:
        db: SQLAlchemy session.
        supplier_id: ID of the supplier to check, or None.

    Raises:
        HTTPException: 404 if a supplier_id is given but no such supplier exists.
    """
    if supplier_id is not None:
        if db.query(Supplier).filter(Supplier.id == supplier_id).first() is None:
            raise HTTPException(status_code=404, detail="Supplier not found")


def check_product_rules(data):
    """Validate business rules on product prices.

    Args:
        data: ProductCreate or ProductUpdate payload with purchase_price and
            selling_price.

    Raises:
        HTTPException: 400 if the selling price is lower than the purchase cost.
    """
    if data.selling_price < data.purchase_price:
        raise HTTPException(
            status_code=400,
            detail="Selling price cannot be lower than the purchase cost"
        )


def check_sku_free(db, sku, exclude_id=None):
    """Make sure no other product already uses this SKU (case-insensitive).

    The SKU is compared in uppercase, so the incoming value is expected to
    already be uppercase (normalised by the request schema).

    Args:
        db: SQLAlchemy session.
        sku: The SKU to check.
        exclude_id: Product ID to ignore, used when editing a product so it
            doesn't clash with its own SKU.

    Raises:
        HTTPException: 409 if another product already uses the SKU.
    """
    query = db.query(Product).filter(func.upper(Product.sku) == sku)
    if exclude_id is not None:
        query = query.filter(Product.id != exclude_id)
    if query.first() is not None:
        raise HTTPException(status_code=409, detail=f"SKU {sku} already exists")


@router.get("/products")
def get_products(
    search: str | None = None,
    category: str | None = None,
    supplier_id: int | None = None,
    low_stock_only: bool = False,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    """List products, with optional search and filters.

    All filters are optional and can be combined. Inactive products are
    hidden unless include_inactive is true.

    Args:
        search: Text to look for in the product name or SKU (case-insensitive).
        category: Only products in this category (exact match).
        supplier_id: Only products from this supplier.
        low_stock_only: If true, only products at or below minimum stock.
        include_inactive: If true, also return deactivated products.
        db: Database session, injected by FastAPI.

    Returns:
        List of Product records, ordered by ID.
    """
    query = db.query(Product)
    if not include_inactive:
        query = query.filter(Product.is_active.is_(True))
    if search:
        pattern = f"%{search}%"
        query = query.filter(Product.name.ilike(pattern) | Product.sku.ilike(pattern))
    if category:
        query = query.filter(Product.category == category)
    if supplier_id:
        query = query.filter(Product.supplier_id == supplier_id)
    if low_stock_only:
        query = query.filter(low_stock_filter())
    return query.order_by(Product.id).all()


@router.post("/products")
def create_product(product_data: ProductCreate, db: Session = Depends(get_db)):
    """Create a new product.

    Validates prices, supplier and SKU uniqueness. If the product starts with
    stock, an "Opening stock" movement is written in the same transaction, so
    the stock history adds up from day one.

    Args:
        product_data: Product details from the request body.
        db: Database session, injected by FastAPI.

    Returns:
        The created Product record.

    Raises:
        HTTPException: 400 if the selling price is below the purchase cost,
            404 if the supplier does not exist, 409 if the SKU already exists.
    """
    check_product_rules(product_data)
    check_supplier_exists(db, product_data.supplier_id)
    check_sku_free(db, product_data.sku)

    product = Product(**product_data.model_dump())
    try:
        db.add(product)
        db.flush()
        if product.current_stock > 0:
            record_movement(db, product.id, product.current_stock, "adjustment",
                            "Opening stock", "product", product.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists")
    db.refresh(product)
    return product


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get one product by ID (active or inactive).

    Args:
        product_id: ID of the product.
        db: Database session, injected by FastAPI.

    Returns:
        The Product record.

    Raises:
        HTTPException: 404 if the product does not exist.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.put("/products/{product_id}")
def update_product(product_id: int, product_data: ProductUpdate,
                   db: Session = Depends(get_db)):
    """Edit a product's details, including its stock quantity.

    The product row is locked while it is edited, so a sale or purchase
    can't change its stock at the same moment. If the stock quantity is
    changed, the difference is written to the stock history as an
    "adjustment" in the same transaction.

    Args:
        product_id: ID of the product to edit.
        product_data: New product details from the request body.
        db: Database session, injected by FastAPI.

    Returns:
        The updated Product record.

    Raises:
        HTTPException: 400 if the selling price is below the purchase cost,
            404 if the product or supplier does not exist, 409 if the SKU
            is used by another product.
    """
    product = (
        db.query(Product).filter(Product.id == product_id).with_for_update().first()
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    check_product_rules(product_data)
    check_supplier_exists(db, product_data.supplier_id)
    check_sku_free(db, product_data.sku, exclude_id=product.id)

    stock_diff = product_data.current_stock - product.current_stock

    product.name = product_data.name
    product.sku = product_data.sku
    product.category = product_data.category
    product.purchase_price = product_data.purchase_price
    product.selling_price = product_data.selling_price
    product.minimum_stock = product_data.minimum_stock
    product.supplier_id = product_data.supplier_id
    product.current_stock = product_data.current_stock

    try:
        if stock_diff != 0:
            record_movement(db, product.id, stock_diff, "adjustment",
                            "Stock updated from products edit form", "product", product.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists")

    db.refresh(product)
    return product


@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Permanently delete a product that has no history.

    Products that already have sales, purchases or stock history can't be
    deleted, because the database blocks it. Deactivate those instead.

    Args:
        product_id: ID of the product to delete.
        db: Database session, injected by FastAPI.

    Returns:
        Dict with a confirmation message.

    Raises:
        HTTPException: 404 if the product does not exist, 409 if it has
            related records.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        db.delete(product)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This product has sales, purchases or stock history. Deactivate it instead."
        )
    return {"message": "Product deleted successfully"}


def set_product_active(product_id: int, active: bool, db: Session):
    """Turn a product on or off (shared by the activate and deactivate endpoints).

    Args:
        product_id: ID of the product.
        active: True to activate, False to deactivate.
        db: SQLAlchemy session.

    Returns:
        The updated Product record.

    Raises:
        HTTPException: 404 if the product does not exist.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = active
    db.commit()
    db.refresh(product)
    return product


@router.patch("/products/{product_id}/deactivate")
def deactivate_product(product_id: int, db: Session = Depends(get_db)):
    """Deactivate a product, hiding it from lists and reports but keeping its history.

    Args:
        product_id: ID of the product.
        db: Database session, injected by FastAPI.

    Returns:
        The updated Product record.

    Raises:
        HTTPException: 404 if the product does not exist.
    """
    return set_product_active(product_id, False, db)


@router.patch("/products/{product_id}/activate")
def activate_product(product_id: int, db: Session = Depends(get_db)):
    """Reactivate a previously deactivated product.

    Args:
        product_id: ID of the product.
        db: Database session, injected by FastAPI.

    Returns:
        The updated Product record.

    Raises:
        HTTPException: 404 if the product does not exist.
    """
    return set_product_active(product_id, True, db)


@router.put("/products/{product_id}/supplier")
def set_product_supplier(product_id: int, data: ProductSupplierUpdate,
                         db: Session = Depends(get_db)):
    """Change which supplier a product is linked to.

    Args:
        product_id: ID of the product.
        data: Request body with the new supplier_id (None removes the link).
        db: Database session, injected by FastAPI.

    Returns:
        The updated Product record.

    Raises:
        HTTPException: 404 if the product or supplier does not exist.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    check_supplier_exists(db, data.supplier_id)
    product.supplier_id = data.supplier_id
    db.commit()
    db.refresh(product)
    return product