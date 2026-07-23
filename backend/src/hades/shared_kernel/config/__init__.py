"""Configuration bootstrapping. Import :func:`get_settings` everywhere."""

from hades.shared_kernel.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
