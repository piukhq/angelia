from pathlib import Path

from setuptools import find_packages, setup

from app.version import __version__

setup(
    name="Angelia",
    version=__version__,
    author="Martin Marsh",
    author_email="mmarsh@bink.com",
    description="Bink API 2.0 Angelia Front End",
    packages=[".", *find_packages()],
    long_description=Path("README.md").read_text(),
    long_description_content_type="text/markdown",
    url="https://github.com/binkhq/angelia",
    classifiers=("Programming Language :: Python :: 3",),
    entry_points={"console_scripts": ("manage = app.cli.commands:manage",)},
)
