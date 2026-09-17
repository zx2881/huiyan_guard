class VisionError(Exception):
    """Base class for safe, user-facing vision failures."""


class VisionNetworkError(VisionError):
    pass


class VisionTimeoutError(VisionError):
    pass


class VisionProviderError(VisionError):
    pass


class VisionOutputError(VisionError):
    pass
