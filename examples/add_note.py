from pprint import pprint

from codesurvey import CodeSurvey
from codesurvey.sources import GithubSampleSource
from codesurvey.analyzers.python import PythonAstAnalyzer
from codesurvey.analyzers.python.features import py_ast_feature_finder_with_transform


@py_ast_feature_finder_with_transform('add_note', xpath='Call/func/Attribute')
def has_add_note(func_attribute_el):
    if func_attribute_el.get('attr') == 'add_note':
        return func_attribute_el
    return None


survey = CodeSurvey(
    db_filepath='examples/add_note.sqlite3',
    sources=[
        GithubSampleSource(language='python'),
    ],
    analyzers=[
        PythonAstAnalyzer(
            feature_finders=[
                has_add_note,
            ],
        ),
    ],
    max_workers=3,
    use_saved_features=False,
)

# Runs until Ctrl-C
survey.run()

print('===== repo_features =====')
pprint(survey.get_repo_features()[:1])
print('===== code_features =====')
pprint(survey.get_code_features()[:1])
print('===== survey_tree =====')
pprint(survey.get_survey_tree(), depth=3)
