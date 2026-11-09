#!/usr/bin/env python3
"""Main module for the test project."""
from utils import calculate_sum, validate_email
from models import User, Product


def main():
    """Main entry point."""
    # Create a user
    user = User("john@example.com", "John Doe")
    print(f"Created user: {user.name}")
    
    # Validate email
    if validate_email(user.email):
        print("Email is valid")
    
    # Calculate something
    result = calculate_sum([1, 2, 3, 4, 5])
    print(f"Sum: {result}")
    
    # Create a product
    product = Product("Widget", 9.99)
    print(f"Product: {product.name} - ${product.price}")


if __name__ == "__main__":
    main()
