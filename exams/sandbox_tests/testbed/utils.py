#!/usr/bin/env python3
"""Utility functions for the test project."""
import re
from typing import List, Optional


def calculate_sum(numbers: List[int]) -> int:
    """Calculate the sum of a list of numbers.
    
    Args:
        numbers: List of integers to sum
        
    Returns:
        The sum of all numbers
    """
    total = 0
    for num in numbers:
        total += num
    return total


def calculate_average(numbers: List[int]) -> float:
    """Calculate the average of a list of numbers.
    
    Args:
        numbers: List of integers
        
    Returns:
        The average value
    """
    if not numbers:
        return 0.0
    return calculate_sum(numbers) / len(numbers)


def validate_email(email: str) -> bool:
    """Validate an email address.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def format_currency(amount: float, currency: str = "USD") -> str:
    """Format a number as currency.
    
    Args:
        amount: The amount to format
        currency: Currency code (default: USD)
        
    Returns:
        Formatted currency string
    """
    if currency == "USD":
        return f"${amount:.2f}"
    elif currency == "EUR":
        return f"€{amount:.2f}"
    else:
        return f"{amount:.2f} {currency}"


def parse_config(config_str: str) -> dict:
    """Parse a simple key=value config string.
    
    Args:
        config_str: Configuration string with key=value pairs
        
    Returns:
        Dictionary of config values
    """
    config = {}
    for line in config_str.strip().split('\n'):
        if '=' in line:
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
    return config
