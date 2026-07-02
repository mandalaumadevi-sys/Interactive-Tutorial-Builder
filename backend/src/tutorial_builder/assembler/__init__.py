"""Deterministic assembly of the final single-file interactive tutorial (Jinja2)."""

from .html_assembler import output_filename, render, write_tutorial

__all__ = ["render", "write_tutorial", "output_filename"]
