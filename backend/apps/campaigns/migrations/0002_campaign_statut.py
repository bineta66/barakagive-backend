from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="statut",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("BROUILLON", "Brouillon"),
                    ("PLANIFIER", "Planifiée"),
                    ("EN_COURS", "En cours"),
                    ("TERMINE", "Terminée"),
                    ("ANNULEE", "Annulée"),
                ],
                default="BROUILLON",
            ),
        ),
    ]
