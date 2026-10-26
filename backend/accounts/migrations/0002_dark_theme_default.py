from django.db import migrations, models


def system_to_dark(apps, schema_editor):
    # The console is designed dark-first; users who never chose a theme get dark.
    apps.get_model('accounts', 'UserPreference').objects.filter(theme='system').update(theme='dark')


class Migration(migrations.Migration):
    dependencies = [('accounts', '0001_initial')]

    operations = [
        migrations.AlterField(
            model_name='userpreference', name='theme',
            field=models.CharField(choices=[('system', 'System'), ('light', 'Light'), ('dark', 'Dark')], default='dark',
                                   max_length=16),
        ),
        migrations.RunPython(system_to_dark, migrations.RunPython.noop),
    ]
