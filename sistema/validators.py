from django.conf import settings
from django.core.exceptions import ValidationError


def validar_assinatura_pdf(arquivo):
    """Confere se o conteúdo começa com a assinatura de um PDF."""
    try:
        arquivo.seek(0)
        cabecalho = arquivo.read(1024)
    finally:
        try:
            arquivo.seek(0)
        except (AttributeError, OSError, ValueError):
            pass

    if b"%PDF-" not in cabecalho:
        raise ValidationError(
            "O arquivo enviado não contém uma assinatura de PDF válida."
        )


def validar_tamanho_pdf(arquivo):
    """Confere o tamanho do PDF contra PDF_MAX_UPLOAD_SIZE."""
    limite = getattr(
        settings,
        "PDF_MAX_UPLOAD_SIZE",
        20 * 1024 * 1024,
    )
    if arquivo.size > limite:
        raise ValidationError(
            "O arquivo PDF excede o tamanho máximo permitido."
        )
