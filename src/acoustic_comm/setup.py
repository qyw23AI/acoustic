from setuptools import setup, find_packages

setup(
    name="acoustic_comm",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    install_requires=[
        "numpy>=1.23",
        "scipy>=1.10",
        "pyyaml>=6.0",
        "sounddevice>=0.4",
        "soundfile>=0.12",
    ],
)