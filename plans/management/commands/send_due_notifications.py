from django.core.management.base import BaseCommand

from plans.web_push import send_due_notifications


class Command(BaseCommand):
    help = "Send due Web Push notifications and update notification delivery status."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        result = send_due_notifications(
            limit=options["limit"],
            dry_run=options["dry_run"],
        )
        self.stdout.write(
            "processed={processed} sent={sent} failed={failed} skipped={skipped} "
            "deactivated_subscriptions={deactivated}".format(
                processed=result.processed_count,
                sent=result.sent_count,
                failed=result.failed_count,
                skipped=result.skipped_count,
                deactivated=result.deactivated_subscription_count,
            )
        )
