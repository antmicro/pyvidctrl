#!/usr/bin/env python
try:
    from setuptools import setup
except ImportError:
    import distribute_setup
    distribute_setup.use_setuptools()
    from setuptools import setup

setup(
    name='pyvidctrl',
    version='0.1',
    author='Antmicro Ltd',
    description="Simple TUI to control V4L2 cameras",
    author_email='contact@antmicro.com',
    url='https://github.com/antmicro/pyvidctrl',
    packages=['pyvidctrl'],
    entry_points={
        'console_scripts': [
            'pyvidctrl = pyvidctrl.__main__:main',
        ]},
    install_requires=[
        'v4l2 @ git+https://github.com/antmicro/python3-v4l2',
    ],
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: MIT',
        'Operating System :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Topic :: Utilities',
    ],
)
