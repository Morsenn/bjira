from bjira.operations import BJiraOperation
from bjira.utils import IMG_STATUS_PREFIX, STATUS_ALIASES

DEFAULT_SUMMARY_LENGTH = 80

class Operation(BJiraOperation):
    def configure_arg_parser(self, subparsers):
        parser = subparsers.add_parser("search", help="search tasks")
        parser.add_argument(dest="limit", type=int, default=10, help="limit", nargs="?")
        parser.add_argument("-o", "--offset", dest="offset", type=int, default=0, help="index of the first issue to return")
        parser.add_argument("-t", "--types", nargs="+", default=[])
        parser.add_argument("-dt", "--devteam", nargs="+", default=[])
        parser.add_argument("-st", "--statuses", nargs="+", default=[])
        parser.add_argument("-s", dest="search", default=None)
        parser.add_argument("-ti", "--title", dest="title", default=None)
        parser.add_argument("-m", "--my", dest="my", nargs="?", default=[])
        parser.add_argument("-tr", "--trim", dest="trim_output", type=int, default=None)
        parser.add_argument("-si", dest="silent", type=bool, default=False)
        parser.set_defaults(func=self._execute_search)

    def _execute_search(self, args):
        api = self.get_jira_api()
        user = api.current_user()
        predicate = ""

        if args.my is None:  # if -m flag is set without any arguments
            args.my = ["assignee", "reporter"]
        if isinstance(args.my, str):
            args.my = [args.my]
        if args.my:
            predicate = "(" + " or ".join(f"{field} = {user}" for field in args.my) + ")"

        if args.types:
            if predicate:
                predicate += " and "
            predicate += "project in (" + ",".join(f'"{t}"' for t in args.types) + ")"

        include_statuses = set([st for st in (args.statuses or []) if not st.startswith("!")])
        if include_statuses:
            include_statuses_normalized = include_statuses
            for alias, values in STATUS_ALIASES.items():
                if alias in include_statuses_normalized:
                    include_statuses.remove(alias)
                    include_statuses.update(values)

            if predicate:
                predicate += " and "
            predicate += "status in (" + ",".join(f'"{t}"' for t in include_statuses) + ")"

        exclude_statuses = set([st.removeprefix("!") for st in (args.statuses or []) if st.startswith("!")])
        if exclude_statuses:
            for alias, values in STATUS_ALIASES.items():
                if alias in exclude_statuses:
                    exclude_statuses.remove(alias)
                    exclude_statuses.update(values)

            if predicate:
                predicate += " and "
            predicate += "status not in (" + ",".join(f'"{t}"' for t in exclude_statuses) + ")"

        if args.search:
            if predicate:
                predicate += " and "
            predicate += f"(text ~ {args.search} or labels = {args.search})"

        if args.title:
            if predicate:
                predicate += " and "
            predicate += f"(summary ~ {args.title})"

        if args.devteam:
            if predicate:
                predicate += " and "
            predicate += '"Development Team" in (' + ",".join(f'"{t}"' for t in args.devteam) + ")"

        query = f"{predicate} ORDER BY created DESC".strip()
        if not args.silent:
            print(f"query: {query}")
        found_issues = api.search_issues(query, startAt=args.offset, maxResults=args.limit)
        max_len_link = max(len(issue.permalink()) for issue in found_issues) if found_issues else 0
        max_len_status = max(len(str(issue.fields.status)) for issue in found_issues) if found_issues else 0
        for issue in found_issues:
            img = IMG_STATUS_PREFIX.get(str(issue.fields.status), '❔')
            output_line = (
                f"{img} {str(issue.fields.status).ljust(max_len_status)} {issue.permalink().ljust(max_len_link)} {issue.fields.summary[:DEFAULT_SUMMARY_LENGTH]}"
            )
            if not args.silent:
                print(output_line[:args.trim_output])


        return MyResult(found_issues)


class MyResult:
    def __init__(self, found_issues):
        self.found_issues = found_issues
