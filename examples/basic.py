from pprint import pprint

from codesurvey import CodeSurvey
from codesurvey.sources import LocalSource, GithubSampleSource, GitSource
from codesurvey.analyzers.python import PythonAstAnalyzer
from codesurvey.analyzers.python.features import py_module_feature_finder, has_set


has_dataclasses = py_module_feature_finder('dataclasses', modules=['dataclasses'])

survey = CodeSurvey(
    db_filepath='examples/basic.sqlite3',
    sources=[
        LocalSource([
            '.',
        ]),
        GitSource([
            'https://github.com/when-of-python/blog.git',
        ]),
        GithubSampleSource(language='python'),
    ],
    analyzers=[
        PythonAstAnalyzer(
            feature_finders=[
                has_set,
                has_dataclasses,
            ],
        ),
    ],
    max_workers=3,
    use_saved_features=False,
)

survey.run(
    max_repos=4
)

print('===== repo_features =====')
pprint(survey.get_repo_features()[:1])
print('===== code_features =====')
pprint(survey.get_code_features()[:1])
print('===== survey_tree =====')
pprint(survey.get_survey_tree(), depth=3)

print('===== analyzer test =====')
analyzer = PythonAstAnalyzer(
    feature_finders=[
        has_set,
        has_dataclasses,
    ],
)
pprint(analyzer.test('''
import dataclasses
'''))
