"""Security Engine infrastructure — adapters for every port.

All blockchain / HTTP / database I/O lives here so the domain and application
layers stay pure. Each adapter ships with an in-memory twin used by the tests.
"""
