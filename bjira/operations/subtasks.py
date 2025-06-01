import re
from decimal import Decimal

from jira import Issue
from mrkdwn_analysis import MarkdownAnalyzer
from jira2markdown import convert as convert_to_markdown
from argparse import Namespace

from bjira.operations import BJiraOperation, SHIRTS_ORDER
from bjira.operations.create import Operation as CreateOperation
from bjira.utils import parse_portfolio_task

DESCRIPTION_FIELD = 'description'
TITLE_FIELD = 'summary'
SHIRT_FIELD = 'customfield_23911'
STORY_POINT_FIELD = 'customfield_11212'

TITLE_HEADER = 'задача'
SHIRT_HEADER = 'оценка'
DESCRIPTION_HEADER = 'описание'
HEADER_FIELD_MAPPING = {
    TITLE_HEADER: TITLE_FIELD,
    SHIRT_HEADER: SHIRT_FIELD,
    DESCRIPTION_HEADER: DESCRIPTION_FIELD
}


def _sanitize_text(text: str) -> str:
    # Удаляем всё, кроме цифр и русских и английских букв
    return re.sub(r'[^a-zA-Zа-яА-Я0-9]', '', text).lower()


def _make_task_name_to_task_mapping(tasks) -> dict[str, Issue]:
    filtered_tasks = []
    for task in tasks:
        if hasattr(task, 'outwardIssue'):
            filtered_tasks.append(task.outwardIssue)
    return {_sanitize_text(task.get_field(TITLE_FIELD)): task for task in filtered_tasks}


def _find_decomposition_table(portfolio: Issue):
    print('Ищем таблицы в описании портфеля. Это может занять несколько секунд...')
    found_tables = (MarkdownAnalyzer
                    .from_string(convert_to_markdown(portfolio.get_field(DESCRIPTION_FIELD)))
                    .identify_tables())['Table']
    print(f'Найдено {len(found_tables)} таблиц')

    for table in found_tables:
        raw_header = table['header']
        header = list(map(_sanitize_text, raw_header))
        if SHIRT_HEADER in header and TITLE_HEADER in header:
            print(f'Найдена таблица декомпозиции. Её заголовки: {raw_header}')
            return table
        else:
            print(f'Пропускаем таблицу с заголовками {raw_header}')
    print('Таблица с декомпозицией не найдена')


def _find_task_prefix(task_title : str):
    # Извлекает текст между [ и ]
    pattern = r'\[(.*?)\]'
    matches = re.findall(pattern, task_title)
    if len(matches) != 0:
        return matches[0]


def _define_task_type(task_prefix: str) -> str:
    if task_prefix is None:
        return 'hh'
    if _sanitize_text(task_prefix) in ['hhautotests', 'at', 'autotests', 'autotest', 'hhautotest']:
        return 'at'
    return 'hh'


def _format_shirts_summary_string(shirt_to_count_in_portfolio: dict[str, int]) -> str:
    result = ''
    for shirt in SHIRTS_ORDER:
        tasks_with_shirt = shirt_to_count_in_portfolio.get(shirt, 0)
        if tasks_with_shirt != 0:
            comma = ', ' if result != '' else ''
            result = result + comma + str(tasks_with_shirt) + ' - ' + shirt
    return result


class Operation(BJiraOperation):
    def __init__(self):
        super().__init__()
        self.story_points_sum = Decimal('0')
        self.portfolio_shirts = {shirt: 0 for shirt in self.get_shirts_mapping().keys()}

    def configure_arg_parser(self, subparsers):
        parser = subparsers.add_parser('subtasks', help='create subtasks for portfolio')
        parser.add_argument(
            dest='portfolio', help='portfolio id'
        )
        parser.add_argument(
            '--skip-check', '-s', dest='skip_check', help="don't check tasks exist before creation", nargs='?',
            default=False
        )
        parser.add_argument(
            '--no-swimlane', '-nsl', dest='no_swimlane', help="don't create swimlane for portfolio", nargs='?',
            default=False
        )
        parser.add_argument(
            '--board', '-b', dest='board', help='board id for swimlane', nargs='?'
        )
        parser.add_argument(  # Not implemented
            '--position', '-p',
            dest='position',
            help='swimlane position on board',
            nargs='?',
            default=0)
        parser.add_argument(
            '--dryrun', dest='dryrun', default=False, action='store_true', help='just show params and exit'
        )
        parser.set_defaults(func=self._create_subtasks)

    def _create_subtasks(self, args):
        self.portfolio_id = parse_portfolio_task(args.portfolio)
        jira_api = self.get_jira_api()

        portfolio = jira_api.issue(self.portfolio_id)
        self.decomposition_table = _find_decomposition_table(portfolio)
        self.linked_task_name_to_task = _make_task_name_to_task_mapping(portfolio.get_field('issuelinks'))
        self.header = list(map(_sanitize_text, self.decomposition_table['header']))

        for row in self.decomposition_table['rows']:
            self._create_task(row, args)

        portfolio_update_fields = {}
        if self.story_points_sum != 0:
            print(f'Adding story points to portfolio: {self.story_points_sum} SP')
            portfolio_update_fields['customfield_11212'] = self.story_points_sum.__float__()  # PORTFOLIO SP

        shirts_summary = _format_shirts_summary_string(self.portfolio_shirts)
        if shirts_summary != '':
            print(f'Adding shirts to portfolio: {shirts_summary}')
            portfolio_update_fields['customfield_23613'] = shirts_summary  # PORTFOLIO T-Shirts
            portfolio_update_fields[DESCRIPTION_FIELD] = (
                    portfolio.get_field(DESCRIPTION_FIELD) + '\r\n' + f'{shirts_summary} = {self.story_points_sum} SP'
            )

        if args.dryrun:
            print(f'Fields for portfolio update: {portfolio_update_fields}')
            return
        portfolio.update(fields=portfolio_update_fields)

    def _create_task(self, row, args):
        task_dict = {self.header[i]: row[i] for i in range(len(self.header))}
        self._add_story_point_and_shirt(task_dict)
        title = task_dict[TITLE_HEADER]

        task_already_exists = ((args.skip_check is not None)
                               and _sanitize_text(title) in self.linked_task_name_to_task)
        if task_already_exists:
            print(f'Пропускаем создание задачи "{title}", так как она уже существует')
            return

        creation_args = {
            'task_type': _define_task_type(_find_task_prefix(title)),
            'service': None,
            'portfolio': self.portfolio_id,
            'description': task_dict.get(DESCRIPTION_HEADER, None),
            'version': None,
            'message': title,
            'team': None,
            'sp': None,
            'labels': None,
            'shirt': None,
            'check': False,
            'dryrun': args.dryrun
        }

        try:
            creation_args['shirt'] = task_dict[SHIRT_HEADER].upper().strip()
        except KeyError:
            pass

        result = CreateOperation()._create_new_task(Namespace(**creation_args))
        if not args.dryrun:
            print(f'Задача {title} успешно создана - {self.get_task_url(result.key)}')

    def _add_story_point_and_shirt(self, task_dict):
        if task_dict is None:
            return
        try:
            shirt = task_dict[SHIRT_HEADER].upper().strip()
            self.portfolio_shirts[shirt] += 1
            self.story_points_sum += self.get_shirts_mapping()[shirt]
        except KeyError:
            print(f'Неизвестная майка у задачи {task_dict[TITLE_HEADER]}. Сумма маек может быть некорректной')
