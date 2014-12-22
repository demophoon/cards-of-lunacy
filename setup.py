import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md')) as f:
    README = f.read()

requires = [
    'pyramid',
    'pyramid_chameleon',
    'pyramid_debugtoolbar',
    'waitress',
    'gevent',
    'gevent-websocket==0.3.6',
    'pyramid_sockjs',
    'shortuuid',
]

setup(name='lunacy',
      version='0.0',
      description='Cards Against Humanity(tm) with Friends',
      long_description=README,
      classifiers=[
          "Programming Language :: Python",
          "Framework :: Pyramid",
          "Topic :: Internet :: WWW/HTTP",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
      ],
      author='Britt Gresham',
      author_email='brittcgresham@gmail.com',
      url='http://cards.brittg.com',
      keywords='web pyramid pylons',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      install_requires=requires,
      tests_require=requires,
      test_suite="lunacy",
      entry_points="""\
      [paste.app_factory]
      main = lunacy:main
      """,
      )
