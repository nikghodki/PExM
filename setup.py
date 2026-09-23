from setuptools import setup, find_packages

setup(
    name="engram",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "torch>=2.0",
        "transformers>=4.40",
        "safetensors",
        "numpy",
    ],
    description="Predictive experience models for AI agent memory",
    author="Engram Contributors",
    license="Apache-2.0",
)
