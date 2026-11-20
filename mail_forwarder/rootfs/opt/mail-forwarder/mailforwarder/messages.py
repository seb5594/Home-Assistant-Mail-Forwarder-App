"""Messages that reach the user are a code plus parameters; the web interface translates them.

``Message`` is the common base of the application's errors. ``TEXTS`` holds the English wording
that goes to the log of the Supervisor, where there is no translation.
"""


class Message(Exception):
    """An error or notice with a stable ``code`` and ``params`` for the translations."""

    texts: dict = {}

    def __init__(self, code: str, **params):
        self.code = code
        self.params = params
        template = self.texts.get(code, code)
        try:
            super().__init__(template.format(**params))
        except (KeyError, IndexError):
            super().__init__(template)

    def as_dict(self) -> dict:
        return {"code": self.code, "params": self.params}
