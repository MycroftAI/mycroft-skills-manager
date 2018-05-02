from setuptools import setup

setup(
    name='py_msm',
    version='0.3.9',
    packages=['py_msm'],
    install_requires=['GitPython'],
    url='https://github.com/JarbasAl/py_msm',
    license='MIT',
    author='jarbasAI',
    author_email='jarbasai@mailfence.com',
    description='Mycroft Skill Manager, in python!',
    entry_points={
        'console_scripts': {
            'msm=py_msm.__main__:main'
        }
    }
)
