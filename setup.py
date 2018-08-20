import os 
from setuptools import setup, find_packages

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "AlexaPy",
    version = "0.0.1",
    author = "Keaton Taylor",
    author_email = "keatonstaylor@gmail.com",
    description = ("Python API to control Amazon Echo Devices Programatically"),
    license = "Apache 2.0",
    keywords = "alexa api home assistant",
    packages=find_packages(),
    long_description=read('README.md'),
    classifiers=[
        "Development Status :: 1 - Alpha",
        "Topic :: Utilities",
        "License :: Apache License",
    ],
    install_requires= [
        'beautifulsoup4',
        'simplejson',
        'requests']
)
