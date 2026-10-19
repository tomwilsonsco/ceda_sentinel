class ImageReadError(RuntimeError):
    """
    Raised when every image checked for the AOI features failed with a read error.

    This usually means CEDA is unavailable (outage, HTTP error or timeout), rather
    than that no suitable images exist.

    Attributes:
        read_errors (list): One dict per failed check, with keys 'feature_id',
            'image_link', 'check' and 'error'.
    """

    def __init__(self, read_errors):
        self.read_errors = read_errors
        super().__init__(
            f"All {len(read_errors)} image checks failed with read errors. "
            f"First error: {read_errors[0]['error']}"
        )
