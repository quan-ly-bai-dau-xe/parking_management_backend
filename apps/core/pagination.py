"""
Standard pagination classes for Parking Management Backend.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """
    Phân trang chuẩn cho các danh sách API:
    - Kích thước trang mặc định: 20
    - Cho phép client tùy chỉnh kích thước trang qua query param: page_size
    - Kích thước trang tối đa: 100
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
