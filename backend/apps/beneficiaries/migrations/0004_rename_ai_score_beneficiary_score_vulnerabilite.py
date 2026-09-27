from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("beneficiaries", "0003_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="beneficiary",
            old_name="ai_score",
            new_name="score_vulnerabilite",
        ),
    ]
