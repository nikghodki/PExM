from setuptools import setup, find_packages

setup(
    name="pexm",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "torch>=2.0",
        "transformers>=4.40",
        "safetensors",
        "numpy",
    ],
    description="PExM -- Predictive Experience Model for AI agent memory",
    author="PExM Contributors",
    license="Apache-2.0",
)
