from rest_framework.pagination import PageNumberPagination


class StandardPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50
    allowed_page_sizes = {10, 20, 50}

    def get_page_size(self, request):
        raw_page_size = request.query_params.get(self.page_size_query_param)
        if raw_page_size is None:
            return self.page_size

        try:
            page_size = int(raw_page_size)
        except (TypeError, ValueError):
            return self.page_size

        if page_size not in self.allowed_page_sizes:
            return self.page_size

        return page_size
