class FSError(Exception):
    pass


class CreateFailed(FSError):
    pass


class FilesystemClosed(FSError):
    pass


class MissingInfoNamespace(FSError):
    pass


class NoSysPath(FSError):
    pass


class OperationFailed(FSError):
    pass


class IllegalDestination(OperationFailed):
    pass


class ResourceError(FSError):
    pass


class ResourceNotFound(ResourceError):
    pass


class DirectoryExpected(ResourceError):
    pass


class DirectoryNotEmpty(ResourceError):
    pass


class FileExpected(ResourceError):
    pass


class DestinationExists(ResourceError):
    pass


class ResourceReadOnly(ResourceError):
    pass
