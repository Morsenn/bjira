import sys

from jira import JIRAError

from bjira.operations import BJiraOperation
from bjira._fields import merge_labels, parse_due, should_require_force
from bjira._text import resolve_body_source


STORY_POINTS_FIELD = "customfield_11212"


class Operation(BJiraOperation):

    def configure_arg_parser(self, subparsers):
        parser = subparsers.add_parser("edit", help="edit fields on an issue")
        parser.add_argument("key", help="issue key")
        parser.add_argument("--summary", default=None)
        parser.add_argument("--description", default=None)
        parser.add_argument("--description-file", dest="description_file", default=None)
        parser.add_argument("--due", default=None, help="YYYY-MM-DD or 'none' to clear")
        parser.add_argument("--assignee", default=None, help="login or 'none' to unassign")
        parser.add_argument("--label", dest="labels", action="append", default=[],
                            help="repeatable; merged with existing")
        parser.add_argument("--labels-clear", dest="labels_clear", action="store_true")
        parser.add_argument("--sp", dest="story_points", type=float, default=None)
        parser.add_argument("--force", action="store_true",
                            help="allow overwriting non-empty summary/description")
        parser.set_defaults(func=self._run)

    def _run(self, args):
        if args.description is not None and args.description_file is not None:
            self._fail_args("--description and --description-file are mutually exclusive")

        wants_any = any([
            args.summary is not None,
            args.description is not None,
            args.description_file is not None,
            args.due is not None,
            args.assignee is not None,
            args.labels,
            args.labels_clear,
            args.story_points is not None,
        ])
        if not wants_any:
            self._fail_args("nothing to update; pass at least one of "
                            "--summary/--description/--description-file/--due/"
                            "--assignee/--label/--labels-clear/--sp")

        if args.description_file is not None:
            try:
                description = resolve_body_source(None, args.description_file)
            except ValueError as exc:
                self._fail_args(str(exc))
        else:
            description = args.description

        due_payload_set = False
        due_value = None
        if args.due is not None:
            try:
                due_value = parse_due(args.due)
            except ValueError as exc:
                self._fail_args(str(exc))
            due_payload_set = True

        jira = self.get_jira_api()
        try:
            issue = jira.issue(args.key, fields="summary,description,labels")
        except JIRAError as exc:
            self._fail_api(args.key, exc)

        summary_changes = (args.summary is not None
                           and args.summary != (issue.fields.summary or ""))
        description_changes = (description is not None
                               and description != (issue.fields.description or ""))

        if summary_changes and should_require_force(
                "summary", issue.fields.summary or "", args.force):
            self._fail_args(
                f"existing summary is not empty ({len(issue.fields.summary)} chars); "
                "pass --force to overwrite")
        if description_changes and should_require_force(
                "description", issue.fields.description or "", args.force):
            self._fail_args(
                f"existing description is not empty ({len(issue.fields.description)} chars); "
                "pass --force to overwrite")

        fields = {}
        if summary_changes:
            fields["summary"] = args.summary
        if description_changes:
            fields["description"] = description
        if due_payload_set:
            fields["duedate"] = due_value
        if args.assignee is not None:
            fields["assignee"] = None if args.assignee == "none" else {"name": args.assignee}
        if args.labels or args.labels_clear:
            merged = merge_labels(list(issue.fields.labels or []), args.labels, args.labels_clear)
            if merged is not None:
                fields["labels"] = merged
        if args.story_points is not None:
            fields[STORY_POINTS_FIELD] = args.story_points

        if not fields:
            print(f"{args.key}: no changes")
            return

        try:
            issue.update(fields=fields)
        except JIRAError as exc:
            self._fail_api(args.key, exc)

        parts = []
        for k, v in fields.items():
            if k == "description":
                parts.append(f"description=<{len(v)} chars>" if v else "description=cleared")
            else:
                parts.append(f"{k}={v}")
        print(f"OK: {args.key} {', '.join(parts)}")

    def _fail_args(self, msg):
        print(f"ERROR: edit: {msg}", file=sys.stderr)
        sys.exit(2)

    def _fail_api(self, key, exc):
        print(f"ERROR: edit {key}: {exc.status_code} {exc.text}", file=sys.stderr)
        sys.exit(3)
