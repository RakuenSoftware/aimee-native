"""Unbound source-development bridge; installed plugins provide their own binding.

The source package can construct explicit adapter ABI calls and validate command
configuration. Enrollment and serving use the dedicated installed model command.
"""
BOUND_ADAPTER = None
PLUGIN_NAME = "aimee_native"
