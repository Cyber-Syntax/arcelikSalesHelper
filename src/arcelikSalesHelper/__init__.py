from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("arcelikSalesHelper")
except PackageNotFoundError:
    # Fallback for development environments where package isn't installed
    __version__ = "dev"
