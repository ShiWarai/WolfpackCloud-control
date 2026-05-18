from setuptools import find_packages, setup

package_name = "rosout_ingest"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="WolfpackCloud",
    maintainer_email="control@wolfpack.local",
    description="Ingest /rosout into Control API",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "rosout_ingest_node = rosout_ingest.node:main",
        ],
    },
)
