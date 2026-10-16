from database import Base, engine
from models import Product, Supplier, Purchase, Sale

Base.metadata.create_all(bind=engine)

print("Database tables created successfully!")