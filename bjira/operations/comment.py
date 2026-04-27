import sys

from jira import JIRAError

from bjira.operations import BJiraOperation
from bjira._text import resolve_body_source


class Operation(BJiraOperation):

    def configure_arg_parser(self, subparsers):
        parser = subparsers.add_parser("comment", help="add a comment to an issue")
        parser.add_argument("key", help="issue key, e.g. PORTFOLIO-53307")
        parser.add_argument("body", nargs="?", default=None, help="comment body")
        parser.add_argument("--from-file", dest="from_file", default=None,
                            help="read body from file")
        parser.set_defaults(func=self._run)

    def _run(self, args):
        try:
            body = resolve_body_source(args.body, args.from_file)
        except ValueError as exc:
            print(f"ERROR: comment {args.key}: {exc}", file=sys.stderr)
            sys.exit(2)

        jira = self.get_jira_api()
        try:
            comment = jira.add_comment(args.key, body)
        except JIRAError as exc:
            print(f"ERROR: comment {args.key}: {exc.status_code} {exc.text}",
                  file=sys.stderr)
            sys.exit(3)

        host = self.get_config()["host"]
        print(f"comment id={comment.id} url={host}/browse/{args.key}?focusedCommentId={comment.id}")
