"""
Selectors package for customers app.
"""

from apps.customers.selectors.customers import (
    ALLOWED_ORDERING_FIELDS,
    get_customer_by_id,
    get_customer_status_summary,
    get_customers_queryset,
)

__all__ = [
    "ALLOWED_ORDERING_FIELDS",
    "get_customer_by_id",
    "get_customer_status_summary",
    "get_customers_queryset",
]
