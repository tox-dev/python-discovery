"""Sphinx configuration for python-discovery documentation."""

from __future__ import annotations

from datetime import datetime, timezone

from python_discovery import __version__

company = "tox-dev"
name = "python-discovery"
version = ".".join(__version__.split(".")[:2])
release = __version__
copyright = f"2026-{datetime.now(tz=timezone.utc).year}, {company}"  # noqa: A001

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.extlinks",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "sphinxcontrib.mermaid",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

templates_path = []
source_suffix = ".rst"
exclude_patterns = ["_build"]

main_doc = "index"
pygments_style = "default"
always_document_param_types = True
project = name

html_theme = "furo"
html_title = project
html_last_updated_fmt = datetime.now(tz=timezone.utc).isoformat()
pygments_dark_style = "monokai"
html_show_sourcelink = False
html_static_path = ["_static"]
html_theme_options = {
    "light_logo": "logo.svg",
    "dark_logo": "logo.svg",
    "sidebar_hide_name": True,
}
html_css_files = ["custom.css"]
