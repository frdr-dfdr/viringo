from flask.cli import FlaskGroup

from . import app


cli = FlaskGroup(wsgi)


if __name__ == "__main__":
    cli()

