from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class ObjectJSONParser(JSONParser):
    """All project write endpoints accept object documents, never root arrays."""

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(
            stream, media_type=media_type, parser_context=parser_context
        )
        if not isinstance(data, dict):
            raise ParseError("JSON request body must be an object.")
        return data
