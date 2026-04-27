import sys

from jira import JIRAError

from bjira.operations import BJiraOperation
from bjira._text import format_comment


class Operation(BJiraOperation):

    def configure_arg_parser(self, subparsers):
        parser = subparsers.add_parser("comments", help="list recent comments")
        parser.add_argument("key", help="issue key")
        parser.add_argument("-n", dest="count", type=int, default=5,
                            help="how many newest comments to show (default 5)")
        parser.set_defaults(func=self._run)

    def _run(self, args):
        jira = self.get_jira_api()
        try:
            all_comments = jira.comments(args.key)
        except JIRAError as exc:
            print(f"ERROR: comments {args.key}: {exc.status_code} {exc.text}",
                  file=sys.stderr)
            sys.exit(3)

        recent = list(reversed(all_comments))[:args.count]
        for c in recent:
            sys.stdout.write(format_comment(c))
