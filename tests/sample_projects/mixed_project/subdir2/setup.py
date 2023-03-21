from setuptools import setup

setup(
    name="MyLib",
    install_requires=["pandas", "click>=1.2"],
    extras_require={"http": ["requests"], "chinese": ["jieba"]},
)
