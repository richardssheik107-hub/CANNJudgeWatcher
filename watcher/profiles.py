"""Explicit publication identities; never infer a contest from stored data."""
from dataclasses import dataclass

from .core import ContractError

DEFAULT_PROFILE = 'jingdong-final'


@dataclass(frozen=True)
class Profile:
    name: str
    contest_slug: str
    state_branch: str
    database_name: str
    config_name: str
    contest_id: str | None = None
    problem_ids: tuple[str, ...] = ()
    ranking_scope: str | None = None

    @property
    def state_ref(self):
        return 'refs/heads/' + self.state_branch

    def accepts_scope(self, scope):
        if scope.get('demo') is not False or scope.get('stage') != self.contest_slug:
            return False
        if self.contest_id is not None and scope.get('contest_id') != self.contest_id:
            return False
        if self.ranking_scope is not None and scope.get('ranking_scope') != self.ranking_scope:
            return False
        if self.problem_ids:
            problems = scope.get('problems', [])
            if (len(problems) != len(self.problem_ids)
                    or sorted(item.get('id') for item in problems) != sorted(self.problem_ids)):
                return False
        return True


PROFILES = {
    'starcup-final': Profile(
        'starcup-final', 'ct_starcup_aiop_final', 'watcher-state',
        'starcup-final.sqlite3', 'monitor.starcup-final.json',
    ),
    'jingdong-final': Profile(
        'jingdong-final', 'op_challenge_jingdong_final', 'watcher-state-jingdong-final',
        'jingdong-final.sqlite3', 'monitor.jingdong-final.json',
        '6adac8e13ff2fef7e8929a9f', ('6adb272d1dac5d235bd66d0b',), 'problem',
    ),
}


def get_profile(name='starcup-final'):
    if not isinstance(name, str) or name not in PROFILES:
        raise ContractError('unknown public monitoring profile')
    return PROFILES[name]
