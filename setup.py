from setuptools import find_packages, setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="hermes_api2",
    version="0.1",
    author="Martin Marsh",
    author_email="mmarsh@bink.com",
    description="Bink API 2.0 Hermes Front End",
    packages=["."] + find_packages(),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://git.bink.com/bink-platform/hermes_api2",
    classifiers=("Programming Language :: Python :: 3",),
    entry_points={"console_scripts": ("manage = app.cli.commands:manage",)},
)
