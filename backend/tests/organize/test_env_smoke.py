"""Le dipendenze esclusive di Organize devono essere importabili nel venv unico."""


def test_mutagen_importabile():
    import mutagen  # noqa: F401


def test_acoustid_importabile():
    import acoustid  # noqa: F401


def test_pillow_importabile():
    from PIL import Image  # noqa: F401
