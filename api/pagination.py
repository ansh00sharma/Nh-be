from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.utils.urls import remove_query_param, replace_query_param


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


class NoCountPageNumberPagination(StandardPageNumberPagination):
    def paginate_queryset(self, queryset, request, view=None):
        self.request = request
        self.page_size = self.get_page_size(request)
        if not self.page_size:
            return None

        self.page_number = self.get_page_number(request, None)
        self.offset = (self.page_number - 1) * self.page_size
        results = list(queryset[self.offset : self.offset + self.page_size + 1])
        self.has_next = len(results) > self.page_size
        self.has_previous = self.page_number > 1
        return results[: self.page_size]

    def get_page_number(self, request, paginator):
        raw_page = request.query_params.get(self.page_query_param, 1)
        try:
            page_number = int(raw_page)
        except (TypeError, ValueError):
            raise NotFound(self.invalid_page_message.format(page_number=raw_page, message="That page number is not an integer"))
        if page_number < 1:
            raise NotFound(self.invalid_page_message.format(page_number=raw_page, message="That page number is less than 1"))
        return page_number

    def get_next_link(self):
        if not self.has_next:
            return None
        url = self.request.build_absolute_uri()
        return replace_query_param(url, self.page_query_param, self.page_number + 1)

    def get_previous_link(self):
        if not self.has_previous:
            return None
        url = self.request.build_absolute_uri()
        previous_page = self.page_number - 1
        if previous_page == 1:
            return remove_query_param(url, self.page_query_param)
        return replace_query_param(url, self.page_query_param, previous_page)

    def get_paginated_response(self, data):
        return Response(
            {
                "count": None,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
