import uuid

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("pulse_service", "0007_reporttask"),
        ("patients", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AnalysisJob",
            fields=[
                (
                    "job_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("idempotency_token", models.CharField(max_length=128, unique=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("RECEIVED", "Received"),
                            ("PROCESSING_SIGNAL", "Processing signal"),
                            ("ANALYSIS_COMPLETE", "Analysis complete"),
                            ("REPORT_GENERATING", "Report generating"),
                            ("COMPLETED", "Completed"),
                            ("FAILED", "Failed"),
                        ],
                        default="RECEIVED",
                        max_length=32,
                    ),
                ),
                ("language", models.CharField(default="english", max_length=16)),
                (
                    "signal_object_key",
                    models.CharField(blank=True, max_length=512, null=True),
                ),
                (
                    "report_object_key",
                    models.CharField(blank=True, max_length=512, null=True),
                ),
                ("analysis_result", models.JSONField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, max_length=64, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=models.deletion.PROTECT,
                        related_name="analysis_jobs",
                        to="patients.patientsmodel",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "pulse_analysis_job",
                "indexes": [
                    models.Index(fields=["state"], name="pulse_anal_state_idx"),
                    models.Index(
                        fields=["patient", "-created_at"], name="pulse_anal_pat_idx"
                    ),
                ],
            },
        ),
    ]
