from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0005_payment_gateway'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='gateway',
            field=models.CharField(choices=[('vandar', 'وندار'), ('zibal', 'زیبال'), ('bazaar', 'کافه‌بازار')], default='vandar', max_length=10, verbose_name='درگاه'),
        ),
    ]
