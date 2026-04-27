import sys

from jira import JIRAError

from bjira.operations import BJiraOperation
from bjira._match import match_transition, AmbiguousMatch, NoMatch


class Operation(BJiraOperation):

    def configure_arg_parser(self, subparsers):
        parser = subparsers.add_parser("status", help="transition an issue")
        parser.add_argument("key", help="issue key")
        parser.add_argument("transition", help="transition id, name, or substring")
        parser.set_defaults(func=self._run)

    def _run(self, args):
        jira = self.get_jira_api()
        try:
            transitions = jira.transitions(args.key)
            issue = jira.issue(args.key, fields="status")
        except JIRAError as exc:
            print(f"ERROR: status {args.key}: {exc.status_code} {exc.text}",
                  file=sys.stderr)
            sys.exit(3)

        try:
            tid = match_transition(args.transition, transitions)
        except (AmbiguousMatch, NoMatch) as exc:
            print(f"ERROR: status {args.key} {args.transition!r}: {exc}",
                  file=sys.stderr)
            sys.exit(3)

        old_status = issue.fields.status.name
        try:
            jira.transition_issue(args.key, tid)
        except JIRAError as exc:
            print(f"ERROR: status {args.key}: {exc.status_code} {exc.text}",
                  file=sys.stderr)
            sys.exit(3)

        new_issue = jira.issue(args.key, fields="status")
        print(f"{args.key}: {old_status} → {new_issue.fields.status.name}")
