"""Synthetic, segregated A/B groups: never represented as live contest evidence."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D
from .core import observation, total_row
from .store import Store


def seed(store: Store):
    if store.scopes():
        raise ValueError('demo requires an empty database; use a separate demo.sqlite3')
    names = ['星河实验室', '北辰 Lab', '向量小队', '极光计划', '编译成功队', '行知工坊',
             '晨光工作室', '矩阵漫游者', '算子探索队', '微秒计划', '青山实验组', '逐浪小队']
    scores = {
      'A': [('234.02','236.14'),('192.57','194.33'),('191.00','192.28'),('187.44','188.82'),
            ('187.56','187.56'),('185.37','187.20'),('173.30','183.62'),('180.87','183.11'),
            ('172.83','174.39'),('172.09','172.78'),('163.26','166.29')],
      'B': [('249.09','257.62'),('245.30','256.33'),('248.85','250.93'),('236.32','238.07'),
            ('231.35','235.89'),('201.09','234.68'),('231.23','232.73'),('153.68','231.52'),
            ('218.90','220.07'),('218.23','219.23'),('202.85','216.84'),('209.33','210.38')]}
    # Fixed relative timestamps make the comparison clear; labels remain explicitly synthetic.
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    for group, totals in scores.items():
        problems = [{'id': group + str(j), 'title': label, 'weight': 1, 'version': 'demo-only'}
                    for j, label in enumerate(['演示题 · 向量计算', '演示题 · 矩阵融合', '演示题 · 稀疏计算'])]
        scope = {'contest_id': 'demo-' + group, 'stage': 'demo-stage', 'group': group,
                 'epoch': 'synthetic-v1', 'problems': problems, 'demo': True, 'title': '星辰杯风格 · ' + group + '组（演示）'}
        for tick in range(4):
            obs, official = [], []
            for i, (current, peak) in enumerate(totals):
                c, p = D(current), D(peak)
                base = [(c / 3).quantize(D('.01'))] * 2
                base.append(c - sum(base))
                gaps = [((p-c) / 3).quantize(D('.01'))] * 2
                gaps.append(p-c-sum(gaps))
                values = [v + gaps[j] if tick == j else max(D(0), v - D(1)) if tick < 3 else v for j, v in enumerate(base)]
                owner = {'_id': f'{group}-{i}', 'team_name': names[i]}
                for j, value in enumerate(values):
                    raw = {'team': owner, 'score': str(value), 'status': 'Pass',
                           'submission_id': f'demo-{group}-{i}-{j}-{tick}',
                           'create_time': (now - timedelta(hours=4-tick)).isoformat(),
                           'result': [{'testcase_id': 'demo-case', 'testcase_status': 'Pass', 'time': 2.4, 'best_time': 1.9}]}
                    obs.append(observation(problems[j]['id'], raw))
                official.append({'team': owner, 'score': str(sum(values))})
            official.sort(key=lambda r: -D(r['score']))
            for position, r in enumerate(official, 1):
                r['rank'] = position
            store.ingest({'schema': 1, 'scope': scope, 'source': 'synthetic-demo',
                          'observed_at': (now - timedelta(hours=3-tick)).isoformat(),
                          'observations': obs, 'totals': [total_row(r) for r in official],
                          'payloads': [], 'notes': ['纯合成数据，仅演示界面和历史聚合，不是任何真实队伍的当前成绩。']})
