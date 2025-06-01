from bjira.operations import BJiraOperation

DEFAULT_JQL = 'issue in linkedIssues("{}") or parent in linkedIssues("{}")'


class Operation(BJiraOperation):
    def configure_arg_parser(self, subparsers):
        parser = subparsers.add_parser('swimlane', help='create swimlane')
        parser.add_argument(
            dest='portfolio', help='portfolio id', nargs=1
        )
        parser.add_argument(
            '--board', '-b', dest='board', help='board to place swimlane', nargs=1
        )
        parser.add_argument(
            '--jql', '-j',
            dest='jql',
            help='jql pattern for swimlane. Use {} for pasting portfolio',
            nargs='?',
            default=DEFAULT_JQL
        )
        parser.add_argument(
            '--position', '-p',
            dest='position',
            help='swimlane position on board',
            nargs='?',
            default=0)
        parser.set_defaults(func=self._create_swimlane)

    def _create_swimlane(self, args):
        print('Not implemented')
        jira_api = self.get_jira_api()
