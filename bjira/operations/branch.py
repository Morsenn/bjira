import os
from argparse import Namespace
from typing import Any

import git
from jira import Issue
from jira.client import ResultList

from bjira.operations import BJiraOperation
from bjira.operations.search import Operation as SearchOperation, DEFAULT_SUMMARY_LENGTH
from bjira.utils import IMG_STATUS_PREFIX

POSITIVE_ANSWERS = ['', 'y', 'yes']
NEGATIVE_ANSWERS = ['n', 'no']
EXPECTED_ANSWERS = POSITIVE_ANSWERS + NEGATIVE_ANSWERS

def _get_repo():
    return git.Repo('.', search_parent_directories=True)

class Operation(BJiraOperation):

    def configure_arg_parser(self, subparsers):
        parser = subparsers.add_parser('branch', help='create git branch for your jira task')
        parser.add_argument("--title", "-t", dest='title', nargs='?', help='jira task title part. When flag set without value then uses repo name', default=[])
        parser.add_argument("-a", "--all", dest='all', nargs='?', help='search tasks with all statuses', default=None)
        parser.set_defaults(func=self._create_branch)

    def _create_branch(self, args):
        repo: git.repo.base.Repo
        try:
            repo = _get_repo()
        except git.exc.InvalidGitRepositoryError:
            print('You have to be in a git-repository')
            return

        task_to_create_branch = self._define_task_to_create(args)

        task_key = task_to_create_branch.key
        if f"remotes/origin/{task_key}" in repo.heads or task_key in repo.heads:
            # Check out the branch using git-checkout.
            # It will fail as the working tree appears dirty.
            try:
                print(f'Switching to existing branch {task_key}')
                repo.git.checkout(task_key)
            except git.GitCommandError:
                print(f"Can't checkout to existing branch {task_key}. Is working tree clean?")
            return

        try:
            print('Fetching master')
            origin = repo.remotes.origin
            origin.fetch("master")
            print('Switching to master')
            repo.git.checkout("master")
            print('Merging origin/master to master')
            repo.git.merge('origin/master', ff_only=True)
        except git.exc.GitError:
            print('Error while pulling master. Is working tree clean?')
            user_decision = None
            while user_decision is None or user_decision.lower() not in EXPECTED_ANSWERS:
                user_decision = input('Create new branch on current HEAD? [y/n]\n')
                if user_decision in NEGATIVE_ANSWERS:
                    return
                if user_decision not in EXPECTED_ANSWERS:
                    print('Unknown option. Try again')

        print(f'Creating branch {task_key}')
        repo.git.checkout("HEAD", b=task_key)

        issue_status = str(task_to_create_branch.fields.status)
        if issue_status.lower() == 'open':
            print(f"Updating task status to 'In progress'")
            # Open to In Progress
            self.get_jira_api().transition_issue(task_key, "4")
            print("Successfully updated task status")



    def _define_task_to_create(self, args) -> Any | Issue:
        all_issues = []

        while True:
            found_issues = self._find_not_finished_tasks(args, offset=len(all_issues))
            self._print_found_issues(found_issues, len(all_issues))
            all_issues.extend(found_issues)

            user_input = input('Type issue number in list to create branch. Type Enter to get more issues\n')
            if user_input.isdigit():
                return all_issues[int(user_input)]

    @staticmethod
    def _print_found_issues(found_issues: dict[str, Any] | ResultList[Issue], start_index: int):
        if found_issues is None or len(found_issues) == 0:
            print('No more issues')

        current_index = start_index
        max_len_summary = max(min(len(issue.fields.summary), DEFAULT_SUMMARY_LENGTH) for issue in found_issues) if found_issues else 0
        max_len_status = max((len(status) for status in IMG_STATUS_PREFIX))
        for issue in found_issues:
            img = IMG_STATUS_PREFIX.get(str(issue.fields.status), '❔')
            output_line = (
                f"{(str(current_index) + ')').ljust(3)} {img} {str(issue.fields.status).ljust(max_len_status)} {issue.fields.summary[:DEFAULT_SUMMARY_LENGTH].ljust(max_len_summary)} {issue.permalink()} "
            )
            print(output_line)
            current_index += 1

    def _find_not_finished_tasks(self, args, offset=0) -> dict[str, Any] | ResultList[Issue]:
        search_args = {
            "limit": 5,
            "offset": offset,
            "types": ["HH"],
            "devteam": [],
            "statuses": ['!closed', '!resolved', '!released', '!fixed', '!Merged To RC'] if args.all is None else None,
            "search": None,
            "title": self._get_title_search_pattern(args),
            "my": None,
            "trim_output": None,
            "silent": True
        }
        return SearchOperation()._execute_search(Namespace(**search_args)).found_issues

    def _get_title_search_pattern(self, args):
        # flag set without value
        if args.title is None:
            # repo name usually equals repo root basename
            git_root = _get_repo().git.rev_parse("--show-toplevel")
            return os.path.basename(git_root)

        if isinstance(args.title, str):
            return args.title

        return None








