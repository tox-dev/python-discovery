"""Sphinx configuration for python-discovery documentation."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from python_discovery import __version__

company: Final[str] = "tox-dev"
name = "python-discovery"
repository: Final[str] = f"https://github.com/{company}/{name}"
version = ".".join(__version__.split(".")[:2])
release = __version__
copyright: Final[str] = f"2026-{datetime.now(tz=timezone.utc).year}, {company}"  # ruff:ignore[builtin-variable-shadowing] Sphinx reads the name `copyright`

extensions = [
    "sphinx_llm.txt",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.extlinks",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "sphinxcontrib.mermaid",
    "sphinxcontrib.towncrier.ext",
]

towncrier_draft_autoversion_mode: Final[str] = "draft"
towncrier_draft_include_empty: Final[bool] = True
towncrier_draft_working_directory = Path(__file__).parent.parent
autosectionlabel_maxdepth: Final[int] = 2

extlinks = {
    "issue": (f"{repository}/issues/%s", "#%s"),
    "pr": (f"{repository}/pull/%s", "PR #%s"),
    "pull": (f"{repository}/pull/%s", "PR #%s"),
    "user": ("https://github.com/%s", "@%s"),
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

templates_path = []
source_suffix: Final[str] = ".rst"
exclude_patterns = ["_build", "changelog/*"]

main_doc: Final[str] = "index"
pygments_style: Final[str] = "default"
always_document_param_types: Final[bool] = True
project = name

html_theme: Final[str] = "furo"
html_title = project
html_last_updated_fmt = datetime.now(tz=timezone.utc).isoformat()
pygments_dark_style: Final[str] = "monokai"
html_show_sourcelink: Final[bool] = False
html_static_path = ["_static"]
html_theme_options = {
    "light_logo": "logo.svg",
    "dark_logo": "logo.svg",
    "sidebar_hide_name": True,
    "source_repository": repository,
    "source_branch": "main",
    "source_directory": "docs/",
    "footer_icons": [
        {
            "name": "GitHub",
            "url": repository,
            # footer icons are inlined into every page, so a path to the image would not resolve
            "html": (Path(__file__).parent / "_static" / "github.svg").read_text(encoding="utf-8"),
            "class": "",
        },
    ],
}
html_css_files = ["custom.css"]

markdown_http_base = os.environ.get("READTHEDOCS_CANONICAL_URL", "")
