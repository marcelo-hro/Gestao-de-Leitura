from django.core.management.base import BaseCommand

from sistema.epub_importacao import limpar_previas_expiradas


class Command(BaseCommand):
    help = "Remove prévias de importação de EPUB expiradas e seus arquivos temporários."

    def handle(self, *args, **options):
        removidas = limpar_previas_expiradas()
        self.stdout.write(self.style.SUCCESS(f"{removidas} prévia(s) removida(s)."))
