import sys
from setuptools import setup, find_packages


if sys.version_info[:3] < (3, 6):
    raise SystemExit("Minerva requires Python 3.6+")


setup(
    name="jtagtap",
    version="0.1",
    author="Jean-François Nguyen",
    author_email="jf@lambdaconcept.fr",
    install_requires=["nmigen"],
    packages=find_packages()
)
