from django.db import migrations


def preservar_progresso_legado(apps, schema_editor):
    Leitura = apps.get_model("sistema", "Leitura")
    Capitulo = apps.get_model("sistema", "Capitulo")
    CapituloLido = apps.get_model("sistema", "CapituloLido")

    leituras_wn = Leitura.objects.filter(
        obra__formato="WEBNOVEL",
        progresso_atual__gt=0,
    ).select_related("obra")

    for leitura in leituras_wn:
        capitulos_ate_progresso = list(
            Capitulo.objects.filter(
                obra_id=leitura.obra_id,
                numero__lte=leitura.progresso_atual,
            ).order_by("numero")
        )
        if not capitulos_ate_progresso:
            continue

        registros = [
            CapituloLido(
                usuario_id=leitura.usuario_id,
                obra_id=leitura.obra_id,
                capitulo_id=cap.id,
            )
            for cap in capitulos_ate_progresso
        ]
        CapituloLido.objects.bulk_create(registros, ignore_conflicts=True)

        if leitura.ultimo_capitulo_id is None:
            leitura.ultimo_capitulo_id = capitulos_ate_progresso[-1].id
            leitura.save(update_fields=["ultimo_capitulo"])


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0017_alter_volume_options_leitura_ultimo_capitulo_and_more"),
    ]

    operations = [
        migrations.RunPython(
            preservar_progresso_legado,
            migrations.RunPython.noop,
        ),
    ]
