#!/usr/bin/env python3
"""Data models for the test project."""
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class User:
    """Represents a user in the system."""
    email: str
    name: str
    age: Optional[int] = None
    
    def __post_init__(self):
        """Validate user data after initialization."""
        if not self.email:
            raise ValueError("Email is required")
        if not self.name:
            raise ValueError("Name is required")
    
    def get_display_name(self) -> str:
        """Get the display name for the user."""
        return self.name
    
    def is_adult(self) -> bool:
        """Check if user is an adult."""
        if self.age is None:
            return False
        return self.age >= 18


@dataclass
class Product:
    """Represents a product in the catalog."""
    name: str
    price: float
    description: Optional[str] = None
    stock: int = 0
    
    def is_available(self) -> bool:
        """Check if product is in stock."""
        return self.stock > 0
    
    def apply_discount(self, percent: float) -> float:
        """Apply a discount to the price.
        
        Args:
            percent: Discount percentage (0-100)
            
        Returns:
            Discounted price
        """
        if percent < 0 or percent > 100:
            raise ValueError("Discount must be between 0 and 100")
        return self.price * (1 - percent / 100)


class Order:
    """Represents a customer order."""
    
    def __init__(self, user: User):
        """Initialize an order for a user."""
        self.user = user
        self.items: List[tuple[Product, int]] = []
        self.status = "pending"
    
    def add_item(self, product: Product, quantity: int = 1):
        """Add a product to the order."""
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        self.items.append((product, quantity))
    
    def calculate_total(self) -> float:
        """Calculate the total order amount."""
        total = 0.0
        for product, quantity in self.items:
            total += product.price * quantity
        return total
    
    def submit(self) -> bool:
        """Submit the order for processing."""
        if not self.items:
            return False
        self.status = "submitted"
        return True
