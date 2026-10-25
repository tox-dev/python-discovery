Contributing
============

Changes that affect users need a reStructuredText fragment in ``docs/changelog``. Name it
``+short-description.category.rst``; the release process links the fragment to its merged pull request, so the
filename needs no pull request number. Keep one change per fragment and describe the effect on users.

Use ``feature`` for a new capability or a Python support change, ``change`` for changed behavior, ``bugfix`` for a
fix, and ``doc`` for user documentation. ``security``, ``performance``, ``deprecation``, ``removal``, and
``packaging`` are available when those distinctions help users. A pull request with no user-facing change needs the
``skip news`` label. Bots get that label automatically unless their pull request includes a fragment.

For example, a fix to interpreter discovery could use ``docs/changelog/+find-venv.bugfix.rst``:

.. code-block:: rst

   Find a virtual environment's base interpreter when its executable is a symlink.

Don't write credits by hand. Each entry credits the merged pull request's commit author and co-authors, computed when
the changelog is built, and release preparation runs ``release-creator contributors`` to add a New Contributors
subsection. GitHub Release notes are rendered as Markdown from the tagged reStructuredText section. Release preparation
runs the repository's ``prek`` checks before creating the release commit and annotated tag.
