import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class ArmazenamentoPdfPrivado(FileSystemStorage):
    """Armazena PDFs fora de MEDIA_ROOT e sem URL pública."""

    @property
    def base_location(self):
        return settings.PDF_STORAGE_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        return ""
