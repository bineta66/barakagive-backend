from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="projectcriteria",
            old_name="name",
            new_name="nom",
        ),
        migrations.AddField(
            model_name="projectcriteria",
            name="actif",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="projectcriteria",
            name="poids",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="projectcriteria",
            name="projet",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="criteres",
                to="projects.project",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="projectcriteria",
            unique_together={("projet", "nom")},
        ),
        migrations.RemoveField(
            model_name="project",
            name="criteria",
        ),
    ]
