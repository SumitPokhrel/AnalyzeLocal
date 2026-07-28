"""Document pipeline: extract text, redact PII, then analyze the redacted text.

The order matters. Nothing in analyze.py may ever see text that has not been
through redact.py.
"""
