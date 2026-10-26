from django.core.management.base import BaseCommand, CommandError

from log_sources.models import LogSource


class Command(BaseCommand):
    help = 'Issue a new ingest token for a log source and print it once (for provisioning scripts).'

    def add_arguments(self, parser):
        parser.add_argument('source_id', type=int)

    def handle(self, source_id, **options):
        source = LogSource.objects.filter(pk=source_id).first()
        if source is None:
            raise CommandError(f'No log source {source_id}')
        self.stdout.write(source.issue_token())
