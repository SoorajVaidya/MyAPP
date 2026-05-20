from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run a pulse-pipeline worker. Choose 'signal' or 'report'."

    def add_arguments(self, parser):
        parser.add_argument(
            "worker",
            choices=("signal", "report"),
            help="Which worker to run.",
        )

    def handle(self, *args, **options):
        kind = options["worker"]
        if kind == "signal":
            from pulse_service.workers.signal_worker import SignalWorker
            SignalWorker().run_forever()
        elif kind == "report":
            from pulse_service.workers.report_worker import ReportWorker
            ReportWorker().run_forever()
        else:  # defensive — argparse choices already gate this
            raise CommandError(f"unknown worker: {kind}")
