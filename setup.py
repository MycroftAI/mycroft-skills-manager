from setuptools import setup

setup(
    name='msm',
    version='0.5.3',
    packages=['msm'],
    install_requires=['GitPython', 'typing'],
    url='https://github.com/MycroftAI/mycroft-skills-manager',
    license='MIT',
    author='jarbasAI, Matthew Scholefield',
    author_email='jarbasai@mailfence.com, matthew331199@gmail.com',
    description='Mycroft Skills Manager',
    entry_points={
        'console_scripts': {
            'msm=msm.__main__:main'
        }
    }
)
