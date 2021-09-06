from setuptools import find_packages, setup
from app.version import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="Angelia",
    version=__version__,
    author="Martin Marsh",
    author_email="mmarsh@bink.com",
    description="Bink API 2.0 Angelia Front End",
    packages=["."] + find_packages(),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://git.bink.com/bink-platform/hermes_api2",
    classifiers=("Programming Language :: Python :: 3",),
    entry_points={"console_scripts": ("manage = app.cli.commands:manage",)},
)
