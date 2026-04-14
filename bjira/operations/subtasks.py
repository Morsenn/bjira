import io
import re
import sys
import threading
import concurrent.futures
from decimal import Decimal

from jira import Issue
from argparse import Namespace
from bs4 import BeautifulSoup

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
# Извлекает текст между [ и ]
PREFIX_PATTERN = r'\[(.*?)\]'
_MAX_WORKERS = 5

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
    html_formatted_description = portfolio.renderedFields.description

    print('Ищем таблицы в описании портфеля. Это может занять несколько секунд...')
    found_tables = _parse_tables(html_formatted_description)
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

def _parse_tables(html: str):
    tables = []
    parsed_html = BeautifulSoup(html, 'html.parser')

    for table_body in parsed_html.find_all('tbody'):
        table = {}
        table_rows = table_body.find_all('tr')

        first_row = [] if len(table_rows) == 0 else table_rows[0]
        headers = first_row.find_all('th')
        if len(headers) == 0:
            headers = first_row.find_all('td')
        table['header'] = [header.text for header in headers]

        result_rows = []
        for row in table_rows[1::]:
            result_rows.append([cell.text for cell in row.find_all('td')])
        table['rows'] = result_rows
        tables.append(table)

    return tables


def _find_task_prefix(task_title : str):
    matches = re.findall(PREFIX_PATTERN, task_title)
    if len(matches) != 0:
        return matches[0]


def _define_task_type(task_title: str) -> str:
    task_prefix = _find_task_prefix(task_title)
    if task_prefix is None:
        return 'hh'
    if _sanitize_text(task_prefix) in ['hhautotests', 'at', 'autotests', 'autotest', 'hhautotest']:
        return 'at'
    return 'hh'

def _prepare_title(title: str) -> str:
    # create.py adds this prefix
    if _define_task_type(title) == 'at':
        return re.sub(PREFIX_PATTERN, '', title, 1).strip()
    return title


def _format_shirts_summary_string(shirt_to_count_in_portfolio: dict[str, int]) -> str:
    result = ''
    for shirt in SHIRTS_ORDER:
        tasks_with_shirt = shirt_to_count_in_portfolio.get(shirt, 0)
        if tasks_with_shirt != 0:
            comma = ', ' if result != '' else ''
            result = result + comma + str(tasks_with_shirt) + ' - ' + shirt
    return result


class _ThreadBufferedStdout:
    """A sys.stdout proxy that buffers output from worker threads.

    The main thread writes directly to the real stdout.
    Each worker thread writes to its own StringIO buffer, which is
    flushed atomically (under a lock) via drain_to_stdout().
    This ensures that logs from different tasks never interleave.
    """

    def __init__(self, real_stdout):
        self._real = real_stdout
        self._lock = threading.Lock()
        self._buffers = {}
        self._main_tid = threading.get_ident()

    def register_thread(self):
        tid = threading.get_ident()
        with self._lock:
            self._buffers[tid] = io.StringIO()

    def write(self, text):
        tid = threading.get_ident()
        if tid == self._main_tid:
            self._real.write(text)
        else:
            buf = self._buffers.get(tid)
            if buf is not None:
                buf.write(text)
            else:
                self._real.write(text)

    def flush(self):
        if threading.get_ident() == self._main_tid:
            self._real.flush()

    def drain_to_stdout(self, tid):
        with self._lock:
            buf = self._buffers.pop(tid, None)
        if buf:
            text = buf.getvalue()
            buf.close()
            if text:
                with self._lock:
                    self._real.write(text)
                    self._real.flush()

    def __getattr__(self, name):
        return getattr(self._real, name)


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
            '--skip-check', '-sc', dest='skip_check', help="don't check tasks exist before creation", action='store_true'
        )
        parser.add_argument(
            '--skip-storypoints', '-ssp', dest='skip_storypoints', help="don't set storypoints and T-shirts in portfolio", action='store_true'
        )
        parser.add_argument(
            '--skip-description', '-sd', dest='skip_description', help="don't change description in portfolio", action='store_true'
        )
        parser.add_argument(
            '--dryrun', dest='dryrun', default=False, action='store_true', help='just show params and exit'
        )
        parser.add_argument(
            '--workers', '-w', dest='workers', type=int, default=None, help='number of parallel workers for task creation'
        )
        parser.set_defaults(func=self._create_subtasks)

    def _create_subtasks(self, args):
        self.portfolio_id = parse_portfolio_task(args.portfolio)
        jira_api = self.get_jira_api()

        portfolio = jira_api.issue(self.portfolio_id, expand='renderedFields')
        self.decomposition_table = _find_decomposition_table(portfolio)
        self.linked_task_name_to_task = _make_task_name_to_task_mapping(portfolio.get_field('issuelinks'))
        self.header = list(map(_sanitize_text, self.decomposition_table['header']))

        tasks_to_create = []
        for row in self.decomposition_table['rows']:
            task_dict = {self.header[i]: row[i] for i in range(len(self.header))}
            self._add_story_point_and_shirt(task_dict)
            title = task_dict[TITLE_HEADER]

            if not args.skip_check and _sanitize_text(title) in self.linked_task_name_to_task:
                print(f'Пропускаем создание задачи "{title}", так как она уже существует')
                continue

            tasks_to_create.append(task_dict)

        if tasks_to_create:
            self._create_tasks_parallel(tasks_to_create, args)

        portfolio_update_fields = {}
        if not args.skip_storypoints and self.story_points_sum != 0:
            print(f'Adding story points to portfolio: {self.story_points_sum} SP')
            portfolio_update_fields['customfield_11212'] = self.story_points_sum.__float__()  # PORTFOLIO SP

        shirts_summary = _format_shirts_summary_string(self.portfolio_shirts)
        if shirts_summary != '':
            if not args.skip_storypoints:
                print(f'Adding T-shirts to portfolio: {shirts_summary}')
                portfolio_update_fields['customfield_23613'] = shirts_summary  # PORTFOLIO T-Shirts
            if not args.skip_description:
                summary_for_description = f'{shirts_summary} = {self.story_points_sum} SP'
                print(f'Adding summary to the tail of portfolio description: {summary_for_description}')
                portfolio_update_fields[DESCRIPTION_FIELD] = (
                        portfolio.get_field(DESCRIPTION_FIELD) + '\r\n' + summary_for_description
                )

        if args.dryrun or not portfolio_update_fields:
            print(f'Fields for portfolio update: {portfolio_update_fields}')
            return
        portfolio.update(fields=portfolio_update_fields)

    def _create_tasks_parallel(self, tasks_to_create, args):
        max_workers = args.workers if args.workers else min(len(tasks_to_create), _MAX_WORKERS)
        buffered_stdout = _ThreadBufferedStdout(sys.stdout)
        sys.stdout = buffered_stdout
        errors = []
        try:
            # Можно использовать create_issues из jira_api, но скорость этой ручки пропорциональна количеству переданных задач
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_title = {}
                for task_dict in tasks_to_create:
                    future = executor.submit(self._create_single_task, task_dict, args, buffered_stdout)
                    future_to_title[future] = task_dict[TITLE_HEADER]

                for future in concurrent.futures.as_completed(future_to_title):
                    title = future_to_title[future]
                    try:
                        future.result()
                    except Exception as e:
                        errors.append((title, e))
        finally:
            sys.stdout = buffered_stdout._real

        if errors:
            print(f'\nОшибки при создании задач:')
            for title, error in errors:
                print(f'  - "{title}": {error}')

    def _create_single_task(self, task_dict, args, buffered_stdout):
        tid = threading.get_ident()
        buffered_stdout.register_thread()
        try:
            title = task_dict[TITLE_HEADER]

            creation_args = {
                'tax': False,
                'task_type': _define_task_type(title),
                'service': None,
                'portfolio': self.portfolio_id,
                'description': task_dict.get(DESCRIPTION_HEADER, None),
                'version': None,
                'message': _prepare_title(title),
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
                print(f'Задача {title} успешно создана - {self.get_task_url(result.task.key)}')
        finally:
            buffered_stdout.drain_to_stdout(tid)

    def _add_story_point_and_shirt(self, task_dict):
        if task_dict is None:
            return
        try:
            shirt = task_dict[SHIRT_HEADER].upper().strip()
            self.portfolio_shirts[shirt] += 1
            self.story_points_sum += self.get_shirts_mapping()[shirt]
        except KeyError:
            print(f'Неизвестная майка у задачи {task_dict[TITLE_HEADER]}. Сумма маек может быть некорректной')
